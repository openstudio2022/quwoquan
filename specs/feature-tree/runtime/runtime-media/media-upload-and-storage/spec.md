# L3 Story：媒体上传与存储（Media Upload and Storage）

## 用户价值

用户选择照片、视频或其它持久媒体后，端侧必须以有界内存、可取消和可恢复的方式把
确定字节写入私有对象存储；服务端必须把一次上传会话、完成后的 `MediaAsset` 身份和
公开交付引用原子对账，断网、响应丢失或进程重启不能制造重复资产或孤儿发布。

## 功能范围

- 对象级 `MediaUploadSession` 命令/查询 Facet：Init、Complete、Abort、Get。
- 对象级 `MediaAsset` owner/public Reader，以及内部 storage object 与 canonical public
  slice 的分离。
- metadata `upload_policy.yaml` 驱动的媒体类型、MIME、大小与 `streaming_required` 校验。
- App `prepare/openRead + streaming PUT`，进度、取消、有限重试和 complete 丢响应回查。
- 上传/发布意图的持久恢复；业务 payload 只携带 `assetId`，不携带本地路径、CAS key、
  presigned URL 或瞬时 CDN URL。
- alpha/beta/gamma/prod 的 upload ingress、storage origin、delivery base 与证书/Range
  证据边界。

## Out of Scope

- 图片归一化、视频转码、封面和预览轨道由
  `discovery-content/media-processing-helper-read` 验收。
- 实时流媒体、CDN 边缘计算和多云自动切换。

## 架构约束

- 不创建跨对象泛型 `MediaStore` 或运行时动态选厂；各业务对象经窄 port 使用其明确
  adapter，存储 SDK 只存在于 infrastructure。
- `MediaUploadSession completed` 必须持久化所创建的 `assetId`，使客户端在 complete
  响应丢失后可经 owner query 恢复。
- 内容发布禁止 `uploadBytes/uploadLocalPath`、UI 裸 HTTP 和整文件读入 Dart heap。
- 公开交付只认 runtime canonical key builder 与处理结果 descriptor，不维护第二套 path。
- 错误使用 metadata 生成的 `RuntimeFailure`；策略拒绝、取消、暂时不可用和不可恢复失败
  具有不同恢复动作和观测标签。
