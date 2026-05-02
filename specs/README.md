# 全局规范导航（端云一体化）

---

## Agent 入口

| 文件 | 说明 |
|------|------|
| **`00_AGENT_MASTER_SPEC.md`** | AI Agent 主导开发入口，索引主线与开发计划 |
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
| `runtime_framework_spec.md` | DDD + 元数据驱动运行时框架规范 |
| `runtime_framework_design.md` | 运行时框架技术选型与完整设计 |
| `RUNTIME_DEVELOPMENT_PLAN.md` | Runtime 商用准出开发计划（P0-fix → P0 → P1 → P2 → P3） |
| `runtime_gap_analysis_and_plan.md` | Runtime Gap 全景分析与详细开发任务 |
| `runtime_extension_catalog.md` | 20 个端云扩展场景详解（0→1 和 1→N） |

---

## 特性树与索引

| 文件 | 说明 |
|------|------|
| `feature-tree/` | 三层目录化特性树（`L1_capability -> L2_journey -> L3_scenario`） |
| `feature-tree/tree_index.yaml` | L1 机器可读索引 |
| `changelog/` | 增量变更流（`CR-YYYYMMDD-NNN-<slug>.yaml`），不嵌入特性树节点目录 |
| `l1_index.yaml` | L1 目录与服务映射 |
| `engineering_directory_manifest.yaml` | 机读约束与 verify 规则 |

---

## 云侧规范

| 入口 | 说明 |
|------|------|
| `quwoquan_service/contracts/metadata/DESIGN.md` | 业务对象元数据设计总览（5 聚合 + 7 实体 + 契约测试） |
| `quwoquan_service/specs/` | 各服务 API 与领域边界（11 个 service spec） |
| `quwoquan_service/design.md` | 云侧架构设计 |
| `quwoquan_service/tasks.md` | 云侧任务清单 |

---

## 端侧规范

| 入口 | 说明 |
|------|------|
| `02_IOS_NATIVE_FRONTEND_UX_SPEC.md` | iOS 原生前端 UX 规范（作者主页、沉浸式浏览器、创作编辑、post、导航、tab、sheet，含组件级响应式清单与门禁） |
| `quwoquan_app/.cursor/rules/` | App 编码/设计/测试/状态管理/语义审计 |
| `quwoquan_app/openspec/specs/` | App 能力规格（personal-assistant 等） |

---

## 特性交付

| 入口 | 说明 |
|------|------|
| `specs/feature-tree/tree_index.yaml` | 特性树结构索引唯一真相源 |
| `specs/feature-tree/<l1>/<l2>/` | Journey / Scenario 节点四件套（`spec/design/plan/acceptance`） |
| `specs/changelog/CR-*.yaml` | 增量变更台账与 revision 真相源 |
| `changes/README.md` | 记录变更体系，迁移期仅供参考 |
