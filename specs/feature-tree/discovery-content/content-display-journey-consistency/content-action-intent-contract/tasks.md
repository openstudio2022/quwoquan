# 开发任务：content-action-intent-contract（8 类反馈闭环）

## 当前交付任务

### metadata（M）

- [x] M1：`user_profile/fields.yaml` 为 `UserSetting` 新增 `blockedKeywords` 字段（string[]，read_write），并保持隐私分级可被推荐过滤消费
- [x] M2：`content/post/behaviors.yaml` 中 `report.dedicated_route` 对齐为 `POST /v1/content/reports`
- [x] M3：确认 8 类反馈路由与对象归属（content/post、content/report、user/block_edge、user/user_profile）在 metadata 中无冲突
- [x] M4：执行 `make verify-metadata`（或仓库兼容命令 `make verify`）通过

---

### codegen（C）

- [x] C1：执行 `make codegen`
- [x] C2：执行 `make codegen-app`
- [ ] C3：若推荐请求 schema 变化，执行 `make codegen-rec-model-python`

---

### 业务逻辑（A）

- [x] A1：端侧反馈入口全接线（Works/Moment）：like/favorite/share/comment/dislike/report/block user/block keywords
- [x] A2：`comment` 从 UI 本地回调改为真实调用评论 API（createComment），并上报 commentLength 特征
- [x] A3：`block keywords` 增加 Repository + Provider，接入用户设置读写
- [x] A4：content-service 实现 like/unlike/favorite/unfavorite handler（当前为 not implemented）
- [x] A5：建立专用路由反馈到推荐热链路的桥接（ContentReacted/BehaviorBatchReported 对齐）
- [x] A6：补齐计数一致性策略：view/like/favorite/comment/share 的主存储写入与回读口径统一
- [x] A7：推荐过滤接入 user block + keyword block（召回后过滤或预过滤，二选一并文档化）
- [x] A8：rec-model-service transformer/scorer 接入 sessionSignals（至少读 tagWeights/exposed/negative）

---

### 测试（T）

- [x] T1：L1 端侧 Journey：8 类反馈逐类覆盖（成功/失败/回滚）
- [x] T2：L2 云侧契约：like/favorite/comment/report/block 路由行为与幂等语义
- [x] T3：L3 API 契约：`/v1/content/behaviors`、`/v1/content/reports`、`/v1/user/block/*`、settings privacy patch
- [x] T4：推荐回归：`dislike` 进入 negative 过滤、`share/like/comment` 改变排序、`block keywords` 过滤命中
- [x] T5：执行 `make gate-full` 通过

---

## 搁置任务（带规划）

| 任务 | 搁置原因 | 重启条件 |
|------|----------|----------|
| block keywords 语义检索（同义词扩展） | 先做精确词匹配闭环 | 基础闭环稳定后 |
| 评论情感强度特征（NLP） | 依赖模型能力 | rec-model-service 引入文本模型后 |
