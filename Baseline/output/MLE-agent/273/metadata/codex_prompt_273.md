This repository is an AI project that needs to be configured.

## 1) Environment Setup (Dockerfile)

### Goal
Create/configure a Dockerfile so the repository can run a standalone Python reproduction script.

### Critical Constraints
- DO NOT modify any source code files.
- DO NOT change any Python/JavaScript/other source files.
- Configure only the execution environment (Dockerfile and dependency setup).

### Base Image Selection (Very Important)
- Python projects: use `python:3.12-slim` or `python:3.11-slim` (strongly recommended).
- Node.js projects: use `node:20-slim` or `node:18-slim`.
- Python + Node.js: start from `python:3.12-slim` and install Node.js on top.
- Rust projects: use `rust:1.75-slim` or `rust:latest`.
- Avoid `debian:bullseye-slim` or `ubuntu` (more dependency issues).

### Project Type Detection
- `Cargo.toml` -> Rust project (`cargo build`, not `pip install`).
- `package.json` -> Node.js/TypeScript project.
- `requirements.txt` or `setup.py` -> Python project.
- `pyproject.toml` -> Python project (possibly Poetry).

### Environment Requirements for Standalone Script
- Ensure Python 3 is installed and available as `python` or `python3`.
- Install standard system dependencies needed for Python execution.
- Install repository dependencies (`requirements.txt` / Poetry / etc.) so imports work.
- The script is run directly (e.g., `python test128.py`), not via `pytest`/`unittest`.
- Ensure standard imports like `sys`, `os`, `json` (and `requests` if needed) work.

### Dockerfile Best Practices
1. File existence checks:
   - Check before operations; never assume files/directories exist.
2. PNPM global config:
   - If using `pnpm link --global`, set `PNPM_HOME` and include it in `PATH`.
3. Python package installation (PEP 668):
   - Prefer venv for Python 3.11+, or use a compatible install approach.
4. Compilation dependencies:
   - Install required system libs before compiling Python packages.
5. Poetry installation:
   - Install with `pipx` or `pip`, and ensure executable path is in `PATH`.
6. Rust projects:
   - Use Rust toolchain and `cargo build` workflow.
7. Path handling:
   - Use forward slashes in paths.
8. Network errors:
   - Add retry strategy/mirrors when package installation is unstable.

---

## 2) F2P Test Script (Standalone Reproduction)

You are tasked with creating a standalone Python reproduction script for an agent-related issue.

### Critical Requirements
1. Write a standalone script based on the issue description and provided patch.
2. **Directly import the class/function from the codebase**; do not re-implement it.
3. Do NOT use `unittest` and do NOT import `unittest.mock`.
4. Use plain `assert` statements.
5. Mock remote API calls (LLM providers / external services); do NOT make real API calls.
6. On buggy version: script should fail (AssertionError or non-zero exit).
7. On fixed version: script should pass (exit code 0).
8. **Must import `sys`** and **must end with `sys.exit(0)`** when all assertions pass.

### Script Structure
- Use normal Python functions or top-level code.
- Include `if __name__ == "__main__":`.

### Output Format
- Save as a Python file.
- Prefer `tests/` directory if it exists; otherwise save at repository root.
- Filename must be exactly: `test{issue_number}.py` (e.g., `test128.py`).
- Do not use variants like `test_issue_128.py` or `test_128.py`.
- The file must be created before finishing.

## 3) Context from GitHub

### Issue: LanceDB error when the first time setup a project

```
Traceback(most recent call last):

File "/Users/zachkoo/miniconda3/envs/mle/bin/mle", line 33, in <module>sys exit(load_entry_point('mle-
agent','console_scripts','mle')())File "/Users/zachkoo/miniconda3/envs/mle/bin/mle", line 25, in 
importlib_load_entry_pointo return next(matches).load()File 
"/Users/zachkoo/miniconda3/envs/mle/lib/python3.9/importlib/metadata.py", line 86, in loadmodule =import 
module(match.group("module'))File "/Users/zachkoo/miniconda3/envs/mle/lib/python3.9/importlib/_init_.py", line 127, in 
import_moduleYesreturn bootstrap._gcd_import(name[level:], package, level)File "<frozen importlib.sbootstrap>"line 
1030,in gcd importFile "<frozen importlib. bootstrap>"line 1007,in find_and loadline 986,in find_and load_unlockedFile,"
<frozenimportlib.. bootstrap>File "<frozen importlib. bootstrap>".line 680,in load unlocked.File "<frozen importlib..
 bootstrap_external>",line 850,in exec moduleFileg""<frozen importlib.bootstrap>",line 228,in 
call_with_frames_removedFile "/Users/zachkoo/Desktop/MLE-agent/mle/cli.py", line 26, in 
<module>memory=LanceDBMemory(os.getcwd())File "/Users/zachkoo/Desktop/MLE-agent/mle/utils/memory.py",line 23,in_init
if config["platform"]-*OpenAI":
TypeError:'NoneType'object is not subscriptable
```

### PR: [MRG] Fixed the memory init before config error

Closes #273 

PR URL: https://github.com/MLSysOps/MLE-agent/pull/274
