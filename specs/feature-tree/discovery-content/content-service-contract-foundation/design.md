# Design: content-service-contract-foundation

## 一、设计动因

### 当前痛点（0→1 起点，无历史包袱）

当前 contracts/metadata/ 存在以下结构性问题：

| 问题 | 现状 | 影响 |
|------|------|------|
| 投影与实体物理分离 | _projections/ 与 post/ 相隔两层 | 修改字段无法就近看到端侧影响 |
| 错误码孤岛 | error_codes.md 是文档，无机器读 | 端侧 CloudErrorMapper 永远返回 'REMOTE_ERROR' |
| 行为/特征/统计三处分散 | types.yaml + service.yaml + _projections/ | 添加新行为需改3处，易遗漏 |
| 端侧大量硬编码 | tab 顺序/内容类型名/布局参数写死 | 每次产品调整都要发版 |
| 测试场景与代码无绑定 | service.yaml contract_test 声明孤立 | 新增场景不保证测试代码跟进 |
| 隐私策略散落 | fields.yaml classification + 手写过滤 | PII 字段 app 日志无自动过滤 |

### 设计目标

```
contracts/metadata/{domain}/{entity}/   ← 唯一真相源
    所有横切声明（10个维度）
         ↓ codegen
端侧（Dart）：DTO + 错误码 + 行为SDK + UI配置 + 隐私过滤  (DO NOT EDIT)
云侧（Go）：domain struct + 路由 + 错误码 + migration       (DO NOT EDIT)
ML侧（Python）：特征schema + 训练样本schema                 (DO NOT EDIT)
         ↓ 手写
端侧：Widget 渲染逻辑 / 动画 / 状态管理
云侧：领域规则 / 事务 / 推荐算法
```

## 二、方案对比

### 方案 A（当前）：分散声明，手工对齐

- 错误码在 error_codes.md，端侧手写字符串匹配
- 行为事件散落在 types.yaml / service.yaml / _projections/
- 端侧 tab 配置硬编码在 UI 代码

**缺点**：人工协调成本高，漂移难发现，新成员学习曲线陡

### 方案 B（推荐）：per-entity 横切 YAML + codegen 全链路

每个实体目录包含完整的10维横切声明，工具链从同一源生成两端代码。

**优点**：
- 单一修改点（改 YAML → 重新 codegen → 两端一致）
- gate 验证：10项自动校验，无人工检查点
- 端侧代码减少95%以上的业务无关硬编码

**代价**：
- codegen 工具需扩展（6个新生成器）
- 初期 YAML 设计需要投入，但后续复用相同模式

### 方案 C：外部配置中心（Remote Config）

feature flags 和 tab 顺序放远程配置服务（Firebase/自建）

**不选原因**：0→1 阶段，运行时热更新的复杂度不划算；YAML→codegen 的编译期常量已满足需求。远程配置可作为后续演进（ui_config.yaml 的 `runtime_overridable: true` 字段预留）。

**选定方案 B**，预留演进到 B+C（ui_config 支持运行时覆盖）的入口。

## 三、目录结构目标态

```
contracts/metadata/
├── _shared/                         # 跨域共享（精简，仅真正共享的）
│   ├── types.yaml                   # 基础枚举（ContentType 等）
│   ├── redis_keyspace.yaml
│   ├── test_infra.yaml
│   └── errors/
│       ├── common_codes.yaml        # 通用错误码（invalid_argument/not_found...）
│       └── http_mapping.yaml        # 错误码 → HTTP status 映射
│
└── content/                         # 域：content-service
    ├── openapi.yaml                 # ← 从 openapi/content-service.v1.yaml 迁入
    └── post/                        # 聚合根 Post
        ├── aggregate.yaml           # 现有
        ├── fields.yaml              # 现有（字段定义 + 分类 + 日志策略）
        ├── storage.yaml             # 现有
        ├── events.yaml              # 现有
        ├── service.yaml             # 现有（仅路由，测试场景迁出）
        │
        ├── projections/             # ← 从 _projections/ 迁入
        │   ├── photo_post.yaml
        │   ├── video_post.yaml
        │   ├── article_post.yaml
        │   └── moment_post.yaml
        │
        ├── errors.yaml              # NEW：域级结构化错误码
        ├── behaviors.yaml           # NEW：行为采集 + 推荐特征 + 训练样本
        ├── privacy.yaml             # NEW：端侧日志过滤 + GDPR 生命周期
        ├── ui_config.yaml           # NEW：tab/布局/flags/空状态
        │
        └── tests/                   # NEW：三层测试契约
            ├── mock.yaml            # 端侧独立（不依赖云）
            ├── contract.yaml        # 云侧（真实DB，从 service.yaml 迁出）
            └── e2e.yaml             # 端云集成（staging）
```

## 四、Codegen 流水线设计

```
输入（YAML）                        输出（DO NOT EDIT）
─────────────────────────────────────────────────────────────────────
fields.yaml + projections/         → Dart: *_dto.g.dart
service.yaml                       → Dart: content_metadata.g.dart
                                   → Go:   generated/contracts.go
errors.yaml                        → Dart: content_errors.g.dart
                                   → Go:   generated/errors.go
behaviors.yaml                     → Dart: content_behaviors.g.dart
                                   → Python: content_features.py
                                   → Python: training_sample.py
privacy.yaml                       → Dart: content_privacy_policy.g.dart
ui_config.yaml                     → Dart: content_ui_config.g.dart
tests/contract.yaml                → Go:   tests/*_contract_test.go (骨架)
storage.yaml                       → Go:   migration/*.sql
─────────────────────────────────────────────────────────────────────
```

## 五、端云责任边界（重新划定后）

```
端侧手写代码（纯 UI 意图）            云侧手写代码（纯业务规则）
────────────────────────────         ────────────────────────────
✓ Widget 渲染逻辑                     ✓ 领域服务规则
✓ 动画 / 手势 / 导航                  ✓ 幂等 / 事务处理
✓ Riverpod Notifier 状态管理          ✓ 推荐排序算法
✓ 错误 UI 展示（用 codegen 错误码）   ✓ 审核状态机
✓ 行为上报调用（用 codegen 的 Tracker）✓ 计数器原子策略
✓ Tab 渲染（用 codegen 的 UIConfig）  ✓ 跨服务编排
```

## 六、Privacy.yaml 与 fields.yaml 的关系

**设计决策**：不重复声明字段分类（fields.yaml 已有 classification + log_policy），
privacy.yaml 只声明 fields.yaml **无法表达**的：
- 端侧 app log 的具体 mask 策略（city_level_only / truncate 等）
- GDPR 删除级联顺序与策略
- 字段在 API 层的 alias（`_id` → `postId`）

## 七、Feature Flags 演进路径

当前：`ui_config.yaml` → codegen → Dart 编译期常量（修改需发版）

未来（当运营需要热更新时）：
1. `ui_config.yaml` 中标记 `runtime_overridable: true`
2. codegen 额外生成 key 注册表（字符串 key 列表）
3. Remote Config 服务按 key 下发覆盖值
4. 端侧运行时：编译期常量为 fallback，远程值优先

无需改动 UI 代码（已通过 ContentUIConfig 抽象隔离）。
