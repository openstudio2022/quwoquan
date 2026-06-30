<figure_contract>
正文用 **figure fence** 承载图片，与底稿、发布渲染同一套语法。两类，你都必须保留其位置、禁止改 id / assetId：

- 单图 fence：
  ```
  :::figure id="<figureId>" layout="fullWidth|wrapLeft|wrapRight|gallery" caption="你的自然说明"
  asset://<assetId>
  :::
  ```
- 连续图组 fence（底稿中相邻连续多图已合并为一个组，内部含 N 个图片行）：
  ```
  :::figuregroup id="<groupId>" count="<N>"
  ![说明1](asset://<assetId-1>)
  ![说明2](asset://<assetId-2>)
  :::
  ```
  这一整块代表**同源相邻的 N 张图**：你必须把它当作一个不可拆分的占位整体原样带回（保留起始 `:::figuregroup` 行的 id 与 count、保留组内每一行 `![..](asset://..)` 的 assetId 与相对顺序、保留收尾 `:::`），放到最贴合上下文的段落之间即可；CLI 会在发布时把它回填展开为 N 张同源连续图。

规则（always）：
- 底稿正文里**已存在**的 figure / figuregroup fence，按原 id、原 assetId、原相对顺序保留，放在最贴合上下文的段落之间，文字围绕它自然展开。
- 需要补封面 / 收尾 / 图集图时，只能引用 `<documents>` 「可用配图素材」里列出的 assetId，用上面的 fence 语法写入。
- 连续图组 fence 代表**同源相邻的 N 张图**：整组保留，不要改 count、不要打散。

规则（never）：
- 禁止虚构 assetId 或引用素材清单之外的 id（会被 generatorProvenance 门拦截）。
- 禁止把 `:::figuregroup ...:::` 拆成多个 `:::figure:::`，或把多张独立图硬塞进一个组。
- 禁止删掉底稿已有的 figure / figuregroup fence 导致图文丢失（这正是上一轮「图文混排丢失」的根因）。
</figure_contract>
