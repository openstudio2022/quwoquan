# 上传会话与 CDN 分发 设计方案

> 本节点为 L4_story，设计决策继承自 L2 `runtime-media` design.md。

## 设计动因

MediaStore 的核心交付 Story。实现三段式上传会话（Init→Upload→Complete/Abort）和 CDN URL 签名分发。

## 上游输入评审

L2/L3 spec + design 完整，无阻断项。

## 方案对比

见 L2 design.md。选定统一 runtime/media 模块方案。

## 关键设计决策

### 三段式上传流程

```
端侧                              云侧                          OSS
  │                                 │                            │
  │─── InitUpload(opts) ──────────▶│                            │
  │                                 │── 策略校验                  │
  │                                 │── 生成 presigned URL ──────▶│
  │◀── {sessionId, uploadUrl} ─────│                            │
  │                                 │                            │
  │─── PUT file ─────────────────────────────────────────────────▶│
  │◀── 200 ──────────────────────────────────────────────────────│
  │                                 │                            │
  │─── CompleteUpload(sessionId) ──▶│                            │
  │                                 │── 验证文件存在               │
  │                                 │── 生成 CDN URL              │
  │                                 │── 持久化 MediaAsset          │
  │◀── {mediaId, cdnUrl} ─────────│                            │
```

### UploadSession MongoDB Schema

```
collection: media_upload_sessions
{
  _id: ObjectId,
  mediaId: string,
  category: string,
  ownerId: string,
  mediaType: string,
  mimeType: string,
  fileSizeBytes: int64,
  clientMeta: object,
  ossKey: string,
  status: string,       // initiated | completed | aborted | expired
  expiresAt: timestamp,
  createdAt: timestamp
}
index: { ownerId: 1, createdAt: -1 }
ttl: expiresAt (自动清理过期会话)
```

### MediaAsset MongoDB Schema

```
collection: media_assets
{
  _id: ObjectId,
  category: string,
  ownerId: string,
  mediaType: string,
  mimeType: string,
  originUrl: string,
  cdnUrl: string,
  thumbnailUrl: string,
  width: int,
  height: int,
  durationMs: int,
  fileSizeBytes: int64,
  clientMeta: object,
  status: string,       // uploaded | processing | ready | failed
  createdAt: timestamp
}
index: { ownerId: 1, category: 1, createdAt: -1 }
```

## 适用场景与约束

同 L2 design.md。

## 未来演进

同 L2 design.md。
