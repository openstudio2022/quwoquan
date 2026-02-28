# 开发任务：runtime-external-integration

## 当前交付任务
- [x] M1. 新建 `integration/location` 元数据五件套（aggregate/fields/storage/events/service）。
- [x] C1. 执行 metadata 验证与 codegen。
- [x] B1. 新建 `services/integration-service/` 服务骨架与分环境配置。
- [x] B2. 补齐服务规格文档与工程目录映射。
- [x] T1. 补齐最小契约测试计划与错误码映射计划。
- [x] B3. 地图供应商主备容灾：主用失败后自动尝试备用一次，两次失败才返回错误。
- [x] B4. 外部地图调用接入可观测日志（IO/Process/Exception）。
- [x] B5. nearby 接口支持默认中心点回退（端侧可不传 lat/lng）。

## 搁置任务（带规划）
- [ ] P1. 集成层统一鉴权（app/service token）细化。

## 未来演进任务
- [ ] F1. 扩展 sms/ocr 等外部能力。
