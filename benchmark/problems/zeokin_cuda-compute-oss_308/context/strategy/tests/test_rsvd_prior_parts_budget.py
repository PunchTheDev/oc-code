"""CPU-only tests: rsvd charges prior sketch parts into later stream budgets.

rsvd.basis keeps each (n, w_i) sketch result in ``parts`` while running the next
stream_gemm_*. On MPS, free_compute_bytes() is a static ceiling, so those prior
buffers must be passed as ``extra_fixed_bytes`` or sketches 2/3 under-budget and
can OOM. Pure stub/arithmetic; no GPU needed.

Run:  python strategy/tests/test_rsvd_prior_parts_budget.py
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from strategy import subspace as sub
from strategy.transforms import RandomizedSVDTransform


class _XP:
    concatenate = staticmethod(np.concatenate)

    class linalg:
        qr = staticmethod(np.linalg.qr)


class _FakeBackend:
    xp = _XP()

    def to_device(self, x):
        return np.asarray(x)


def _capture_extra_fixed(n=96, m=30, dtype=np.float32):
    """Call rsvd.basis with stubbed sketches; return each call's extra_fixed_bytes."""
    captured = []
    orig_r, orig_l = sub.stream_gemm_right, sub.stream_gemm_left_t

    def fake(X, Q, backend, dt, frac=sub._DEFAULT_ROW_BLOCK_FRACTION,
             extra_fixed_bytes=0):
        captured.append(int(extra_fixed_bytes))
        return np.zeros((X.shape[0], Q.shape[1]), dtype=dt)

    sub.stream_gemm_right = fake
    sub.stream_gemm_left_t = fake
    try:
        A = np.eye(n, dtype=dtype)
        B = np.eye(n, dtype=dtype)
        Q = RandomizedSVDTransform(seed=0).basis(
            n, m, _FakeBackend(), dtype, A=A, B=B, frac=0.3
        )
        assert Q.shape == (n, m)
    finally:
        sub.stream_gemm_right, sub.stream_gemm_left_t = orig_r, orig_l
    return captured


def test_rsvd_charges_cumulative_prior_parts():
    # Three equal-ish widths for m=30: [10, 10, 10]. After sketch i, prior grows
    # by n * w_i * itemsize.
    n, m = 96, 30
    item = np.dtype(np.float32).itemsize
    base, rem = divmod(m, 3)
    widths = [base + (1 if i < rem else 0) for i in range(3)]
    assert widths == [10, 10, 10]

    seen = _capture_extra_fixed(n=n, m=m)
    assert seen == [
        0,
        n * widths[0] * item,
        n * (widths[0] + widths[1]) * item,
    ], seen


def test_rsvd_prior_parts_keeps_peak_within_budget():
    """Arithmetic: with prior parts charged, sketch-3 peak fits; without it overshoots."""
    n, m, item, frac = 8192, 1024, 4, 0.3
    free = 300 * 1024**2
    budget = int(free * frac)
    base, rem = divmod(m, 3)
    w = [base + (1 if i < rem else 0) for i in range(3)]
    prior = n * (w[0] + w[1]) * item
    # left_t steady-state: acc + product = 2*n*w; caller prior charged as extra.
    fixed = 2 * n * w[2] * item + prior
    blk = max(1, (budget - fixed) // (n * item))
    peak = fixed + blk * n * item
    assert peak <= budget

    # Old model: same left_t fixed cost, prior parts omitted -> overshoots.
    old_fixed = 2 * n * w[2] * item
    old_blk = max(1, (budget - old_fixed) // (n * item))
    old_peak = old_fixed + old_blk * n * item + prior
    assert old_peak > budget


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
