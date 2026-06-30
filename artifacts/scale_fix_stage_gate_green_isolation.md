# Phase A 收口:verify_quwoquan_data.sh 绿(隔离根 sampling manifest 漂移修复)

## 结论

`bash quwoquan_data/scripts/verify/verify_quwoquan_data.sh` → **VERIFY_EXIT=0(PASSED)**
(log: artifacts/_verify_data_run.log,末行 `[verify-quwoquan-data] PASSED`)。

含:RC 全套契约、三类路由、图库许可、翻译门、内联图 lazy 抽取、agent executor 契约、
fanout_runner(26)、template lint 系列、creator match、ship 采样、`verify --scope current` 全过。

## 本阶段修复的真实 bug:ship sampling manifest 在隔离根下路径漂移

### 现象

启用 E2E 沙箱 env(`QWQ_DATA_ROOT=~/qwq_scale_verify`)后,门禁 `ship` 步 `FileNotFoundError:
/Users/zhaoyuxi/deploy/shared/content_sampling_manifest.yaml`(漏了 `Projects/quwoquan`)。

### 根因

`quwoquan_data/scripts/ship/sampler.py` 用 `SAMPLING_MANIFEST = DATA_ROOT.parent / "deploy"/...`,
而 `DATA_ROOT` 来自 env-driven `_common.paths.DATA_ROOT`。隔离/沙箱下 `DATA_ROOT.parent` 漂移到
`$HOME`,丢失受版本控制的跨工程契约 `deploy/shared/content_sampling_manifest.yaml`(git-tracked)。
这正是 `_common/paths.py` 注释明令禁止的反模式:"禁止用 DATA_ROOT.parent 推导（隔离根下会漂移）"。

### 修复

`SAMPLING_MANIFEST = REPO_ROOT / "deploy"/"shared"/"content_sampling_manifest.yaml"`,改用
code-anchored 的 `_common.paths.REPO_ROOT`(由 `__file__` 派生,不随运行时数据根漂移)。
验证:沙箱 env 下 `SAMPLING_MANIFEST` 正确解析到仓库 `deploy/shared/...` 且 exists=True。

### 同类排查(已确认无需改)

- `task/handler.py`、`task/scaled_e2e.py`、`_common/python_runtime.py` 的 `REPO_ROOT = DATA_ROOT.parent`
  其 `DATA_ROOT` 均来自 `__file__`(code-anchored),隔离下已正确,**不动**。
- `produce/materialize.py` / `_common/post_evidence_chain.py` 的 `DATA_ROOT.parent / normalized` 是
  legacy `quwoquan_data/runtime/` 前缀的 best-effort 候选解析(带 try/except + `RUNTIME_ROOT` 兜底),
  非门禁阻断,改动风险更高,**本轮不动**,记为低优 finding。

## 沙箱状态收口(非 git)

`~/qwq_scale_verify/tasks/.../四川景点fresh scale100/task.yaml` 缺 `content.angles` 致 `task lint` FAIL;
该任务在 scale-verify 沙箱(非仓库),补回 `angles:[体验,美图,攻略]`(与垂类菜单一致),使沙箱 lint 干净。
仓库 `quwoquan_data/tasks/` 本身 lint OK(已单独验证)。
