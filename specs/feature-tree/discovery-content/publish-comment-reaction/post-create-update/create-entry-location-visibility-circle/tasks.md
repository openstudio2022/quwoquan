# 开发任务：create-entry-location-visibility-circle

## 当前交付任务

### metadata
- [x] M1. 核对 `content/post` 现有元数据字段可覆盖本需求（`visibility/location/locationName/circleIds`）。
- [x] M2. 若发现缺口，仅补最小 metadata 变更并更新对应契约说明；无缺口则记录“无需变更”。

### codegen
- [x] C1. 执行 `make verify-metadata`。
- [x] C2. 仅在 metadata 发生变更时执行 `make codegen && make codegen-app` 并提交产物。

### 业务逻辑
- [x] B1. 抽取通用发布设置状态模型（`PublishSettings`），承载位置/公开/圈子选择并支持多页面复用。
- [x] B2. 实现可复用“所在位置”入口与回填展示组件（未选默认不显示，选中后蓝色高亮）。
- [x] B3. 接入地图位置服务抽象，支持附近位置与关键字搜索，按配置切换百度/阿里。
- [ ] B4. 实现可复用“是否公开”Switch（CupertinoSwitch，iOS 风格，激活态蓝色），默认公开。
- [x] B5. 实现可复用“选择要发布的圈子”多选入口：仅公开时显示，回填逗号分隔并支持省略显示；圈子选择器全屏、顶部居中「选择圈子」、底部取消+完成、默认全选，暂不加搜索框。
- [ ] B6. 在 moment/photo/video/article 四类发布流程中接入通用发布设置组件。
- [x] B7. 修正统一发布 payload 映射：`visibility`、`location`、`locationName`、`circleIds` 按状态正确提交（经由 PublishSettings.toPayloadFields）。
- [x] B8. 异常降级：地图失败可回退“不显示位置”；圈子列表为空可发布但给出空态提示。
- [x] B9. 统一发布设置图标：是否公开、发布到圈子入口采用与高品质内容创作定位匹配的 CupertinoIcons 或等效风格；所在位置入口已统一为 CupertinoIcons.location。

### 测试
- [ ] T1. 通用组件 UI/状态单测：公开开关、圈子展示联动、位置与圈子回填文本。
- [x] T2. Payload 单测：四类内容在公开/私密、是否选位置、是否选圈子下的多组合断言。
- [ ] T3. Journey 回归：至少覆盖 moment + photo/video/article 任一媒体页的发布路径（remote/mock 各至少一条）。
- [ ] T4. 复用验证：其它媒体编辑页接入通用发布设置后无需重复业务逻辑代码。

## 搁置任务（带规划）
- [ ] P1. 更多功能按钮反馈（不感兴趣/屏蔽/投诉）端云闭环。
  - 搁置原因：当前迭代聚焦“创作入口可发布”主链路。
  - 重启条件：本节点 A1~A8 达成后，在 `content-action-intent-contract` 节点承接。

## 未来演进任务
- [ ] F1. 位置选择支持最近使用与收藏地点。
- [ ] F2. 圈子列表支持搜索与按兴趣排序。
- [ ] F3. 发布前增加“圈子推荐”智能提示（基于历史互动）。
