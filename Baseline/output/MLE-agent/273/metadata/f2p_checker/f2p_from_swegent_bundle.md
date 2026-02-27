# 用 SWEGENT bundle 做 Fail2Pass（F2P）单例验证

这个脚本用于把 SWEGENT 生成的单个 issue bundle（`issue_*.json` + `test*.py` + `*.dockerfile`）跑一遍 **Fail2Pass**：

- **before**：在 `base_sha` 上跑 bundle 的测试
- **after**：在 `base_sha` 上应用 `patch` 后再跑同一套测试
- 输出分类：`fail2pass / fail2fail / pass2pass / pass2fail / error`

脚本位置：`scripts/f2p_from_swegent_bundle.py`

## 目录结构要求

bundle 目录需要包含至少：

- `issue_*.json`（从中读取 repo、base_sha、patch）
- `test*.py`（要跑的测试脚本）
- `*.dockerfile`（用于构建可复现环境的 Dockerfile）

## 使用示例（issue_256）

假设你已经把 zip 解压到：

`/home/cc/issue_256-20260224T063439Z-1-001/issue_256/`

直接运行：

```bash
python /home/cc/swe-factory/scripts/f2p_from_swegent_bundle.py \
  /home/cc/issue_256-20260224T063439Z-1-001/issue_256
```

运行结束会输出类似：

- `[F2P] fail2pass`
- `Report: /home/cc/swe-factory/run_instances/swegent_f2p/<run_id>/f2p_report.json`

报告目录下还会有：

- `pytest_before.stdout.txt / pytest_before.stderr.txt`
- `pytest_after.stdout.txt / pytest_after.stderr.txt`
- `docker_build_before.* / docker_build_after.*`
- `git_apply_patch.*`（after 侧应用 patch 的日志）

## 安全注意事项

有些 bundle 附带的 `*.dockerfile` 里可能硬编码了 API key（例如 `ENV FORGE_API_KEY=...`）。
建议在跑之前**删掉或替换**这些敏感行，避免密钥进入镜像层或日志。

