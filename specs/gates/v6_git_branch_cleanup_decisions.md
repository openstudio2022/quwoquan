# V6 (S5) Git 历史残留分支清理裁决记录

关联：`specs/changelog/CR-20260531-028-v6-arch-source-unify-growth-closure.yaml`（S5）。

执行口径：用户选择 **local_only** —— 本地 worktree / 分支清理本会话执行；**远程分支删除待人工确认后执行**，本文逐条记录裁决理由。终态目标：只保留 `dev1.0` + `main`。

## 已执行（本地，local_only）

| 对象 | 状态 | 处理 |
| --- | --- | --- |
| worktree `quwoquan-auth-dev10-publish-20260530` | 提交 `b5bd8bfb`（auth 登录/路由/会话收口）**已在 origin/dev1.0**（本地 dev1.0 behind 1 即此提交） | 已 `git worktree remove` + `git branch -D commit/auth-dev10-publish-20260530`，无数据丢失 |

本地终态：仅 `dev1.0` + `session6-arch-growth-closure`（V6 集成分支，终态合回 dev1.0 后删）。

## 远程分支裁决（待人工执行 `git push origin --delete <branch>`）

### A 类：已完全并入（ahead vs origin/dev1.0 = 0 且 in origin/main）→ 建议直接删

| 远程分支 | ahead | 在 main | 裁决 |
| --- | --- | --- | --- |
| `origin/dev1.1` | 0 | 是 | 删（已并入 dev1.0 + main） |
| `origin/feat/openspec-integration-and-figma-migration` | 0 | 是 | 删（已并入） |
| `origin/fix/kustomize-install-flake` | 0 | 是 | 删（已并入） |
| `origin/merge-dev10-to-main-20260502151414` | 0 | 是 | 删（历史 merge 分支，已并入） |

### B 类：有未合并提交（ahead > 0）→ 逐条裁决

| 远程分支 | ahead | 内容性质 | 最后提交 | 裁决 |
| --- | --- | --- | --- | --- |
| `origin/fix/assistant-ios-matrix-timeout` | 1 | 纯 CI：放宽 beta/gamma iOS 设备矩阵 flutter test 超时 | 2026-05-07 | 删（CI 调优，3 周前，dev1.0 CI 已演进） |
| `origin/validation/pr-gate-timing-20260507` | 1 | 纯 CI：allow single-platform self-hosted device matrix | 2026-05-07 | 删（CI 调优，已过时） |
| `origin/fix/gamma-main-gate-pr` | 7 | 纯 CI/门禁：gamma 主门禁链收口、设备矩阵 artifact 路径、self-hosted 证据上传重试等 | 2026-05-05 | 删（全部 CI 调优，dev1.0 门禁链已大幅演进，无业务代码） |
| `origin/fix/08-allow-missing-platforms` | 5 | 4 个 CI 调优 + **1 个实质修复** `5d40c6f7 fix(user-service): restore privacy contract round-trip`（user_settings blocked_keywords / 隐私契约 round-trip，触及 setting_service.go / migration 014 / privacy_contract_test.go） | 2026-05-08 | **人工核对**：先确认 dev1.0 是否已独立实现 blocked_keywords 隐私设置；若缺 → cherry-pick `5d40c6f7` 进 dev1.0；CI 4 提交删。核对后删分支 |

## 人工执行清单（确认后）

```bash
# A 类 + B 类已裁决为删的，逐条删除远程分支：
git push origin --delete dev1.1
git push origin --delete feat/openspec-integration-and-figma-migration
git push origin --delete fix/kustomize-install-flake
git push origin --delete merge-dev10-to-main-20260502151414
git push origin --delete fix/assistant-ios-matrix-timeout
git push origin --delete validation/pr-gate-timing-20260507
git push origin --delete fix/gamma-main-gate-pr

# fix/08：先核对 privacy 修复
git merge-base --is-ancestor 5d40c6f7 origin/dev1.0   # 若非 0 即未含
# 若 dev1.0 缺该隐私修复，cherry-pick 后再删：
# git checkout dev1.0 && git cherry-pick 5d40c6f7
git push origin --delete fix/08-allow-missing-platforms
```

`origin/main` 不动。终态仅 `dev1.0` + `main`。

## V7 人工核对与实删执行记录（2026-05-31）

### fix/08 隐私修复人工核对结论：**无需 cherry-pick**

核对 `5d40c6f7 fix(user-service): restore privacy contract round-trip` 是否需进 dev1.0：

- `git merge-base --is-ancestor 5d40c6f7 origin/dev1.0` → 1（该具体提交不在 dev1.0）。
- 但 **dev1.0 已独立且更完整实现** blocked_keywords 隐私契约 round-trip：
  - `setting_service.go:77-78`：`normalizeStringList(data["blockedKeywords"])` → `st.BlockedKeywords = blocked`（round-trip 代码已在）。
  - `tests/settings_contract_test.go:9 TestPrivacySettings_BlockedKeywordsRoundTrip`：覆盖 PATCH/GET round-trip + 归一化（`["alpha"," beta ","alpha"]`→`[alpha beta]`）+ `profileVisibility`，等价并超越 fix/08 的 `privacy_contract_test.go`。
  - blocked_keywords schema 整合进 `005_user_settings.up.sql`；dev1.0 的 `014_*` slot 已被 `014_greeting_requests.up.sql` 占用。
- 结论：cherry-pick 5d40c6f7 会造成 **migration 014 冲突** 并回退到陈旧重复实现，**判定不 cherry-pick**；隐私修复意图在 dev1.0 已闭环。fix/08 直接删。

### 待删分支 tip SHA（可恢复记录）

| 分支 | tip | 类 |
| --- | --- | --- |
| `dev1.1` | `ede1944f` | A |
| `feat/openspec-integration-and-figma-migration` | `32d19cac` | A |
| `fix/kustomize-install-flake` | `5fd91deb` | A |
| `merge-dev10-to-main-20260502151414` | `82978a52` | A |
| `validation/pr-gate-timing-20260507` | `ad9869e3` | B |
| `fix/gamma-main-gate-pr` | `d142343a` | B |
| `fix/08-allow-missing-platforms` | `5d40c6f7` | B（隐私已在 dev1.0） |
| `fix/assistant-ios-matrix-timeout` | （fetch --prune 时已不在远程，先前已删） | B |

### 实删结果（2026-05-31，V7）

7 个分支 `git push origin --delete` 全部 rc=0 成功删除；`fix/assistant-ios-matrix-timeout` 此前已删。`git fetch --prune` 后 `git ls-remote --heads origin` 终态：

```
refs/heads/dev1.0
refs/heads/main
```

**远程终态达成：仅 `dev1.0` + `main`。** `origin/main`、`origin/dev1.0` 未改动。
