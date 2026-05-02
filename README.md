# 趣我圈 (QuWoQuan) 项目

趣我圈是一个社交内容应用项目，包含多个子模块。

## 项目结构

```
quwoquan/
├── specs/                 # 全栈规范入口（Agent 入口、特性树、契约索引、端云协同）
├── changes/               # 全量特性目录（特性台账 + 特性实例）
├── scripts/               # 全栈自动化脚本（gate/verify/模板）
├── .cursor/               # 全栈 AI 规则与命令
├── openspec/              # OpenSpec 能力规格与变更（从根目录运行，不依赖子模块）
├── quwoquan_app/          # Flutter 端侧（子模块）
│   ├── .cursor/           #   端侧 AI 规则/命令/skills
│   └── current/            #   归档文档（仅参考）
├── quwoquan_service/      # Go 云侧
│   ├── contracts/         #   端云契约（metadata + OpenAPI + 领域契约）
│   ├── runtime/           #   公共运行时（横切能力统一实现）
│   ├── specs/             #   各服务 API 规格
│   └── platform/          #   可观测/配置平台
└── Makefile               # verify + gate 入口
```

## 规范导航

- **全局入口**：`specs/README.md`
- **Agent 入口**：`specs/00_AGENT_MASTER_SPEC.md`
- **唯一主线**：`specs/00_MASTER_DEVELOPMENT_FLOW.md`
- **产品概念基线**：`specs/00_PRODUCT_CONCEPT_SYSTEM.md`（品牌定位、身份、主页、群组、群、内容、会话、小趣与跨域对象关系）
- **全局术语表**：`specs/00_GLOBAL_TERMINOLOGY.md`（用户语言、PRD 语言、技术语言、禁用词与旧词迁移映射）
- **业务对象设计**：`quwoquan_service/contracts/metadata/DESIGN.md`

## 端云一体化交付（特性粒度）

本仓库以**特性粒度**推进标准主链路：

```text
/explore → /prd → /design → /dev → /commit → /deploy
```

其中：
- `/dev` 负责按 TDD 实施、完成 `T1~T4` 四层自验证、完成 `gray-release ready` 检查，并自动归档
- `/commit` 读取 `/dev` 自动归档结果后执行提交
- `/archive` 仅作兼容补归档入口，标准流通常不单独使用
- `/try → /land` 保留原型链路与基线化/归档语义

- **创建特性目录（Ask/Plan 输出落盘）**：

```bash
bash scripts/new_feature_fullstack.sh "<slug>"
```

- **正式命令入口（Cursor 命令，统一在根目录）**：
  - `/explore`、`/prd`、`/design`
  - `/dev`、`/deliver`、`/commit`、`/deploy`
  - `/verify`、`/audit`
  - `/try`、`/land`
  - `/extend`、`/prune`

特性目录位于：`specs/feature-tree/<l1-capability>/<l2-story>/`。
特性树索引位于：`specs/feature-tree/tree_index.yaml`。
全量变更台账仍位于：`changes/feature_catalog.yaml`。

全局规范入口：`specs/README.md`。

## 开发指南

### 统一质量门禁（禁止不遵从变更合入）

- **快速门禁（本地必过）**：

```bash
make gate
```

- **全量门禁（包含端侧测试；CI/合入必需）**：

```bash
make gate-full
```

- **特性与元数据一致性检查（可单独执行）**：

```bash
bash scripts/verify_feature_traceability.sh
bash scripts/verify_contract_metadata.sh
bash scripts/verify_specs_l1_hierarchy.sh
bash scripts/verify_feature_tree_refactor.sh
```

### 安装本地提交阻断（可选）

安装 pre-commit hook：当 staged 变更涉及 `quwoquan_app/` 或 `quwoquan_service/` 时自动运行门禁。

```bash
bash scripts/install-hooks.sh
```

### 初始化子模块

如果是首次克隆此仓库，需要初始化子模块：

```bash
git submodule update --init --recursive
```

### 更新子模块

```bash
git submodule update --remote
```

### 在子模块中工作

```bash
cd quwoquan_app
# 进行开发工作
git add .
git commit -m "Your commit message"
git push
```

然后回到主仓库提交子模块的更新：

```bash
cd ..
git add quwoquan_app
git commit -m "Update quwoquan_app submodule"
git push
```

## Git 配置

本项目使用 SSH 密钥进行 GitHub 认证。SSH 密钥已配置在 `~/.ssh/id_ed25519_quwoquan`。

## 贡献指南

1. 在主仓库创建功能分支
2. 在相应的子模块中进行开发
3. 提交子模块更改
4. 在主仓库中更新子模块引用
5. 提交并推送主仓库更改

