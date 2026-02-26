# quwoquan 端云一体化契约总览

> 本目录是端云一体化开发的**唯一真相源**。
> 所有代码生成、测试、门禁均从此目录 YAML 驱动，不存在手动维护的副本。

---

## 目录结构

```
contracts/
├── metadata/                  ← 核心：业务对象元数据（详见 metadata/DESIGN.md）
│   ├── _shared/               ← 跨域共享（枚举、Redis key、测试引擎、消息信封）
│   ├── _vectors/              ← 向量索引（跨服务共享）
│   ├── content/               ← 内容域 → content-service
│   ├── user/                  ← 用户域 → user-service
│   ├── messages/              ← 消息域 → chat-service
│   ├── social/                ← 社交域 → circle-service
│   ├── assistant/             ← 助手域 → assistant/orchestrator-service
│   ├── recommendation/        ← 推荐域 → rec-model-service
│   ├── notification/          ← 通知域 → notification-service
│   └── ops/                   ← 运营域 → ops-service
│
└── [横切规范文档]              ← 跨域工程规范（不含业务对象定义）
    ├── authn_authz.md         ← 认证鉴权规范（JWT/scope/角色）
    ├── ci_cd_automation.md    ← CI/CD 自动化规范
    ├── configuration.md       ← 配置管理规范
    ├── ddd_fullstack_guidelines.md ← DDD + 端云一体化开发指南
    ├── feedback_and_learning.md    ← 反馈与自学习规范
    ├── id_and_pagination.md   ← ID 格式 + 分页规范
    ├── metrics.md             ← 指标体系
    ├── roles_and_scopes.md    ← 角色与权限范围
    ├── service_governance.md  ← 服务治理（熔断/限流/降级）
    ├── exception_log_baseline.yaml    ← 异常日志格式基线
    ├── io_access_log_baseline.yaml    ← 接入日志格式基线
    └── process_trace_log_baseline.yaml← 过程追踪日志格式基线
```

---

## 每个业务域的标准文件集（以 content/post/ 为完整参考实现）

```
{domain}/{entity}/
├── aggregate.yaml     # 存储后端 + DDD 层级映射 + counter strategy
├── fields.yaml        # 字段 + 分类（PUBLIC/PII/SENSITIVE/SECRET）+ 日志策略
├── storage.yaml       # 索引 + Migration DDL + TTL
├── events.yaml        # 领域事件
├── service.yaml       # API 路由（仅路由声明，测试场景在 tests/）
├── projections/       # 端侧 DTO 投影（codegen → Dart，DO NOT EDIT）
├── errors.yaml        # 结构化错误码 → codegen 端云双侧
├── behaviors.yaml     # 行为采集 + ML 特征 + 训练样本 → codegen 端/Python
├── privacy.yaml       # 端侧日志过滤 + GDPR 删除级联
├── ui_config.yaml     # 端侧 UI 配置（tab/布局/feature flags）
└── tests/
    ├── mock.yaml      # 端侧独立测试场景（flutter test）
    ├── contract.yaml  # 云侧契约测试场景（go test + 真实 DB）
    └── e2e.yaml       # 端云集成场景（staging，advisory）
```

**参考实现**：`metadata/content/post/` — 包含全部 10 个横切面的完整声明。

---

## codegen 流水线

```bash
# 1. 验证 YAML 内部一致性（枚举引用/字段类型/路径绑定/门禁 G1~G10）
make verify-metadata

# 2. 生成 Go 代码（struct + routes + errors + migration + fixture 骨架）
make codegen

# 3. 生成 Dart 代码（DTO + metadata + errors + behaviors + privacy + ui_config）
make codegen-app

# 4. 生成 Python 代码（features + training_samples Pydantic）
make codegen-rec-model-python

# 5. 全量门禁（含 codegen hash 保护 + 结构约束 + 测试场景覆盖验证）
make gate
```

---

## 端云路径三段对称

```
contracts/metadata/{domain}/{entity}/   ← YAML 唯一真相源
         ↕ codegen
lib/cloud/{domain}/generated/           ← Dart codegen 产物（DO NOT EDIT）
lib/cloud/{domain}/repository/          ← Dart 手写 Repository（三层模式）
         ↕ HTTP 契约（openapi.yaml）
services/{domain}-service/              ← Go 服务实现
```

**一致性规则**：域名称（content/user/messages/social/...）在三段路径中必须一致，
`make gate G10` 自动检查 projections output_path 前缀匹配。

---

## 错误处理拉通

云侧返回：`{"code": "CONTENT.USER.post_not_found", "userMessage": "内容不存在", ...}`

端侧解析链（全部 codegen，零手写）：
```
CloudErrorMapper.parse(body)
  → ContentErrorCode.postNotFound       (from errors.yaml → content_errors.g.dart)
  → ContentErrorMessages.zh[code]       (i18n 文案，从 errors.yaml user_message 生成)
  → UI 直接展示，无需任何 switch/if
```

---

## 新增业务对象的标准流程

```
1. 选择归属域，在 metadata/{domain}/{entity}/ 创建 5 文件（aggregate/fields/storage/events/service）
   → 使用 /qwq-extend new-aggregate 命令，禁止手动 mkdir
2. make verify-metadata          # 确认 YAML 合法
3. make codegen && make codegen-app  # 生成代码骨架
4. 手写领域逻辑（domain service + application use case + adapter handler）
5. 填充 errors.yaml / behaviors.yaml / ui_config.yaml / tests/
6. make gate                     # 全量门禁，通过后合入
```
