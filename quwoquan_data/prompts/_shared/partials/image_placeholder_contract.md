<image_placeholder_contract>
底稿材料中形如下面这样的**整行**是系统图片占位符（只有 id，不含图注）：

```
[[IMG:fig_03]]
```

你的职责边界（最小干扰协议）：

规则（always）：
- 每一行 `[[IMG:fig_NN]]` 占位符都必须**原样带回**：保持 id、独占一行的形态不变，行尾不加任何文字。
- 你只做文字工作：语病修正、繁简统一、冗余压缩、章节标题规整；保持事实与章节顺序。

规则（never）：
- 禁止新增、删除、移动、复制任何占位符行；禁止改动占位符 id；禁止在占位符行前后拼写图注。
- 禁止书写任何 `asset://`、`:::figure`、`:::gallery`、frontmatter、封面或『相关图片』章节；
  当前 draft 只保留 compose 阶段已经冻结的图片占位关系，最终对象结构留给 publish 阶段显式物化。
- 任一占位符缺失 / 新增 / 重复 / 行尾追加文字，都必须在 stage contract 自检中判为 blocked，
  不得伪报通过或等待自动重跑。
</image_placeholder_contract>
