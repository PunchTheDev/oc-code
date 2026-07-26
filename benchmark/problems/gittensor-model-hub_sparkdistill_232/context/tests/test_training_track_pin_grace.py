"""Tests for canonical-pin grace window during training-track PRs (issue #118)."""

import json
from pathlib import Path

import pytest

from eval.canonical_dataset import sft_sha256_from_canonical_text
from eval.training_track_gate import (
    _canonical_sft_sha256s_for_pr_window,
    gate_training_pr,
    validate_pr_body_canonical_pin,
    verify_remote_proof_bundle,
)


def _canonical_json(sft_sha: str) -> str:
    return json.dumps(
        {
            "repo_id": "gittensor-model-hub/sparkproof-mining",
            "hf_url": "https://huggingface.co/datasets/gittensor-model-hub/sparkproof-mining",
            "mix_manifest": {"sft_sha256": sft_sha, "rows_total": 100},
        }
    )


SHA_HEAD = "a" * 64
SHA_BASE = "b" * 64
SHA_MID = "c" * 64


def test_sft_sha256_from_canonical_text():
    assert sft_sha256_from_canonical_text(_canonical_json(SHA_HEAD)) == SHA_HEAD
    assert sft_sha256_from_canonical_text("not json") is None


def test_canonical_sft_sha256s_for_pr_window(monkeypatch):
    def fake_show(ref: str, path: str) -> str | None:
        if path != "datasets/canonical.json":
            return None
        if ref in ("HEAD", "head"):
            return _canonical_json(SHA_HEAD)
        if ref == "merge-base":
            return _canonical_json(SHA_BASE)
        if ref == "mid-commit":
            return _canonical_json(SHA_MID)
        return None

    def fake_log(cmd, **kwargs):
        assert "merge-base..HEAD" in cmd
        class Result:
            returncode = 0
            stdout = "mid-commit\n"
        return Result()

    monkeypatch.setattr("eval.training_track_gate._git_show", fake_show)
    monkeypatch.setattr("eval.training_track_gate.subprocess.run", fake_log)

    shas = _canonical_sft_sha256s_for_pr_window(merge_base_ref="merge-base", head_ref="HEAD")
    assert shas == {SHA_HEAD, SHA_BASE, SHA_MID}


def test_validate_pr_body_accepts_merge_base_pin():
    url = "https://huggingface.co/datasets/gittensor-model-hub/sparkproof-mining"
    body = f"Canonical dataset URL: {url}\nPinned sft_sha256: `{SHA_BASE}`\n"
    issues = validate_pr_body_canonical_pin(body, acceptable_sft_shas={SHA_BASE, SHA_HEAD})
    assert issues == []


def test_validate_pr_body_rejects_stale_pin():
    url = "https://huggingface.co/datasets/gittensor-model-hub/sparkproof-mining"
    stale = "d" * 64
    body = f"Canonical dataset URL: {url}\nPinned sft_sha256: `{stale}`\n"
    issues = validate_pr_body_canonical_pin(body, acceptable_sft_shas={SHA_BASE, SHA_HEAD})
    assert issues
    assert any("merge-base window" in issue for issue in issues)


def test_verify_remote_proof_bundle_accepts_base_pin(monkeypatch):
    def fake_download(*, repo_id, repo_type, filename, token=None):
        tmp = Path("/tmp") / f"fake_{filename}"
        if filename == "manifest.json":
            tmp.write_text(
                json.dumps(
                    {
                        "dataset_url": (
                            "https://huggingface.co/datasets/gittensor-model-hub/sparkproof-mining"
                        )
                    }
                ),
                encoding="utf-8",
            )
        elif filename == "mix_manifest.json":
            tmp.write_text(json.dumps({"sft_sha256": SHA_BASE}), encoding="utf-8")
        return str(tmp)

    monkeypatch.setattr("huggingface_hub.hf_hub_download", fake_download)

    issues = verify_remote_proof_bundle(
        "gittensor-model-hub/test-bundle",
        acceptable_sft_shas={SHA_BASE, SHA_HEAD},
    )
    assert issues == []


def test_verify_remote_proof_bundle_rejects_outside_window(monkeypatch):
    def fake_download(*, repo_id, repo_type, filename, token=None):
        tmp = Path("/tmp") / f"fake2_{filename}"
        if filename == "manifest.json":
            tmp.write_text(
                json.dumps(
                    {
                        "dataset_url": (
                            "https://huggingface.co/datasets/gittensor-model-hub/sparkproof-mining"
                        )
                    }
                ),
                encoding="utf-8",
            )
        elif filename == "mix_manifest.json":
            tmp.write_text(json.dumps({"sft_sha256": "e" * 64}), encoding="utf-8")
        return str(tmp)

    monkeypatch.setattr("huggingface_hub.hf_hub_download", fake_download)

    issues = verify_remote_proof_bundle(
        "gittensor-model-hub/test-bundle",
        acceptable_sft_shas={SHA_BASE, SHA_HEAD},
    )
    assert any("accepted canonical pin" in issue for issue in issues)
