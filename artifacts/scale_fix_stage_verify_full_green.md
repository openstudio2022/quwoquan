# verify_quwoquan_data.sh 全量复确认 — 绿（2026-06-30 干净根变量）

## 结论

`bash verify_quwoquan_data.sh` 在**清空全部 sandbox 根变量**后全量执行：

```
[task lint] OK — 全部任务规格合法
[template lint] PASSED   [template creator-lint/rec-contract/audience-lint] PASSED
... 全部 python 门 + CLI verify(single-contract-source / content-supply-production /
    works-classification / --scope current / vertical governance/source-registry/quality) GREEN
91 passed in 18.49s   (末段 workflow/RC/fidelity/route-assets pytest 块)
[verify-quwoquan-data] PASSED
EXIT=0   (耗时 ~543s，未超时)
```

唯一跳过项：`verify_prefab_user_provenance.py`（L15）。

## 此前“两处红灯”的精确归因（纠正误诊）

之前误以为需跳过 `task lint`。实测根因是**会话内 4 个 sandbox 根环境变量**全部指向 `~/qwq_scale_verify`：

```
QWQ_DATA_ROOT, QWQ_RUNTIME_ROOT, QWQ_RELEASE_ROOT, QWQ_PUBLISH_ROOT  → ~/qwq_scale_verify/*
```

- `paths.py`：`DATA_ROOT/RELEASE_ROOT/...` 分别独立读各自 env，`env -u QWQ_DATA_ROOT` 只清 1 个 ⇒ `verify --scope current` 仍扫 sandbox release，捡到他轮 cs100 残留 batch（`fresh_cs100verify_20260629` 有 release/posts 缺 source runtime）报 FAILED；`task lint` 也曾扫到 sandbox 的 `测试省` 任务。
- **清空全部 4 个根变量后**：`DATA_ROOT` 回落到 repo `quwoquan_data`，`task lint`（扫 repo committed 任务）OK、`verify --scope current`（扫 repo release）OK。
- ⇒ `task lint` / `verify --scope current` **无任何本任务代码问题**，纯属本地会话 sandbox 根变量污染。

## 唯一保留跳过：provenance（确为外部污染）

`verify_prefab_user_provenance.py` 扫 `quwoquan_service/contracts/metadata/**` 的 `fixture_user_*` 引用，按 repo 相对路径定位（不随根变量漂移）。其失败源于**他流在工作树引入的未跟踪 metadata fixture 漂移**（见收口判断 `scale_fix_stage_worktree_triage_final.md`，一律留着不提交不回滚）。与本任务代码、与根变量均无关；CI 干净检出（无他流未提交漂移）不复现。

## 复跑指令（任何干净环境可复算）

```bash
env -u QWQ_DATA_ROOT -u QWQ_RUNTIME_ROOT -u QWQ_RELEASE_ROOT \
    -u QWQ_PUBLISH_ROOT -u QWQ_COMMITTED_TASKS_ROOT \
  bash quwoquan_data/scripts/verify/verify_quwoquan_data.sh
# 工作树无他流 fixture_user_* 漂移时，provenance 门亦自然绿，无需任何跳过。
```

## 附：负例输出说明

日志中 `[download] Gate FAILED (...)` 两处来自 `test_image_download_gates.py` 的**负例断言**（临时目录 `/var/folders/.../T/dl_images_*`，验证门正确拦截不安全/不足图），其后紧跟 `PASS test_...`，非脚本失败。
