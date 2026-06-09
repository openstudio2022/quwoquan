# 端云一体化开发主线

> 唯一主线。所有命令式开发和直接对话开发都必须先落到同一棵树，再落到验收和测试证据。

## 一棵树

```text
AppRoot
  └── L1_domain_service
        └── L2_business_capability
              └── L3_story
```

- 应用根：全 App 定位、跨领域 Journey/Scenario、UAT、全局架构与治理。
- `L1_domain_service`：产品领域服务边界、上下游依赖、服务治理。
- `L2_business_capability`：领域内业务能力、跨 Story 编排、SIT。
- `L3_story`：最小可闭环价值点、GWT、接口契约。

`Journey/Scenario` 只在应用根 registry 和 UAT 中表达，不作为目录层。临时执行计划与会话 todo 不属于正式特性树文档。

## 增量入口检查

任何增量开始前必须能回答：

```text
AppRoot Journey/Scenario: <id 或无影响>
L1_domain_service: <domain>
L2_business_capability: <capability>
L3_story: <story>

验收意图: UAT / SIT / GWT / contract
测试证据: T1 / T2 / T3 / T4
```

若无法填写，先补 `spec.md` / `acceptance.yaml`，或补应用根 registry、能力 `design.md`、metadata/test 设计。不得绕过。

## 文档分工

- `spec.md`：定位、范围、业务对象、边界、Out of Scope。
- `design.md`：只在应用根、领域服务、业务能力层存在；描述架构、边界、依赖、技术约束、观测与回滚。
- `acceptance.yaml`：UAT/SIT/GWT/contract、done_when、证据、测试。
- `journey_scenario_registry.yaml`：跨领域 Journey/Scenario 到领域服务、能力、Story 的映射。
- `specs/changelog/CR-*.yaml`：增量变更影响记录。

## 测试映射

| 树层级 | 验收意图 | 主要证据 |
|---|---|---|
| AppRoot | UAT | `T4`，辅以 `T3` |
| `L1_domain_service` | 领域边界与治理 | `T1/T3`，必要时 `T4` |
| `L2_business_capability` | SIT | `T2/T3` |
| `L3_story` | GWT + contract | `T1/T2`，涉及远端补 `T3` |

## 非协商原则

- `spec-first`、`acceptance-first`、`test-first`。
- `metadata-first`：字段、错误码、path、operation、surface、route、decoder context 先改 metadata。
- `env-seed-first`：alpha/beta/gamma 数据来自 metadata fixtures 与 seed manifest。
- `single-source`：不得维护第二套树、第二套路由、第二套错误码或第二套 mock 数据。
- `commercial-ready-before-dev`：用户可见、可灰度、可分享、可被小趣消费的能力，先冻结 SLO/KPI、权限、生命周期、灰度和回滚。
- `no-partial-stop`：进入 `/dev` 后，目标 Story 相关前后端、metadata/codegen、测试、验收和证据必须闭环到待 `/commit`。

## 阶段口径

- `/explore`：定位 AppRoot Journey/Scenario 与三层目录归属，识别 metadata、测试、CR、风险。
- `/prd`：冻结 `spec.md` 与 `acceptance.yaml`，必要时更新 registry 和 CR。
- `/design`：只冻结应用根、领域服务、业务能力 `design.md`。
- `/plan-review`：冻结/开发前，用设计、产品、架构、代码评审、测试质量、运维运营、工程自动化多角色交叉检视规格/任务清单/验收的完备性，对标微信·小红书·Apple HIG 刷新规划。
- `/baseline`：需求稳定且方案收敛时，一次冻结 spec / acceptance / 必要 design / CR。
- `/dev`：从 Story acceptance 和当前会话计划派生 todo，执行 Red → Green → Refactor。
- `/verify`：检查 UAT/SIT/GWT/contract 与 `T1~T4` 证据。
- `/plan-next`：功能或计划完成后，多角色自检完成度与证据，回填未达成项后生成下一轮规划（目标 / 规格 / 任务清单 / 验收标准）。
- `/commit`：只提交已闭环 Story、相关文档、metadata/codegen、测试和 CR。
- `/deploy`：以 release batch / CR 范围发布，必须完成 `T3/T4`、SLO、观测和回滚演练。

## 阻断项

- 旧树目录层级或旧验收 schema 回归。
- 临时执行计划或会话 todo 进入正式特性树。
- Story 层设计文档回归。
- UI 直连 mock、硬编码 path/error/surface/operation。
- `implemented/completed` 但无测试证据。
