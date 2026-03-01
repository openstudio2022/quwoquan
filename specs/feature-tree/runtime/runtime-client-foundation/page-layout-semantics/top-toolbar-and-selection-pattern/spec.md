# L4 契约：top-toolbar-and-selection-pattern

## 功能说明

顶部 leading 统一：Modal 用 close，Stack 用 arrow_back。选择器：单选 tap 即返回，多选 select-then-confirm + 底部「取消|完成」。

## 范围

- 创作、编辑、选择器页：leading = close
- 设置、管理、详情、列表子页：leading = arrow_back
- 地点选择（单选）：tap 即 pop，无底部条
- 圈子选择（多选）：底部 取消|完成

## 与父节点关系

父节点：`page-layout-semantics` L3

## 验收标准

- Modal 创作/选择页使用 Icons.close
- Stack 设置/管理页使用 Icons.arrow_back
- 多选选择器底部有 取消|完成
