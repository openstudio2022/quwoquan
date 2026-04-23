# Media Object Key 与 URL 规范

## 1. 目标

统一媒体对象命名、路径组织、版本失效与 CDN URL 生成规则。

## 2. objectKey 规则

标准格式：

```text
{domain}/{assetKind}/{yyyy}/{mm}/{dd}/{ownerType}/{ownerId}/{assetId}_{variant}.{ext}
```

## 3. 命名要求

- `domain`：`user` / `chat` / `content`
- `variant`：`origin` / `thumb` / `grid128` / `cover` 等
- `ext`：统一使用处理后文件的最终格式

## 4. URL 规则

公开资源：

```text
https://{cdnDomain}/{objectKey}?v={version}
```

私有资源：

```text
https://{cdnDomain}/{objectKey}?v={version}&sign=...&t=...
```

## 5. 版本失效

头像与封面类资源推荐使用：

- 新对象 key + 新 version

而不是覆盖原对象后强刷 CDN。

## 6. 禁止项

- 使用用户上传的原始文件名作为 objectKey 主体
- objectKey 中直接暴露敏感业务信息
- 业务服务自定义第二套路径规则
