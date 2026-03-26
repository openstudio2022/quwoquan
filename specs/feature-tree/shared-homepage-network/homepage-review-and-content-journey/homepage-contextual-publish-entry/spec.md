# L3 Scenario: homepage-contextual-publish-entry

## 节点定位

- `L1_capability`: `shared-homepage-network`
- `L2_journey`: `homepage-review-and-content-journey`
- `L3_scenario`: `homepage-contextual-publish-entry`

## 背景与动机

主页不只是被看，还应该成为继续贡献内容的上下文入口。  
如果从主页进入发布器不能自动带入当前主页，主页就只能是静态消费页。

## 目标用户

- 浏览主页后想继续发笔记、作品、提问或口碑的用户。

## 功能范围

- 从主页发起发布动作。
- 自动带入当前主页上下文。
- 发布后回到主页或继续浏览的返回语义。

## Out of Scope

- 编辑器实现。
- 主页搜索与补充。
- 认领和下线。

## 约束

- 主页内发布入口和全局发布入口必须共用同一发布器。
- 当前主页必须默认带入，但允许在非口碑场景调整。

## 角色分工

- `shared-homepage-network`：入口与主页上下文
- `content`：发布器和写入

## 数据生命周期合同

- 主页上下文只在本次发布会话内保留，发布成功后写入稳定内容事实。

## 非功能目标

- 从主页进入发布器的额外开销低

## 验收重点

1. 用户可从主页直接发内容。
2. 当前主页默认带入成功。
3. 发布完成后回流语义稳定。
