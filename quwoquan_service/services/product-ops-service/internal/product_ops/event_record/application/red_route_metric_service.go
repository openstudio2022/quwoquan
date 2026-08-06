package application

import (
	"context"
	"fmt"
	"sort"
	"strconv"
	"strings"
)

// serviceRouteREDItem 是单个接口的 RED 指标行（每接口平均/P99 延迟、流量、成功率）。
type ServiceRouteREDItem struct {
	Service     string  `json:"service"`
	Route       string  `json:"route"`
	Method      string  `json:"method,omitempty"`
	QPS         float64 `json:"qps"`
	AvgMs       float64 `json:"avgMs"`
	P99Ms       float64 `json:"p99Ms"`
	SuccessRate float64 `json:"successRatePercent"`
}

type ServiceRouteREDResponse struct {
	Items  []ServiceRouteREDItem `json:"items"`
	Window string                `json:"window"`
	Source string                `json:"source"`
}

// GetServiceRouteRED 按 route 下钻服务 RED：数据源是 Prometheus 的
// http_server_requests_total / http_server_duration_seconds（service+route 维度）。
func (s *MetricQueryService) GetServiceRouteRED(
	ctx context.Context,
	service string,
) (ServiceRouteREDResponse, error) {
	vectorQuery, ok := s.prometheus.(PrometheusVectorQuery)
	if s.prometheus == nil || !ok {
		return ServiceRouteREDResponse{}, fmt.Errorf("prometheus reader is not configured")
	}
	service = strings.TrimSpace(service)
	if service == "" {
		return ServiceRouteREDResponse{}, ErrInvalidEventQuery
	}
	const window = "5m"
	selector := "{service=" + strconv.Quote(service) + "}"
	errorSelector := "{service=" + strconv.Quote(service) + `,status=~"5.."}`

	qps, err := queryRouteVector(ctx, vectorQuery,
		`sum(rate(http_server_requests_total`+selector+`[`+window+`])) by (route)`)
	if err != nil {
		return ServiceRouteREDResponse{}, err
	}
	errorRate, err := queryRouteVector(ctx, vectorQuery,
		`sum(rate(http_server_requests_total`+errorSelector+`[`+window+`])) by (route)`)
	if err != nil {
		return ServiceRouteREDResponse{}, err
	}
	avgMs, err := queryRouteVector(ctx, vectorQuery,
		`1000 * sum(rate(http_server_duration_seconds_sum`+selector+`[`+window+`])) by (route)`+
			` / (sum(rate(http_server_duration_seconds_count`+selector+`[`+window+`])) by (route) + 0.000001)`)
	if err != nil {
		return ServiceRouteREDResponse{}, err
	}
	p99Ms, err := queryRouteVector(ctx, vectorQuery,
		`1000 * histogram_quantile(0.99, sum(rate(http_server_duration_seconds_bucket`+selector+`[`+window+`])) by (le, route))`)
	if err != nil {
		return ServiceRouteREDResponse{}, err
	}

	routes := map[string]*ServiceRouteREDItem{}
	ensure := func(route string) *ServiceRouteREDItem {
		if item, exists := routes[route]; exists {
			return item
		}
		item := &ServiceRouteREDItem{Service: service, Route: route, SuccessRate: 100}
		routes[route] = item
		return item
	}
	for route, value := range qps {
		ensure(route).QPS = value
	}
	for route, value := range avgMs {
		ensure(route).AvgMs = value
	}
	for route, value := range p99Ms {
		ensure(route).P99Ms = value
	}
	for route, value := range errorRate {
		item := ensure(route)
		if item.QPS > 0 {
			item.SuccessRate = 100 * (1 - value/item.QPS)
			if item.SuccessRate < 0 {
				item.SuccessRate = 0
			}
		}
	}
	items := make([]ServiceRouteREDItem, 0, len(routes))
	for _, item := range routes {
		items = append(items, *item)
	}
	sort.Slice(items, func(i, j int) bool { return items[i].QPS > items[j].QPS })
	return ServiceRouteREDResponse{
		Items:  items,
		Window: window,
		Source: "prometheus",
	}, nil
}

func queryRouteVector(
	ctx context.Context,
	reader PrometheusVectorQuery,
	expression string,
) (map[string]float64, error) {
	samples, err := reader.QueryVector(ctx, expression)
	if err != nil {
		return nil, err
	}
	out := make(map[string]float64, len(samples))
	for _, sample := range samples {
		route := strings.TrimSpace(sample.Labels["route"])
		if route == "" {
			continue
		}
		out[route] = sample.Value
	}
	return out, nil
}
