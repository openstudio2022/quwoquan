package application

import "context"

// PrometheusQuery 是 L3/L4 服务 SLI 的只读端口。产品事件仓库不得冒充
// HTTP RED；调用方只能请求已登记的 PromQL，并接收单值结果。
type PrometheusQuery interface {
	Query(ctx context.Context, expression string) (float64, error)
}

// PrometheusVectorSample 是带标签的即时向量样本（每接口 RED 下钻用）。
type PrometheusVectorSample struct {
	Labels map[string]string `json:"labels"`
	Value  float64           `json:"value"`
}

// PrometheusVectorQuery 返回多序列即时向量（如 by (route) 分组的 RED 指标）。
type PrometheusVectorQuery interface {
	QueryVector(ctx context.Context, expression string) ([]PrometheusVectorSample, error)
}
