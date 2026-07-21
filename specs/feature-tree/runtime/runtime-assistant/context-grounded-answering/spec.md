# L3 特性：context-grounded-answering

## 功能说明
- 小趣基于当前页面结构化 context snapshot（pageType、businessObjects、userAction）做 grounding 回答；引用只指向真实站内对象或声明的外部来源。
- 交集入口只提交 `AssistantIntersectionEvidenceRef`（intersectionId、evidenceId、sourceRef、canonical object type/id）；assistant-service 必须按当前 actor 通过 content 的公开 Reader 回查当前事实后，才可将其注入 prompt、evidence ledger 与 citation。

## 约束
- 页面只上报结构化 snapshot（`ReportPageContext`），小趣不得维护第二套对象真相源。
- grounding 失败或上下文过期（Redis TTL 300s）时按通用回答降级并声明边界，不合成伪事实。
- 携带交集证据引用的 Run 在对象不存在、actor 无权访问、证据快照已过期或 sourceRef/目标不匹配时必须 fail-closed，返回 metadata 定义的结构化失败；禁止静默忽略或信任客户端标题、结论、URL、tag 与样本。
- 引用（citation）必须携带唯一 `CitationDestination`：站内为 canonical object type/id 与 metadata 生成的 deep link，站外仅为已校验 HTTPS URL；未知目标、无链接或无权访问不得回退打开 post。

## 验收标准
- A1：内容详情/发现/圈子/聊天四类页面上下文可注入回答。
- A2：上下文缺失/过期时降级回答不失败、不伪造。
- A7：`ReportPageContext` 与 grounding 消费的契约测试可复跑。
- A8：交集卡到小趣只传强类型引用；服务端以当前 actor 回查后才写入 prompt、evidence ledger 与 citation，伪造、撤销或过期引用被拒绝。
- A9：站内与站外 citation 均经同一 destination resolver 打开，未知类型、无链接和无权访问 fail-closed。
