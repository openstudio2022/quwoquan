# 第二阶段：物理媒体压缩到 100 张内

## 目标

在不改变业务 `objectKey`、fixture id 和逻辑实体规模的前提下，把真实二进制媒体数量压到 `<=100`，同时仍支持约 `1000` 个逻辑实体 / post / conversation 使用稳定 URL。

## 核心原则

- 逻辑对象数量与物理文件数量解耦。
- 业务数据仍只保存 `objectKey`、`version`、`hash`、`assetId`。
- 复用发生在媒体层，不发生在业务 DTO / seedRef 层。
- 不新增图片级路由表。

## 推荐做法

1. 维护 `<100` 张基础底图池，按 `avatar / background / cover / inline-image` 划分。
2. 逻辑 objectKey 继续按现有命名生成，但落盘时通过以下任一方式复用：
   - hard link
   - symlink
   - object storage copy-on-write / server-side copy
   - `objectKey -> baseAssetId` 的低频别名清单
3. UI 场景需要更多“看起来不同”的效果时，只在展示层做：
   - 不同裁剪窗口
   - 轻量色调 / 模糊 / overlay
   - 群头像组合

## 不采用

- 为每个逻辑实体保留一份独立物理 PNG/JPG
- 为每张图片单独写路由元数据
- 在 alpha / beta / gamma 分别维护三套不同图片池

## 环境收益

- `alpha`：本地磁盘扫描和 fixture 管理明显减小。
- `beta`：启动脚本不再因为媒体目录体积放大 IO。
- `gamma`：本机公网回源和未来对象存储成本一起下降。

## 与切片注册表的关系

- `sliceId` 仍决定请求应去哪个 origin。
- 物理复用发生在该 origin 内部。
- 也就是说：`sliceId -> origin` 不变，`objectKey -> baseAsset` 可以在 origin 内部实现，但不能倒逼客户端改变 URL。

## 准入条件

- 先完成显式 `sliceId` 路由与 `media slice registry`
- 再做基础底图池与别名策略
- 最后才切换 shared pool pipeline，避免在旧路由模型上同时做两类迁移
