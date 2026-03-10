# L4 特性：location-nearby-search-gateway

## 功能说明
- 提供 `/v1/integration/location/nearby` 与 `/v1/integration/location/search` 标准接口。
- 全量通过云端获取附近列表与搜索结果，端侧不直接调用百度/阿里。

## 适用范围与约束
- 不做地图选点，仅做附近列表与关键词检索。
- 限流场景对用户无感：端侧保持当前列表，不额外弹出“操作太频繁”提示。

## 验收标准
- A1：附近列表接口契约完成并可验证。
- A2：搜索接口契约完成并支持实时输入更新（客户端防抖）。
- A3：错误码覆盖定位不可用、上游超时、服务不可用等场景。
- A4：LocationPoi 端侧解析元数据驱动，禁止硬编码字段名；与 content 域 DTO 模式一致，make verify-metadata + make codegen-app 通过。
- A5：云侧抛出异常时，code 与 user_message 统一定义于 errors.yaml，生成 Go 文件可直接使用（无硬编码）。
