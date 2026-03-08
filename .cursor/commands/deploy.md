---
name: /deploy
id: deploy
category: Workflow
description: 部署（commit 入库后，部署到 integration → L3/L4 集成验证 → 灰度到 prod）
---

> SDD 主流程：... → commit → **deploy**

commit 完成入库（L1/L2 自测通过）后，执行本命令完成：**部署到集成环境 → L3/L4 集成验证 → 灰度/滚动发布到生产**，实现特性到生产端到端打通。

---

## 前置条件检查（执行前必须满足）

| # | 检查项 | 判定方式 |
|---|--------|----------|
| 1 | /commit 已完成 | 代码已入库 main，make gate 通过 |
| 2 | integration 环境可用 | staging/integration API 可访问，CONFIG_VERSION/IMAGE_VERSION 已准备 |
| 3 | 部署拓扑一致 | `verify_deployment_domain_mapping.sh` 通过，integration 与 prod mapping 一致 |
| 4 | 灰度参数就绪 | FROM_IMAGE、TO_IMAGE、FROM_CONFIG、TO_CONFIG 已确定，STEP 序列为 5→25→50→100 |
| 5 | 观测与回滚就绪 | 日志、指标、报警、回滚命令、负责人已明确 |
| 6 | 非功能目标可观测 | 实时性 / 弱网 / 性能 / 容量 / 体验指标可采集 |

**若不满足**：输出前置条件补全列表，引导用户完成后再执行 `/deploy`。

---

## 执行流程

### 阶段 1：G5a — 部署到 integration

1. 确认 `deploy/shared/process_domain_mapping.yaml` 中 integration 拓扑
2. 使用 `deploy/service/seed-box/kustomize/overlays/integration` 渲染部署清单
3. 将 main 当前版本（或指定 tag/commit）构建物部署到 integration 环境
4. 验证 integration API 可达：

```bash
curl -s -o /dev/null -w "%{http_code}" $STAGING_BASE_URL/health
```

**失败** → 输出部署日志 + 修复建议，修复后重试。

---

### 阶段 2：G5b — L3/L4 集成验证

#### 2.1 L3 API Contract 测试

```bash
STAGING_BASE_URL=<integration-api-url> TEST_AUTH_TOKEN=<token> make test-api-contract
```

失败 → 阻塞，不得进入 G5c。

#### 2.3 非功能与体验复核

进入灰度前必须确认以下目标已在 integration 有可观测证据：
- **实时性**：端到端时延、送达/处理时延、顺序一致性、重连恢复时间
- **弱网体验**：高延迟、抖动、短断网下的加载、重试、回退、提示与最终一致性
- **并发性能**：热点路径 P95/P99、错误率、资源占用、限流/降级行为
- **交互体验**：首屏时间、关键交互成功率、卡顿率、崩溃率、对标体验不打折项

任一关键项未达标 → 阻塞，不得进入 G5c。

#### 2.2 L4 Patrol 测试

```bash
cd quwoquan_app && patrol test test/patrol/ \
  --dart-define=ENV=staging \
  --dart-define=STAGING_BASE_URL=<integration-api-url> \
  --dart-define=TEST_AUTH_TOKEN=<token>
```

需连接真机或模拟器；CI 可用 Firebase Test Lab（见 `.github/workflows/pre-release-gate.yml`）。

失败 → 阻塞，不得进入 G5c。

---

### 阶段 3：G5c — 灰度/滚动发布到 prod

按 `deploy/service/config-release/` 规范执行灰度发布：

#### 3.1 灰度步进序列

```
STEP: 5 → 25 → 50 → 100（%）
```

每步执行：

```bash
make config-gray-rollout \
  SERVICE=<service-name> \
  FROM_IMAGE=<current> TO_IMAGE=<target> \
  FROM_CONFIG=<current> TO_CONFIG=<target> \
  STEP=5   # 依次 25, 50, 100
```

#### 3.2 SLO 卡点（每步后必须执行）

```bash
make config-slo-gate \
  ERROR_RATE=<实测> \
  P95_MS=<实测> \
  REDIS_ERROR_RATE=<实测>
```

阈值见 `deploy/service/config-release/slo_thresholds.yaml`。

每步放量后还必须复核：
- 实时性指标：如送达时延、流式首 token、同步恢复时间
- 弱网体验指标：重试成功率、断线恢复率、回退成功率
- 端侧体验指标：崩溃率、卡顿率、首屏/关键交互耗时
- 容量弹性指标：错误率、CPU/内存、队列堆积、限流触发情况

超过 critical → 执行回滚：

```bash
make config-rollback SERVICE=... TO_CONFIG=<from_config>
```

---

## 输出摘要

```
部署完成：<service> → prod

| 阶段                   | 状态      |
|------------------------|-----------|
| G5a. 部署 integration  | 已部署    |
| G5b. L3 集成验证       | 通过      |
| G5b. L4 Patrol 验证    | 通过      |
| G5b. 非功能/体验复核   | 通过      |
| G5c. 灰度发布 prod     | 已到 100% |

灰度步进：5 → 25 → 50 → 100
SLO 卡点：每步通过
实时性/弱网/体验指标：达标
```

---

## 参考

- `deploy/shared/process_domain_mapping_runbook.md` — 部署拓扑
- `deploy/shared/deliver_to_production_runbook.md` — commit → prod 端到端流程
- `deploy/service/config-release/runbook.md` — 配置发布与灰度

---

## 与其他命令的关系

| 命令 | 作用 | 与 /deploy 关系 |
|------|------|----------------|
| `/commit` | 归档 + 提交合入 | deploy 的前置：commit 完成后执行 deploy |
| `/deliver` | dev + commit 一气呵成 | deliver 完成后的下一步为 deploy |
