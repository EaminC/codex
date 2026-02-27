#!/usr/bin/env python3
import argparse
import json
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Set, Tuple


def run_cmd(
    cmd: List[str],
    cwd: Path | None = None,
    env: Dict[str, str] | None = None,
    capture_output: bool = True,
) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            env=env,
            check=True,
            text=True,
            capture_output=capture_output,
        )
    except subprocess.CalledProcessError as e:
        stderr = (e.stderr or "").strip()
        stdout = (e.stdout or "").strip()
        details = stderr or stdout or "No stderr/stdout output."
        cmd_text = " ".join(shlex.quote(part) for part in e.cmd)
        raise RuntimeError(
            f"Command failed (exit {e.returncode}): {cmd_text}\n{details}"
        ) from e
    except FileNotFoundError as e:
        missing = cmd[0] if cmd else "<unknown>"
        raise RuntimeError(
            f"Command not found: '{missing}'. Install it and make sure it is in PATH."
        ) from e


def load_map(path: Path) -> List[dict]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("issue_pr_map.json must be a JSON array.")
    return data


def ensure_repo(repo_full_name: str, repos_root: Path) -> Tuple[Path, bool]:
    repo_name = repo_full_name.split("/")[-1]
    repo_dir = repos_root / repo_name
    if (repo_dir / ".git").exists():
        return repo_dir, False
    if repo_dir.exists() and not (repo_dir / ".git").exists():
        raise RuntimeError(
            f"Target path exists but is not a git repo: {repo_dir}. "
            "Delete/rename it or choose a different --repos-root."
        )

    try:
        run_cmd(["gh", "repo", "clone", repo_full_name, str(repo_dir)], cwd=repos_root)
    except RuntimeError:
        # Fallback to git clone via HTTPS when gh clone fails.
        run_cmd(
            ["git", "clone", f"https://github.com/{repo_full_name}.git", str(repo_dir)],
            cwd=repos_root,
        )
    return repo_dir, True


def gh_api_json(endpoint: str) -> dict:
    out = run_cmd(["gh", "api", endpoint]).stdout
    return json.loads(out)


def gh_api_text(endpoint: str, accept: str) -> str:
    return run_cmd(["gh", "api", endpoint, "-H", f"Accept: {accept}"]).stdout


def parse_codex_template(path: Path) -> Tuple[Dict[str, str], List[str]]:
    text = path.read_text(encoding="utf-8")
    lines = [ln.rstrip() for ln in text.splitlines()]

    export_env: Dict[str, str] = {}
    for ln in lines:
        stripped = ln.strip()
        if stripped.startswith("export ") and "=" in stripped:
            # Supports export KEY=value syntax.
            _, body = stripped.split("export ", 1)
            key, val = body.split("=", 1)
            export_env[key.strip()] = val.strip().strip('"').strip("'")

    cmd_start = None
    for i, ln in enumerate(lines):
        if "codex exec" in ln:
            cmd_start = i
            break
    if cmd_start is None:
        raise ValueError(f"No 'codex exec' command found in {path}.")

    merged = []
    for ln in lines[cmd_start:]:
        stripped = ln.strip()
        if not stripped:
            continue
        if stripped.endswith("\\"):
            merged.append(stripped[:-1].strip())
        else:
            merged.append(stripped)
            break

    cmd_str = " ".join(merged)
    cmd_tokens = shlex.split(cmd_str)
    if len(cmd_tokens) < 2 or cmd_tokens[0] != "codex" or cmd_tokens[1] != "exec":
        raise ValueError(f"Failed to parse codex command: {cmd_str}")

    # Templates usually end with a placeholder prompt (e.g. "hello").
    # Replace that placeholder with the generated prompt.
    if cmd_tokens and not cmd_tokens[-1].startswith("-"):
        cmd_tokens = cmd_tokens[:-1]
    return export_env, cmd_tokens


def build_prompt(template: str, issue: dict, pr: dict) -> str:
    issue_title = issue.get("title", "")
    issue_body = issue.get("body", "") or "(empty)"
    pr_title = pr.get("title", "")
    pr_body = pr.get("body", "") or "(empty)"
    pr_url = pr.get("html_url", "")

    return (
        f"{template.strip()}\n\n"
        "## 3) Context from GitHub\n\n"
        f"### Issue: {issue_title}\n\n"
        f"{issue_body}\n\n"
        f"### PR: {pr_title}\n\n"
        f"{pr_body}\n\n"
        f"PR URL: {pr_url}\n"
    )


def parse_changed_paths(repo_dir: Path) -> Set[Path]:
    """
    Parse paths from `git status --porcelain` and return changed/untracked files.
    """
    status = run_cmd(["git", "status", "--porcelain"], cwd=repo_dir).stdout
    changed: Set[Path] = set()
    for raw in status.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        payload = line[3:] if len(line) > 3 else ""
        if " -> " in payload:
            payload = payload.split(" -> ", 1)[1]
        rel_path = Path(payload.strip())
        if rel_path:
            changed.add(rel_path)
    return changed


def collect_special_files(repo_dir: Path) -> Set[Path]:
    """
    Keep Docker and test artifacts even if users want a minimal final package.
    """
    keep: Set[Path] = set()
    for p in repo_dir.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(repo_dir)
        name = p.name
        lower = name.lower()
        if name == "Dockerfile" or name.startswith("Dockerfile."):
            keep.add(rel)
            continue
        if lower.startswith("test") and p.suffix == ".py":
            keep.add(rel)
            continue
        if rel.parts and rel.parts[0] == "tests" and p.suffix == ".py":
            keep.add(rel)
    return keep


def copy_repo_files(repo_dir: Path, rel_paths: Set[Path], dest_dir: Path) -> None:
    dest_dir.mkdir(parents=True, exist_ok=True)
    for rel in sorted(rel_paths):
        src = repo_dir / rel
        if not src.exists() or not src.is_file():
            continue
        dst = dest_dir / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def create_checker_bundle(
    export_dir: Path,
    issue: dict,
    pr: dict,
    patch_text: str,
) -> Dict[str, str]:
    """
    Create a SWEGENT-like bundle layout that can be consumed directly by
    f2p_from_swegent_bundle.py.
    """
    bundle_dir = export_dir / "bundle"
    files_dir = export_dir / "files"
    bundle_dir.mkdir(parents=True, exist_ok=True)

    issue_number = int(issue.get("number"))
    issue_url = issue.get("html_url") or issue.get("url") or ""
    base_sha = pr.get("base", {}).get("sha", "")
    head_sha = pr.get("head", {}).get("sha", "")

    bundle_issue = {
        "number": issue_number,
        "url": issue_url,
        "linked_prs": [
            {
                "base_sha": base_sha,
                "head_sha": head_sha,
                "patch": patch_text,
            }
        ],
    }
    issue_json_path = bundle_dir / f"issue_{issue_number}.json"
    issue_json_path.write_text(
        json.dumps(bundle_issue, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    docker_src = files_dir / "Dockerfile"
    docker_dst = bundle_dir / "codex.dockerfile"
    docker_root_dst = export_dir / "codex.dockerfile"
    if docker_src.exists() and docker_src.is_file():
        shutil.copy2(docker_src, docker_dst)
        shutil.copy2(docker_src, docker_root_dst)

    copied_tests = 0
    # Recursively collect test*.py under files/, then flatten into bundle and export root.
    seen_names: Set[str] = set()
    for test_file in sorted(files_dir.rglob("test*.py")):
        if not test_file.is_file():
            continue
        name = test_file.name
        if name in seen_names:
            continue
        seen_names.add(name)
        shutil.copy2(test_file, bundle_dir / name)
        shutil.copy2(test_file, export_dir / name)
        copied_tests += 1

    # Also place issue_<n>.json at export root for direct checker input.
    issue_root_path = export_dir / f"issue_{issue_number}.json"
    shutil.copy2(issue_json_path, issue_root_path)

    return {
        "bundle_dir": str(bundle_dir),
        "bundle_issue_json": str(issue_json_path),
        "bundle_dockerfile": str(docker_dst) if docker_dst.exists() else "",
        "bundle_test_count": str(copied_tests),
        "root_issue_json": str(issue_root_path),
        "root_dockerfile": str(docker_root_dst) if docker_root_dst.exists() else "",
        "root_test_count": str(copied_tests),
    }


def copy_f2p_checker_files(src_files: List[Path], baseline_dir: Path) -> List[Path]:
    """
    Copy reusable F2P checker assets into Baseline/f2p_checker.
    Returns copied destination paths.
    """
    dst_dir = baseline_dir / "f2p_checker"
    dst_dir.mkdir(parents=True, exist_ok=True)
    copied: List[Path] = []
    for src in src_files:
        if not src.exists() or not src.is_file():
            continue
        dst = dst_dir / src.name
        shutil.copy2(src, dst)
        copied.append(dst)
    return copied


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Batch-fetch repo issues/PRs and run Codex in each repo's Baseline."
    )
    parser.add_argument(
        "--map-file",
        default=str(Path(__file__).with_name("issue_pr_map.json")),
        help="Path to issue_pr_map.json",
    )
    parser.add_argument(
        "--prompt-file",
        default=str(Path(__file__).with_name("prompt.md")),
        help="Path to the prompt template file",
    )
    parser.add_argument(
        "--codex-template",
        default=str(Path(__file__).with_name("codex")),
        help="Path to codex command template file (contains codex exec ...)",
    )
    parser.add_argument(
        "--repos-root",
        default=os.getcwd(),
        help="Root directory for repos (missing repos will be cloned here)",
    )
    parser.add_argument(
        "--baseline-dir-name",
        default="Baseline",
        help="Baseline directory name inside each repo",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate files only; do not invoke codex",
    )
    parser.add_argument(
        "--result-root",
        default=os.path.join(os.getcwd(), "results"),
        help="Root path for exported outputs at reponame/issuenumber",
    )
    parser.add_argument(
        "--f2p-checker-files",
        nargs="*",
        default=[
            "/home/cc/swe-factory/scripts/f2p_from_swegent_bundle.py",
            "/home/cc/swe-factory/scripts/f2p_from_swegent_bundle.md",
        ],
        help="Optional reusable F2P checker files to copy into Baseline/f2p_checker",
    )
    args = parser.parse_args()

    if shutil.which("gh") is None:
        raise RuntimeError(
            "Missing required dependency: 'gh' (GitHub CLI).\n"
            "Install it first, then run: gh auth login"
        )

    if shutil.which("codex") is None and not args.dry_run:
        raise RuntimeError(
            "Missing required dependency: 'codex'. Install it first (e.g. npm install -g @openai/codex)."
        )

    map_file = Path(args.map_file).expanduser().resolve()
    prompt_file = Path(args.prompt_file).expanduser().resolve()
    codex_template = Path(args.codex_template).expanduser().resolve()
    repos_root = Path(args.repos_root).expanduser().resolve()
    result_root = Path(args.result_root).expanduser().resolve()
    f2p_checker_files = [Path(p).expanduser().resolve() for p in args.f2p_checker_files]
    repos_root.mkdir(parents=True, exist_ok=True)
    result_root.mkdir(parents=True, exist_ok=True)

    items = load_map(map_file)
    prompt_template = prompt_file.read_text(encoding="utf-8")
    exported_env, codex_base_cmd = parse_codex_template(codex_template)

    base_env = os.environ.copy()
    base_env.update(exported_env)

    for idx, item in enumerate(items, start=1):
        repo = item["repo"]
        issue_number = int(item["issue_number"])
        pr_number = int(item["pr_number"])
        print(f"[{idx}/{len(items)}] Processing {repo} issue#{issue_number} pr#{pr_number}")

        repo_dir, cloned_now = ensure_repo(repo, repos_root)
        baseline_dir = repo_dir / args.baseline_dir_name
        baseline_dir.mkdir(parents=True, exist_ok=True)
        copied_checker_paths = copy_f2p_checker_files(f2p_checker_files, baseline_dir)

        issue = gh_api_json(f"repos/{repo}/issues/{issue_number}")
        pr = gh_api_json(f"repos/{repo}/pulls/{pr_number}")
        patch_text = gh_api_text(
            f"repos/{repo}/pulls/{pr_number}",
            "application/vnd.github.v3.patch",
        )

        (baseline_dir / "issue.json").write_text(
            json.dumps(issue, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (baseline_dir / "pr.json").write_text(
            json.dumps(pr, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        (baseline_dir / f"pr_{pr_number}.patch").write_text(patch_text, encoding="utf-8")

        issue_body = issue.get("body", "") or ""
        (baseline_dir / f"issue_{issue_number}.md").write_text(issue_body, encoding="utf-8")

        codex_prompt = build_prompt(prompt_template, issue, pr)
        codex_prompt_file = baseline_dir / f"codex_prompt_{issue_number}.md"
        codex_prompt_file.write_text(codex_prompt, encoding="utf-8")

        if args.dry_run:
            print(f"  - dry-run: generated files in {baseline_dir}")
            continue

        cmd = codex_base_cmd + [codex_prompt]
        print(f"  - running codex in {repo_dir} ...")
        run_cmd(cmd, cwd=repo_dir, env=base_env, capture_output=False)

        repo_name = repo.split("/")[-1]
        export_dir = result_root / repo_name / str(issue_number)
        meta_dir = export_dir / "metadata"
        files_dir = export_dir / "files"
        meta_dir.mkdir(parents=True, exist_ok=True)

        # Export collected GitHub metadata/context.
        shutil.copy2(baseline_dir / "issue.json", meta_dir / "issue.json")
        shutil.copy2(baseline_dir / "pr.json", meta_dir / "pr.json")
        shutil.copy2(baseline_dir / f"pr_{pr_number}.patch", meta_dir / f"pr_{pr_number}.patch")
        shutil.copy2(baseline_dir / f"issue_{issue_number}.md", meta_dir / f"issue_{issue_number}.md")
        shutil.copy2(codex_prompt_file, meta_dir / codex_prompt_file.name)
        if copied_checker_paths:
            checker_export_dir = meta_dir / "f2p_checker"
            checker_export_dir.mkdir(parents=True, exist_ok=True)
            for p in copied_checker_paths:
                shutil.copy2(p, checker_export_dir / p.name)

        # Keep agent outputs + Docker/Test artifacts in final package.
        changed_paths = parse_changed_paths(repo_dir)
        keep_paths = changed_paths | collect_special_files(repo_dir)
        copy_repo_files(repo_dir, keep_paths, files_dir)

        summary = {
            "repo": repo,
            "issue_number": issue_number,
            "pr_number": pr_number,
            "export_dir": str(export_dir),
            "changed_files_count": len(changed_paths),
            "kept_files_count": len(keep_paths),
            "repo_removed": cloned_now,
            "f2p_checker_files": [str(p) for p in copied_checker_paths],
        }

        # Generate checker-ready bundle (issue_*.json + *.dockerfile + test*.py).
        summary.update(create_checker_bundle(export_dir, issue, pr, patch_text))

        (export_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Remove original cloned repo to keep only exported minimal artifacts.
        if cloned_now:
            shutil.rmtree(repo_dir)
            print(f"  - exported to {export_dir} and removed cloned repo")
        else:
            print(
                f"  - exported to {export_dir}; repo kept because it existed before this run"
            )

    print("All repositories processed.")


if __name__ == "__main__":
    main()
