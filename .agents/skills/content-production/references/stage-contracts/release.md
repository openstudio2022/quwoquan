# 阶段契约：release

从 canonical 构建 immutable release。

## 身份

- stage：`release`（与磁盘目录一字不差）
- 前置阶段：`publish`
- 合法 next：`ship`
- 角色人设：[release-operator](../roles/release-operator.md)
- 写目录 allowlist：`.qwq_output/data/releases/<releaseId>/`（只经 release 命令）

## 做前（PRE）

- `publish` receipt `verdict=pass`；复跑：

```bash
python3 quwoquan_data/scripts/cli.py verify publish-purity
python3 quwoquan_data/scripts/cli.py verify publish-closure
```

## 做中（DURING）

- 唯一 CLI：`python3 quwoquan_data/scripts/cli.py release pool-build
  --release-class research|commercial …` 产出 immutable release；
  release class 语义见 `runtime-data-engineering` REQ-002。
- [MUST NOT] 事后修改 release payload；[MUST NOT] 建立第二发布身份。

## 做后（POST）

交付件：`.qwq_output/data/releases/<releaseId>/`（desired state + payload +
attestations）。完成判据：

```bash
python3 quwoquan_data/scripts/cli.py verify release-integrity --release <releaseId>
python3 quwoquan_data/scripts/cli.py verify media-release-contract
```

常见 issue → 修复：

- 引用闭包缺对象 → 回 `publish` 补齐 canonical（该对象重走 readiness），
  再重新 build；不改已产出 release。
- attestation/digest 不一致 → 废弃该 releaseId 重新 build，不原地修文件。

按 [handoff-protocol.md](../handoff-protocol.md) 执行 `task stage-open` → `task stage-gate` → `task stage-close`；宿主不填写 command 退出码、verdict 或 next。

## 交接（HANDOFF）

- gate context 结构化绑定 `releaseId` 与 `releaseDigest`，machine gate receipt 冻结 exact identity；release close 重验 receipt `authority.releaseBinding` 就是本次 machine gate 的 releaseBinding。
- `next=ship`。
