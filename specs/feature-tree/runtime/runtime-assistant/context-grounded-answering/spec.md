# L3 特性：context-grounded-answering

## 功能说明
- 小趣基于当前页面结构化 context snapshot（pageType、businessObjects、userAction）做 grounding 回答；引用只指向真实站内对象或声明的外部来源。

## 约束
- 页面只上报结构化 snapshot（`ReportPageContext`），小趣不得维护第二套对象真相源。
- grounding 失败或上下文过期（Redis TTL 300s）时按通用回答降级并声明边界，不合成伪事实。
- 引用（citation）必须携带 objectType/objectId 或外部 sourceDomain，可被端侧回溯打开。

## 验收标准
- A1：内容详情/发现/圈子/聊天四类页面上下文可注入回答。
- A2：上下文缺失/过期时降级回答不失败、不伪造。
- A7：`ReportPageContext` 与 grounding 消费的契约测试可复跑。
