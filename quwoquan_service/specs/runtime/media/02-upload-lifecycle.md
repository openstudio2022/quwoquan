# 上传生命周期

## 1. 生命周期阶段

统一采用四阶段模型：

1. `init`
2. `upload`
3. `complete`
4. `abort`

## 2. init

服务端校验：

- `category`
- `ownerId`
- `contentType`
- `fileSize`

产出：

- `sessionId`
- `presignUrl`
- `objectKey`
- `expiresAt`

## 3. upload

客户端直传对象存储，不经过业务服务转发文件内容。

要求：

- 支持分片上传
- 支持中断恢复
- 大文件必须可续传

## 4. complete

上传完成后由业务服务确认，runtime 写入 `MediaAsset`。

产出：

- `assetId`
- `cdnUrl`
- 派生信息

## 5. abort

用于：

- 用户取消上传
- 页面退出
- 过期会话清理

## 6. 生命周期约束

- `init` 必须幂等友好
- `complete` 必须防止重复入库
- `abort` 允许最终一致清理对象

## 7. 适用场景

- 用户头像上传
- 内容图片上传
- 聊天视频上传

群头像预合成不走客户端上传，而走服务端内部生成再入库。
