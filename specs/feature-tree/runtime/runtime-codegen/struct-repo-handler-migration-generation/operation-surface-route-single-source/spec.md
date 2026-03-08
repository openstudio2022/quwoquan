# L4 细节：operation-surface-route-single-source

## 背景与动机

当前端云两侧虽然已经部分通过 metadata + codegen 生成 API path、DTO、错误码与部分请求 pageId，但仍存在三类“第二真相源”：

- `service.yaml` 之外的代码 override map 决定 operation 对应的请求标识
- `app_router.dart` 直接硬编码业务 route path
- `CloudResponseDecoder.context`、部分请求 header、部分媒体上传入口继续使用字符串字面量

这类问题的根因不是单一业务域实现问题，而是 **元数据和代码生成尚未把 operation / surface / route 统一收口**。因此本特性归属于 `runtime-codegen`，负责把这类跨端、跨域的业务标识统一定义、统一生成、统一守门。

## 功能范围

- 扩展 metadata schema，明确：
  - `operation_id`
  - `surface_id`
  - `route_id`
  - `path_template`
  - `decoder_context_id`
- 扩展 codegen，生成：
  - operation 常量
  - surface 常量
  - route/path 常量与 builder
  - 请求头与 decoder context 所需的辅助常量
- 约束 App Router、Repository、测试、网关传播链路全部消费生成产物
- 增加 semantic gate，阻断新增硬编码业务标识

## 不做什么

- 不负责设计网关内部 trace 存储模型
- 不负责接管 UI 视觉布局配置
- 不在本特性内引入运行时远程下载路由表

## 约束

- metadata 是唯一真相源
- codegen 产物一律 `DO NOT EDIT`
- 业务代码不得再维护 route/page/surface/operation override 表
- 迁移期间允许兼容旧 `X-Client-Page-Id`，但值也必须来自 codegen

## 验收重点

- 所有 operation / surface / route 都有明确 metadata 归属
- codegen 能生成端云两侧共同消费的常量
- App Router、Repository、CloudRequestHeaders、CloudResponseDecoder 不再手写业务字符串
- gate 能持续阻断回退
