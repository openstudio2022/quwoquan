# L1 Domain Service：<中文名称> (`<l1-id>`)

> 一句话定位：说明本领域为谁解决什么稳定问题，以及它不等同于某个部署进程。

## 1. 目标与用户价值

说明本领域存在的产品理由、核心用户价值和业务结果，不描述类、函数、表结构或施工步骤。

## 2. 领域边界

### 本领域拥有

- <业务对象、生命周期或业务决定权>
- <只能由本领域修改的事实>

### 本领域不拥有

- <容易误归本领域的职责>；owner：[`<other-l1-id>`](../<other-l1-id>/spec.md)

### 上下游协作

- 上游：<L1 链接及输入事实>
- 下游：<L1 链接及输出事实>
- 跨域写入：<目标领域公开 command>
- 跨域读取：<目标领域公开 query/projection>
- 异步协作：<公开 event；不适用则删除>

## 3. Journey / Scenario 职责

- [`JNY-001 / SCN-001`](../spec.md#scn-001)
  - 本领域负责：……
  - 进入条件：……
  - 交付给下游的结果：……
  - 不负责：……

## 4. 业务能力

- [`<l2-id>`](./<l2-id>/spec.md)：<可组合业务结果>

列表必须与直接 L2 子目录一致，并补充语义。

## 5. 领域要求

### REQ-001 <要求标题>

- 本领域必须……
- 本领域不得……
- 契约引用：<canonical contract ID；不适用则删除>

## 6. 领域验收

### DOM-001 <领域边界或不变量>

- 条件：……
- 可观察结果：……
- 禁止结果：……

只验证领域责任、所有权和不变量，测试排列组合留在代码。

## 7. 工程归属

只登记稳定工程根，不列具体实现文件。

- App：`<module-root>`
- Contracts：`<service-contract-root>`
- Metadata：`<shared-metadata-root>`；没有跨服务共享协议则删除
- Service：`<service-or-context-root>`
- Data：`<data-root>`
- Ops：`<ops-root>`
- 测试：
  - `local_contract`：`<root>`
  - `api_integration`：`<root>`
  - `user_acceptance`：`<root>`

## 8. 开放事项

仅在存在未完成事项时保留本章。

### OPEN-001 <标题>

- 类型：`capability_gap | external_blocker | risk | future_plan`
- 优先级：`P0 | P1 | P2 | P3`
- 准出影响：`block | track`
- 影响或价值：……
- 完成判定：`DOM-001` 或其他可观察结果
- 依赖：……
