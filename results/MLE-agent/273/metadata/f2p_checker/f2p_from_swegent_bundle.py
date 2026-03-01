#!/usr/bin/env python3
"""
Run a single Fail2Pass check from a SWEGENT bundle folder.

Input bundle directory is expected to contain (example):
  - issue_256.json
  - test256.py
  - *.dockerfile (e.g. claude.dockerfile)

This script will:
  1) Parse repo + base_sha + head_sha from issue_*.json
  2) Create two git worktrees (base/head)
  3) Copy the bundle test file(s) + dockerfile into each worktree
  4) docker build + docker run pytest for base and head
  5) Classify as fail2pass/fail2fail/pass2pass/pass2fail/error

Notes:
  - Many bundles embed API keys inside the provided Dockerfile. Treat them as secrets.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class RunResult:
    ok: bool
    exit_code: int
    stdout: str
    stderr: str


def _run(cmd: list[str], cwd: Path | None = None, timeout_s: int = 3600) -> RunResult:
    p = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout_s,
        env=os.environ.copy(),
    )
    return RunResult(ok=(p.returncode == 0), exit_code=p.returncode, stdout=p.stdout or "", stderr=p.stderr or "")


def _die(msg: str) -> None:
    print(msg, file=sys.stderr)
    sys.exit(2)


def _parse_repo_from_issue_url(url: str) -> str:
    # https://github.com/always-further/AgentUp/issues/256
    m = re.search(r"github\.com/([^/]+/[^/]+)/(?:issues|pull)/\d+", url or "")
    if not m:
        raise ValueError(f"Cannot parse repo from url: {url!r}")
    return m.group(1)


def _load_issue_json(bundle_dir: Path) -> dict[str, Any]:
    candidates = sorted(bundle_dir.glob("issue_*.json"))
    if not candidates:
        raise FileNotFoundError(f"No issue_*.json found under {bundle_dir}")
    # Prefer issue_<number>.json if present
    issue_json = candidates[0]
    with issue_json.open("r", encoding="utf-8") as f:
        return json.load(f)


def _pick_dockerfile(bundle_dir: Path) -> Path:
    cands = sorted(bundle_dir.glob("*.dockerfile"))
    if not cands:
        raise FileNotFoundError(f"No *.dockerfile found under {bundle_dir}")
    return cands[0]


def _pick_tests(bundle_dir: Path) -> list[Path]:
    # prefer test*.py, otherwise any *.py excluding issue_*.json and non-test utilities
    tests = sorted(bundle_dir.glob("test*.py"))
    if tests:
        return tests
    py = [p for p in sorted(bundle_dir.glob("*.py")) if not p.name.startswith("issue_")]
    return py


def _ensure_tools() -> None:
    for tool in ("git", "docker"):
        if shutil.which(tool) is None:
            _die(f"Missing required tool: {tool}. Please install it first.")


def _classify(before_ok: bool, after_ok: bool) -> str:
    if (not before_ok) and after_ok:
        return "fail2pass"
    if (not before_ok) and (not after_ok):
        return "fail2fail"
    if before_ok and after_ok:
        return "pass2pass"
    if before_ok and (not after_ok):
        return "pass2fail"
    return "error"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle_dir", type=Path, help="Extracted SWEGENT bundle folder (contains issue_*.json, test*.py, *.dockerfile)")
    repo_root = Path(__file__).resolve().parent.parent
    default_work_dir = repo_root / "run_instances" / "swegent_f2p"
    parser.add_argument("--work-dir", type=Path, default=default_work_dir, help="Where to create temp worktrees and logs")
    parser.add_argument("--keep-workdir", action="store_true", help="Do not delete temp worktrees after run")
    parser.add_argument("--pytest-args", type=str, default="-q", help="Extra args passed to pytest (string)")
    parser.add_argument("--timeout-build", type=int, default=3600, help="docker build timeout seconds")
    parser.add_argument("--timeout-test", type=int, default=1800, help="docker run pytest timeout seconds")
    args = parser.parse_args()

    bundle_dir = args.bundle_dir.resolve()
    if not bundle_dir.exists():
        _die(f"Bundle dir not found: {bundle_dir}")

    _ensure_tools()

    issue = _load_issue_json(bundle_dir)
    issue_number = issue.get("number")
    issue_url = issue.get("url") or ""
    repo = _parse_repo_from_issue_url(issue_url)

    linked_prs = issue.get("linked_prs") or []
    if not linked_prs:
        _die("issue_*.json has no linked_prs; cannot get base/head sha.")
    pr0 = linked_prs[0]
    base_sha = pr0.get("base_sha")
    head_sha = pr0.get("head_sha")
    patch_text = pr0.get("patch") or ""
    if not base_sha:
        _die("linked_prs[0] missing base_sha.")
    if not patch_text.strip():
        _die("linked_prs[0] missing patch text; cannot apply fix on top of base_sha.")

    dockerfile_src = _pick_dockerfile(bundle_dir)
    test_files = _pick_tests(bundle_dir)
    if not test_files:
        _die(f"No test*.py found under {bundle_dir}")

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"issue_{issue_number}-{ts}" if issue_number else f"bundle-{ts}"
    run_root = (args.work_dir / run_id).resolve()
    run_root.mkdir(parents=True, exist_ok=True)

    meta = {
        "run_id": run_id,
        "bundle_dir": str(bundle_dir),
        "repo": repo,
        "issue_url": issue_url,
        "issue_number": issue_number,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "dockerfile": dockerfile_src.name,
        "tests": [p.name for p in test_files],
    }
    (run_root / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # 1) Clone repo (bare-ish) to serve worktrees
    origin_url = f"https://github.com/{repo}.git"
    repo_dir = run_root / "repo"
    base_dir = run_root / "base"
    head_dir = run_root / "head"

    clone = _run(["git", "clone", "--no-checkout", origin_url, str(repo_dir)], cwd=run_root, timeout_s=3600)
    (run_root / "git_clone.stdout.txt").write_text(clone.stdout, encoding="utf-8")
    (run_root / "git_clone.stderr.txt").write_text(clone.stderr, encoding="utf-8")
    if not clone.ok:
        _die(f"git clone failed (see logs under {run_root})")

    fetch = _run(["git", "fetch", "--all", "--tags"], cwd=repo_dir, timeout_s=3600)
    (run_root / "git_fetch.stdout.txt").write_text(fetch.stdout, encoding="utf-8")
    (run_root / "git_fetch.stderr.txt").write_text(fetch.stderr, encoding="utf-8")
    if not fetch.ok:
        _die("git fetch failed")

    # Write patch once (used to create "after" from base_sha)
    patch_path = run_root / "gold_patch.diff"
    patch_path.write_text(patch_text, encoding="utf-8")

    # 2) Create worktrees
    wt_base = _run(["git", "worktree", "add", "--detach", str(base_dir), str(base_sha)], cwd=repo_dir, timeout_s=600)
    (run_root / "git_worktree_base.stdout.txt").write_text(wt_base.stdout, encoding="utf-8")
    (run_root / "git_worktree_base.stderr.txt").write_text(wt_base.stderr, encoding="utf-8")
    if not wt_base.ok:
        _die("git worktree add (base) failed")

    # Some PR head_sha may be unreachable (squash merge). Build "after" by applying patch onto base_sha.
    wt_head = _run(["git", "worktree", "add", "--detach", str(head_dir), str(base_sha)], cwd=repo_dir, timeout_s=600)
    (run_root / "git_worktree_head.stdout.txt").write_text(wt_head.stdout, encoding="utf-8")
    (run_root / "git_worktree_head.stderr.txt").write_text(wt_head.stderr, encoding="utf-8")
    if not wt_head.ok:
        _die("git worktree add (head) failed")

    apply_patch = _run(["git", "apply", "--whitespace=nowarn", str(patch_path)], cwd=head_dir, timeout_s=300)
    (run_root / "git_apply_patch.stdout.txt").write_text(apply_patch.stdout, encoding="utf-8")
    (run_root / "git_apply_patch.stderr.txt").write_text(apply_patch.stderr, encoding="utf-8")
    if not apply_patch.ok:
        _die("git apply patch failed (see git_apply_patch.stderr.txt)")

    # 3) Copy test(s) + dockerfile into each worktree
    def stage_bundle_into(worktree: Path) -> None:
        shutil.copy2(dockerfile_src, worktree / dockerfile_src.name)
        for t in test_files:
            shutil.copy2(t, worktree / t.name)

    stage_bundle_into(base_dir)
    stage_bundle_into(head_dir)

    pytest_args = args.pytest_args.strip().split() if args.pytest_args.strip() else []

    def build_and_test(label: str, worktree: Path) -> dict[str, Any]:
        image = f"swegent-f2p:{run_id}-{label}".lower()
        # Build
        b = _run(
            ["docker", "build", "-t", image, "-f", dockerfile_src.name, "."],
            cwd=worktree,
            timeout_s=args.timeout_build,
        )
        (run_root / f"docker_build_{label}.stdout.txt").write_text(b.stdout, encoding="utf-8")
        (run_root / f"docker_build_{label}.stderr.txt").write_text(b.stderr, encoding="utf-8")
        if not b.ok:
            return {"label": label, "image": image, "build_ok": False, "test_ok": False, "build_exit": b.exit_code, "test_exit": None}

        # Test: run pytest for all bundle tests
        cmd = ["docker", "run", "--rm", image, "pytest", *pytest_args, *[t.name for t in test_files]]
        t = _run(cmd, cwd=worktree, timeout_s=args.timeout_test)
        (run_root / f"pytest_{label}.stdout.txt").write_text(t.stdout, encoding="utf-8")
        (run_root / f"pytest_{label}.stderr.txt").write_text(t.stderr, encoding="utf-8")
        return {
            "label": label,
            "image": image,
            "build_ok": True,
            "test_ok": t.ok,
            "build_exit": b.exit_code,
            "test_exit": t.exit_code,
        }

    before = build_and_test("before", base_dir)
    after = build_and_test("after", head_dir)

    status = _classify(bool(before.get("test_ok")), bool(after.get("test_ok")))
    report = {
        **meta,
        "status": status,
        "before": before,
        "after": after,
        "paths": {
            "run_root": str(run_root),
            "base_worktree": str(base_dir),
            "head_worktree": str(head_dir),
        },
    }
    (run_root / "f2p_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[F2P] {status}")
    print(f"Report: {run_root / 'f2p_report.json'}")

    if not args.keep_workdir:
        # Keep the report + logs but remove worktrees to save space
        try:
            _run(["git", "worktree", "remove", "--force", str(base_dir)], cwd=repo_dir, timeout_s=300)
            _run(["git", "worktree", "remove", "--force", str(head_dir)], cwd=repo_dir, timeout_s=300)
        except Exception:
            pass


if __name__ == "__main__":
    main()

