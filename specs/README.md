# 全局规范导航（端云一体化）

---

## Agent 入口

| 文件 | 说明 |
|------|------|
| **`../AGENTS.md`** | Agent 执行入口，索引主线、阶段路由与仓库级约束 |
| **`00_AGENT_MASTER_SPEC.md`** | Agent 规格导航，链接 D0/F1 与 metadata 权威文档 |
| **`00_MASTER_DEVELOPMENT_FLOW.md`** | 唯一主线：5 阶段 × 自动卡点 + 命令 + 约束 + 扩展场景 |

---

## 产品基线与术语

| 文件 | 说明 |
|------|------|
| **`00_PRODUCT_CONCEPT_SYSTEM.md`** | 全 App 产品概念基线：品牌定位、身份、主页、群组、群、内容、会话、小趣与跨域对象关系 |
| **`00_GLOBAL_TERMINOLOGY.md`** | 全局术语与命名规则：用户语言、PRD 语言、技术语言、禁用词与旧词迁移映射 |

---

## Runtime 规范

| 文件 | 说明 |
|------|------|
| `feature-tree/runtime/system-architecture-and-engineering-guide/design.md` | D0 业务对象、F1 ContractGraph 与 G1 门禁的架构权威 |
| `feature-tree/runtime/system-architecture-and-engineering-guide/acceptance.yaml` | D0/F1/G1 准出状态与测试证据权威 |
| `../quwoquan_service/contracts/metadata/DESIGN.md` | metadata、Object Facade/Data Ports 与 compiler 合同权威 |
| `runtime_extension_catalog.md` | 当前端云扩展执行目录；只链接权威设计，不定义第二套架构 |

---

## 特性树与索引

| 文件 | 说明 |
|------|------|
| `feature-tree/` | 一棵树（`AppRoot -> L1_domain_service -> L2_business_capability -> L3_story`） |
| `feature-tree/tree_index.yaml` | L1 机器可读索引 |
| `changelog/` | 增量变更流（`CR-YYYYMMDD-NNN-<slug>.yaml`），不嵌入特性树节点目录 |
| `plans/` | 跨节点或长周期实施计划；由对应 L3 `spec.md` 与 CR 显式引用，不成为特性树节点文档 |
| `l1_index.yaml` | L1 目录与服务映射 |
| `engineering_directory_manifest.yaml` | 机读约束与 verify 规则 |

---

## 云侧规范

| 入口 | 说明 |
|------|------|
| `quwoquan_service/contracts/metadata/DESIGN.md` | 业务对象元数据、ContractGraph 与 Object Facade/Data Ports 设计总览 |
| `specs/feature-tree/` + `quwoquan_service/contracts/metadata/` | 各服务 API、领域边界与验收真相源 |
| `feature-tree/runtime/system-architecture-and-engineering-guide/` | 云侧服务目录、部署进程、工程导引与 one-box 组网权威入口 |
| `quwoquan_service/README.md` | 当前服务域目录职责索引 |

---

## 端侧规范

| 入口 | 说明 |
|------|------|
| `02_IOS_NATIVE_FRONTEND_UX_SPEC.md` | iOS 原生前端 UX 规范（作者主页、沉浸式浏览器、创作编辑、post、导航、tab、sheet，含组件级响应式清单与门禁） |
| `.cursor/rules/` + `quwoquan_app/AGENTS.md` | App 编码、设计、测试、状态管理和语义审计的唯一规则入口 |

---

## 特性交付

| 入口 | 说明 |
|------|------|
| `specs/feature-tree/tree_index.yaml` | 特性树结构索引唯一真相源 |
| `specs/feature-tree/<l1>/<l2>/` | Journey 节点三件套（`spec/design/acceptance`）；Scenario 节点两件套（`spec/acceptance`） |
| `specs/plans/*.yaml` | 长周期实施计划唯一真相源 |
| `specs/changelog/CR-*.yaml` | 增量变更台账与 revision 真相源 |
