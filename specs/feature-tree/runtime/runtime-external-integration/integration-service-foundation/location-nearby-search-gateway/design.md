# Design: location-nearby-search-gateway

## 设计决策
- 端侧只请求 integration-service，服务内按配置选择百度/阿里。
- nearby/search 统一返回 `LocationPoi`，不暴露供应商差异。
- 错误语义统一映射为 runtime/errors 结构化错误码。

## 约束
- 仅提供列表，不涉及地图拖拽选点。
- 搜索请求为高频输入场景，需支持防抖与取消前序请求。
