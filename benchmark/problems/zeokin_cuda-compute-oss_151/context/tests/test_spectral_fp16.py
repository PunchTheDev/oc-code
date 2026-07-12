"""Regression tests: the spectral global branch must handle fp16 (issue TBD).

`spectral_global_mix` fed a raw tensor into torch.fft.rfft, which PyTorch does not
support in half precision -- so the DEFAULT benchmark (AttentionSpec.dtype='fp16',
benchmark --mode fixed) crashed with "Unsupported dtype Half". The sibling spectral
branches already upcast to fp32; this pins that spectral_global_mix does too.

CPU-safe: skips cleanly when torch is not installed.
Run:  python tests/test_spectral_fp16.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import torch
except Exception:  # noqa: BLE001
    torch = None

if torch is not None:
    from attention.hybrid import hybrid_attention, spectral_global_mix


def _skip_if_no_torch():
    if torch is None:
        print("SKIP  torch not installed")
        return True
    return False


def test_spectral_global_mix_fp16_does_not_crash():
    if _skip_if_no_torch():
        return
    torch.manual_seed(0)
    v = torch.randn(1, 2, 64, 8, dtype=torch.float16)
    out = spectral_global_mix(v)
    assert out.dtype == torch.float16
    assert out.shape == v.shape
    assert torch.isfinite(out.float()).all()


def test_spectral_global_mix_fp16_matches_fp32():
    if _skip_if_no_torch():
        return
    torch.manual_seed(1)
    v32 = torch.randn(1, 2, 48, 8, dtype=torch.float32)
    out32 = spectral_global_mix(v32)
    out16 = spectral_global_mix(v32.to(torch.float16)).float()
    # fp16 rounding of the input/output only; the FFT itself runs in fp32.
    assert torch.allclose(out16, out32, atol=5e-2, rtol=5e-2)


def test_spectral_global_mix_fp32_unchanged():
    """fp32 path is identical (upcast to float32 is a no-op)."""
    if _skip_if_no_torch():
        return
    torch.manual_seed(2)
    v = torch.randn(1, 1, 32, 4, dtype=torch.float32)
    seq = v.shape[-2]
    vf = torch.fft.rfft(v, dim=-2)
    freqs = torch.arange(vf.shape[-2], dtype=torch.float32)
    gain = 1.0 / (1.0 + 1.0 * freqs)
    expected = torch.fft.irfft(vf * gain.view(1, 1, -1, 1), n=seq, dim=-2)
    assert torch.allclose(spectral_global_mix(v), expected, atol=1e-6)


def test_hybrid_attention_fp16_default_path_runs():
    """The default reference operator (fp16, spectral global branch) must run."""
    if _skip_if_no_torch():
        return
    torch.manual_seed(3)
    q = torch.randn(1, 2, 100, 8, dtype=torch.float16)
    k = torch.randn(1, 2, 100, 8, dtype=torch.float16)
    v = torch.randn(1, 2, 100, 8, dtype=torch.float16)
    out = hybrid_attention(q, k, v, window=16)
    assert out.dtype == torch.float16
    assert torch.isfinite(out.float()).all()


if __name__ == "__main__":
    fns = [v for kk, v in sorted(globals().items()) if kk.startswith("test_")]
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