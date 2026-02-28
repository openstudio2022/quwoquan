# L3 特性：integration-service-foundation

## 功能说明
- 定义 integration-service 的服务边界、目录结构、配置规范与调用契约。
- 首批承载 location 能力，后续作为公共外部集成入口复用。

## 约束
- 服务必须遵循 metadata-first 与 DDD 单向依赖。
- 对外只暴露标准化接口，禁止端侧直接调用供应商 API。

## 验收标准
- A1：服务目录与配置分层符合规范。
- A7：服务契约与 metadata 一致。
