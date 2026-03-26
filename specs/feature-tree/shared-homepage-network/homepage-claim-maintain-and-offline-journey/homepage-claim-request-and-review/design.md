# homepage-claim-request-and-review 设计

## 设计动因

主页认领是经营主体和共享主页网络建立正式关系的入口。  
如果认领链路没有明确设计，常见后果只有两个：

1. 材料太轻，谁都能认领；
2. 材料太重，没人愿意认领。

## 上游输入评审

- L2：`specs/feature-tree/shared-homepage-network/homepage-claim-maintain-and-offline-journey/spec.md`
- L2 design：`specs/feature-tree/shared-homepage-network/homepage-claim-maintain-and-offline-journey/design.md`
- L3：`spec.md`
- L3 acceptance：`acceptance.yaml`
- 认领后维护场景：`claimed-homepage-basic-maintenance`

当前仓库已经具备认领申请表单、审核操作和 claimed 状态更新，因此本设计重点冻结“材料分层、审核状态和认领结果合同”。

## 方案对比

### 方案 A：所有类目统一走重材料 KYC

优点：

- 风控规则表面统一。

缺点：

- 冷启动阻力过高；
- 不适合多元实体主页；
- 申请转化率低。

### 方案 B：分层材料 + 显式审核状态

优点：

- 兼顾风险与转化；
- 与不同实体类目更匹配；
- 后续能自然延展到维护权限。

缺点：

- 需要冻结 claim tier 和状态字段。

### 选型

选择 **方案 B**。

## 关键设计决策

### D1：认领材料按 tier 分层

baseline 至少区分：

- `basic_claim`
- `verified_claim`

不同 tier 的材料强度不同，但都进入统一审核状态机。

### D2：认领状态不等于维护权限自动开放

审核通过后主页进入 `claimed`，才允许继续进入 maintenance flow。  
审核中主页仍可浏览，但不显示已认领标识。

### D3：补件、驳回和通过都是正式结果

认领审核最小结果包括：

- 待审核
- 补件
- 驳回
- 通过

这样才能避免“提交后黑盒等待”的治理问题。

### D4：认领只建立经营主体与主页关系，不改写主页事实

认领完成后只是拿到维护权，不意味着：

- 可以直接改评分
- 可以删历史内容
- 可以直接下线主页

后续操作仍需走各自场景合同。

## metadata / codegen 方案

- `entity/homepage/fields.yaml`：claim tier、claim status、claim evidence
- `entity/homepage/service.yaml`：create / review claim request
- `entity/homepage/errors.yaml`：材料不全、越权、重复申请错误码
- app 端：认领页与状态展示共用同一 contract

## TDD / ATDD 策略

- `T1_schema`：tier、状态和材料字段稳定
- `T2_module_interaction`：认领申请、审核、补件和驳回稳定
- `T3_cross_service_integration`：通过后主页进入 claimed 状态并可进入维护

## 回滚策略

- 一级回滚：关闭认领入口，但保留已认领主页
- 二级回滚：暂停审核通过动作，仅保留申请记录
- 不允许回滚到“未审核就显示已认领”的状态
