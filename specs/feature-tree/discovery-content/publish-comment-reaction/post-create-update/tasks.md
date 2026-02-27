# 开发任务：post-create-update

## 元数据（metadata）

- [x] contracts-first
- [x] metadata 对齐
- [x] 更新 `content/post/aggregate.yaml`：新增分发/转发/墓碑实体成员
- [x] 更新 `content/post/fields.yaml`：补充 visibility 简化、summary/illustration/source/device/location 等字段与新实体
- [x] 更新 `content/post/storage.yaml`：新增 `post_circle_distribution`、`post_circle_reshare`、`deleted_post_tombstones`
- [x] 更新 `content/post/service.yaml`：补齐分发管理、转发、上传会话、封面策略、摘要生成等路由
- [x] 更新 `content/post/events.yaml`：新增分发更新、转发、级联删除、墓碑、媒体元数据事件
- [x] 更新 `content/post/errors.yaml`：补齐发布后不可变、已删除命中、分发冲突等错误码
- [x] 更新 `_shared/types.yaml`：Visibility 调整为 `public/private`，新增 source/distribution 枚举

## 代码生成（codegen）

- [x] 执行 `make verify-metadata`
- [x] 执行 `make codegen`
- [x] 执行 `make codegen-app`
- [x] 修复 metadata/codegen 不一致问题直至通过

## 业务逻辑（implement）

- [x] 服务侧实现四类型发布校验（moment/photo/video/article）
- [x] 服务侧实现 `published` 后内容不可变（仅允许删除与分发关系变更）
- [x] 实现作者分发关系增删（发布后可变更圈子）
- [x] 实现转发/引用关系独立落库（与作者主动分发区分）
- [x] 实现删除级联下架（作者分发 + 用户转发）
- [x] 实现 tombstone 查询分支（已删除 vs 不存在）
- [x] 实现视频封面策略（默认首帧 + 手工覆盖）
- [x] 实现媒体元数据提取入库（图片/视频分辨率、大小、时长）
- [x] 实现设备与发布地点信息入库

## 测试（mock/unit/contract/integration/uat）

- [x] mock：四类型 payload 构造与错误码映射
- [x] unit：发布校验、不可变校验、分发/转发状态机
- [x] contract：新增路由请求响应、错误码与幂等删除
- [x] integration：删除级联 + tombstone + 圈子流过滤
- [x] uat：创作到发布到圈子再删除的端到端回归

## 门禁（gate）

- [x] make build
- [x] make test-contract
- [x] make gate
- [x] make gate-full
