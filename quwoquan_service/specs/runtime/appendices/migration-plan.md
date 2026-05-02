# 迁移计划

## Phase 1：冻结规范

- 冻结 runtime 总体边界
- 冻结媒体对象引用与 URL 规范
- 冻结用户同步流 patch 模型

## Phase 2：接入群头像

- `chat-service` 增加群头像字段
- 生成服务端预合成群头像
- 客户端改为只消费统一 `avatarUrl`

## Phase 3：接入用户头像版本化

- `user-service` 增加 `avatarVersion`
- 发布 `UserAvatarUpdated`
- 联系人与群组同步链路接入

## Phase 4：统一聊天媒体

- 聊天图片/视频/语音统一走 runtime media
- 增强上传完成后的资产派生

## Phase 5：扩展到内容媒体

- `content-service` 统一接入 runtime media
- 统一封面、转码、派生与 URL 规范
