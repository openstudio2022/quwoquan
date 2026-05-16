# Media Object Key 与 URL 规范

## 1. 目标

统一媒体对象命名、切片路由、版本失效与 CDN URL 生成规则。

## 2. objectKey 规则

标准格式：

```text
{domain}/{assetKind}/s/{sliceId}/{ownerType}/{ownerId}/{assetId}_{variant}.{ext}
```

其中：

- `sliceId` 为媒体服务写入时统一分配的稳定切片标识。
- 路由层必须优先通过 URL / objectKey 中的 `sliceId` 解析目标切片。
- 切片满载后由媒体服务自动顺延到下一个 writable slice，既有 objectKey 不回写、不搬家。

## 3. 命名要求

- `domain`：`media` / `user` / `chat` / `content`
- `variant`：`origin` / `thumb` / `grid128` / `cover` 等
- `ext`：统一使用处理后文件的最终格式
- `sliceId`：例如 `avatar-seed-0001`、`image-hot-0042`

## 3.1 兼容阶段

- 历史 fixture 仍存在 `media/avatar/...`、`media/image/...` 等 legacy 路径时，路由层允许按 prefix 回落到固定 legacy slice。
- 新增写入链路、`quwoquan_data` 冷启动与未来对象存储导入必须直接产出显式 `sliceId` 版本 objectKey。

## 4. URL 规则

公开资源：

```text
https://{cdnDomain}/{objectKey}?v={version}
```

私有资源：

```text
https://{cdnDomain}/{objectKey}?v={version}&sign=...&t=...
```

## 5. 切片路由

一次请求的标准路由过程：

1. 从 URL 提取 `objectKey`
2. 解析 `/s/{sliceId}/`
3. 查询 `media slice registry`
4. 得到 `originType / originBaseUrl / localRoot / failover`
5. 由路由层回源或本地读取

明确禁止逐图片维护 `imageId -> origin` 路由表。

## 6. 版本失效

头像与封面类资源推荐使用：

- 新对象 key + 新 version

而不是覆盖原对象后强刷 CDN。

## 7. 禁止项

- 使用用户上传的原始文件名作为 objectKey 主体
- objectKey 中直接暴露敏感业务信息
- 业务服务自定义第二套路径规则
- 用 `yyyy/mm/dd` 作为主路由分片键
- 为每个图片单独维护不可推导的路由元数据
