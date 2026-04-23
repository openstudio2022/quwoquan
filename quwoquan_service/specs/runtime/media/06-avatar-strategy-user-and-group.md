# 用户头像与群头像策略

## 1. 用户头像

### 1.1 归属

- 归属 `user-service`
- 存储 `avatarAssetId`
- 维护 `avatarVersion`

### 1.2 更新策略

用户更换头像后：

1. 生成新资产
2. `avatarVersion + 1`
3. 发布 `UserAvatarUpdated`

## 2. 群头像

### 2.1 归属

- 归属 `chat-service`
- 存储 `groupAvatarAssetId`
- 维护 `groupAvatarVersion`
- 维护 `groupAvatarSourceHash`

### 2.2 生成策略

- 只取前 9 个成员
- 按加入顺序
- 服务端预合成
- 失败时客户端显示默认群图标

## 3. 更新触发

### 3.1 必重算

- `MemberJoined`
- `MemberLeft`
- `ConversationCreated`

### 3.2 异步重算

- 前 9 成员之一收到 `UserAvatarUpdated`

## 4. sourceHash

推荐计算：

```text
hash(top9UserIdsInOrder + top9AvatarVersions + layoutVersion)
```

若 hash 未变，则跳过重算。

## 5. 不做的事

- 不做端侧拼图兜底
- 不要求非前 9 成员变化触发重算
- 不允许客户端自己推导群头像
