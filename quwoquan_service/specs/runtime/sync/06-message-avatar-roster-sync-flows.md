# 消息、头像与成员变更同步流程

## 1. 发消息

1. `chat-service` 写入消息并分配 seq
2. 更新收件箱投影
3. 生成 `message.created` patch
4. realtime 通知在线设备
5. 客户端按 cursor 拉增量

## 2. 用户改头像

1. `user-service` 更新 `avatarAssetId`
2. `avatarVersion + 1`
3. 发布 `UserAvatarUpdated`
4. 生成 `user.avatar.updated` patch
5. 相关联系人、本人多端消费 patch
6. `chat-service` 评估其所在群的前 9 是否受影响

## 3. 群成员加入/离开

1. `chat-service` 更新成员表
2. 发布 `MemberJoined` / `MemberLeft`
3. 更新 `membersRosterRevision`
4. 生成 `conversation.roster.updated` patch
5. 若前 9 变化，则触发群头像重算

## 4. 群头像更新

1. 群头像重算任务完成
2. `groupAvatarVersion + 1`
3. 发布 `ConversationAvatarUpdated`
4. 生成 `conversation.avatar.updated` patch
5. 相关成员客户端刷新列表与会话头部

## 5. 已读变化

1. `MarkAsRead`
2. 更新 read seq 与未读数
3. 生成 `receipt.updated` 或 `badge.updated`
4. 客户端刷新局部状态
