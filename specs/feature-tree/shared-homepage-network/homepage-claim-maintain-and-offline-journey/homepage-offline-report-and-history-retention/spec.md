# L3 Scenario: homepage-offline-report-and-history-retention

## 节点定位

- `L1_capability`: `shared-homepage-network`
- `L2_journey`: `homepage-claim-maintain-and-offline-journey`
- `L3_scenario`: `homepage-offline-report-and-history-retention`

## 背景与动机

现实世界里的酒店、餐厅、景点和门店会自然消亡。  
如果主页在“关闭”后被直接删除，用户记录内容和口碑将失去锚点，平台可信度也会下降。

## 目标用户

- 上报已关闭、已结束、信息错误的用户。
- 浏览已下线主页记录的用户。

## 功能范围

- 下线上报。
- 已下线状态与原因标签。
- 原 URL、记录内容、记录口碑和相关群组关系保留。

## Out of Scope

- 主页合并。
- 记录迁移。
- 复杂恢复后台。

## 约束

- baseline 统一采用软下线。
- 已下线主页不得直接物理删除。

## 角色分工

- `shared-homepage-network`：下线上报与已下线合同
- `content`：记录内容保留
- `circle`：相关群组关系保留

## 数据生命周期合同

- 已下线主页保留 URL、记录内容、记录口碑和相关群组关系。
- 搜索与推荐可降级，但不可阻断记录访问。

## 非功能目标

- 下线处理 SLA `<= 7 天`

## 验收重点

1. 下线上报链路成立。
2. 已下线主页保留记录。
3. 搜索降级不等于删页。
