# 媒体上传与存储（Media Upload and Storage）

> **层级**：L3_subfeature（隶属 L2 `runtime-media`，L1 `runtime`）
> **状态**：specified

## 背景与动机

`runtime-media` 的核心子系统，负责媒体文件从端到云的上传、持久化存储和 CDN 分发。提供 `MediaStore` 接口和上传策略引擎，供 content-service、chat-service、circle-service 统一消费。

## 目标用户

- Go 服务开发者（通过 `MediaStore` 接口）
- Dart 端侧开发者（通过 `MediaUploadManager`）

## 功能范围

1. `MediaStore` 接口定义（InitUpload/CompleteUpload/AbortUpload/GetAsset/BatchGetAssets）
2. OSS presigned URL 上传适配器
3. CDN URL 签名与过期管理
4. 上传策略引擎（Category×MediaType→限制规则）
5. `MediaAsset` MongoDB 持久化
6. 端侧 `MediaUploadManager` + `MediaDownloadCache`

## 不做什么（Out of Scope）

- 媒体处理管线（转码、缩略图、波形提取）
- CDN 边缘计算
- 多云 OSS 自动切换

## 约束

- 遵循 `runtime` 模块模式
- OSS SDK 仅在 `runtime/media/` 内部使用
- 使用 `ModuleOSS`/`ModuleCDN` 错误体系

## 适用范围与约束

- **适用**：所有需要持久化的媒体文件上传/存储/分发
- **不适用**：实时流媒体、临时文件

## 验收重点

见子节点 L4 Story 的 acceptance.yaml。
