# L3 Story：Markdown 文章内核 (`markdown-article-kernel`)

> 所属能力：[`content-type-framework`](../spec.md)

> Journey / Scenario：[`JNY-004 / SCN-001`](../../../spec.md#scn-001)

> 设计归属：[L2 DEC-001](../design.md#dec-001)

## 1. 用户价值

作为内容创作者或浏览者，
我希望小屏或可访问性大字号下统一降级为 `fullWidth`，
从而完成可恢复的内容创作、发现或互动。

## 2. 范围与非目标

### In Scope

- “Markdown 文章内核”的输入、可观察主路径、失败语义以及与父能力的交接。

### Out of Scope

- 父能力中由其他 Story 独立拥有的行为、能力级架构决定和实现任务。

## 3. 行为要求

<a id="req-001"></a>
### REQ-001 Markdown 文章内核

- 小屏或可访问性大字号下统一降级为 `fullWidth`。

<a id="req-002"></a>
### REQ-002 小屏或可访问性大字号下统一降级为 fullWidth

- 小屏或可访问性大字号下统一降级为 `fullWidth`。
- 降级不能丢失图片、caption、阅读顺序和语义标签。
- Markdown 解析失败时必须返回结构化 runtime failure，不向用户暴露原始异常字符串。
- 素材缺失、hash 不匹配、scope 不合法时不可发布。
- 详情页、发现沉浸式和侵入式媒体浏览器必须消费同一 AST/page model。
- seed、fixture、冷启动 batch 中不得再新增 `articleDocument` 长文真相源。

<a id="req-003"></a>
### REQ-003 行内样式记号与编辑阅读保真

- `qwq-rich-md` 的行内样式记号：`**粗体**`、`*斜体*`、`***粗斜体***`、
  `++下划线++`、`~~删除线~~`；记号必须成对，未闭合记号按字面量文本处理，
  不得 crash、不得吞字。
- 编辑器行内样式 span（bold/italic/underline/strikethrough）序列化必须写出
  对应记号；解析必须还原为等价 span；编辑→发布→重新打开的 roundtrip 不得
  丢失样式（所见即所得）。
- 阅读端与编辑预览消费同一行内分段真相源（span 字符级合成），记号本身
  不得作为字面量出现在渲染文本中；行内 mention 记号 `@[label](kind:id)`
  与样式记号可共存，mention 段为原子段不被样式记号切分。

<a id="req-004"></a>
### REQ-004 富块阅读渲染不做有损压缩

- `parseDocument` 对 quote、callout、codeBlock 不得压缩成 paragraph 或丢弃；
  三类块必须进入 Document 模型并由阅读主路径渲染
  （引用条、callout 卡面、等宽代码块），样式走既有模板/纸张 token。
- 数据工程供稿（同 `qwq-rich-md` dialect）中的上述富块与 App 编辑器产出
  必须由同一渲染路径呈现，禁止建立第二套渲染真相源。
- 编辑器暂不提供三类块的创作 UI；编辑器加载含富块的文档时必须保留原块
  语义（不改写、不降级），再次序列化时原样写回。

<a id="req-005"></a>
### REQ-005 行内链接与嵌套列表贯通

- 行内链接 `[text](https://…)`：解析产出 `kind='link'` 原子 span，targetId
  即链接地址；仅白名单 scheme（https/http）进入 span 真相源，恶意 scheme
  如 javascript:/data: 按字面量输出不产生 span；序列化按原形写回；
  阅读端链接段可点，经系统浏览器打开外链。
- 嵌套列表：`listDepth` 语义为嵌套级别 0–2（0 = 顶层），序列化按两空格/级
  写缩进、解析按缩进还原、阅读端按级别渲染缩进；parser、codec 与渲染共用
  同一约定，禁止第二套缩进映射。

## 4. 契约引用

- 父能力公开契约：[`L2 spec`](../spec.md)。

## 5. 验收场景

<a id="gwt-001"></a>
### GWT-001 Markdown 文章内核

- GIVEN 内容创作者或浏览者具备有效身份，且父能力声明的输入与上游事实成立。
- WHEN 参与者执行“Markdown 文章内核”对应的公开行为。
- THEN 小屏或可访问性大字号下统一降级为 `fullWidth`。
- AND 失败时返回 canonical failure，且不产生伪成功事实。

<a id="gwt-002"></a>
### GWT-002 行内样式编辑阅读 roundtrip 保真

- GIVEN 作者在编辑器对正文区段施加粗体、斜体、下划线或删除线。
- WHEN 文档序列化为 `qwq-rich-md` 发布，再由阅读端或编辑器重新解析。
- THEN 序列化输出含成对样式记号，解析还原等价 span，样式不丢失。
- THEN 阅读端按 span 渲染样式，记号不以字面量出现在渲染文本。
- THEN 未闭合记号按字面量处理不吞字；mention 段保持原子且可点。

<a id="gwt-003"></a>
### GWT-003 富块阅读渲染保真

- GIVEN 数据工程或未来编辑入口产出的 `qwq-rich-md` 含 quote、callout、codeBlock。
- WHEN 阅读主路径经 `parseDocument` 渲染该文档。
- THEN 三类块进入 Document 模型且渲染为引用条、callout 卡面与等宽代码块。
- THEN 无有损压缩：块文本、顺序与语义完整保留。

<a id="gwt-004"></a>
### GWT-004 行内链接可点与嵌套列表 roundtrip

- GIVEN `qwq-rich-md` 正文含 `[text](https://…)` 链接与两空格缩进嵌套列表项。
- WHEN 文档经 `parseDocument` 解析、阅读端渲染并再次序列化。
- THEN 链接还原为原子 link span 且阅读端可点（系统浏览器打开）；恶意
  scheme 不产生 span、按字面量呈现。
- THEN 列表项 `listDepth` 按缩进还原（最多 2 级），序列化按同一约定写回，
  roundtrip 不丢失嵌套结构；阅读端按级别缩进渲染。

## 6. 依赖

- 前置要求：[`content-type-framework`](../spec.md) 的范围、要求与 SIT。
- 下游结果：本 Story 声明的 GWT 可观察结果。
- 父级设计：[L2 DEC-001](../design.md#dec-001)

## 7. 开放事项

<a id="open-001"></a>
### OPEN-001 Markdown 文章内核 验收证据

- 类型：`capability_gap`
- 优先级：`P1`
- 准出影响：`track`
- 影响或价值：尚缺 `GWT-001` 小屏/大字号 fullWidth 降级行为的直接测试绑定，
  以及 `GWT-004` 阅读端子句的证据——链接段可点经系统浏览器打开、嵌套列表按
  级别缩进渲染；`GWT-004` 的 codec 侧——链接原子 span、恶意 scheme 字面量
  降级与 listDepth roundtrip——已由
  `article_markdown_codec__local_contract_test.dart` 覆盖。`GWT-002` 行内样式 roundtrip 已覆盖序列化—解析双向等价、未闭合记号字面量降级与
  mention 原子共存；`GWT-003` 富块阅读渲染保真已覆盖 quote/callout/codeBlock 的
  解析—投影—分页—序列化写回全链。两者分别由
  `article_markdown_codec__local_contract_test.dart` 与
  `article_typography_page_widget__local_contract_test.dart` 绑定闭合。
- 完成判定：`GWT-001`、`GWT-002`、`GWT-003` 三条对应行为均满足且各自有真实测试 `spec_ref`，且 `GWT-004` 的 4 条结果子句（`gwt-004.t1..t4`）各自被真实测试 `spec_ref` 绑定。`GWT-002` 与 `GWT-003` 必须覆盖 `qwq-rich-md` 的解析—序列化双向等价，不得只断言单向渲染结果。
