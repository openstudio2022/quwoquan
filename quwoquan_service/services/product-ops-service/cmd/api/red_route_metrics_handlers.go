package main

import (
	"context"
	"net/http"
	"sort"
	"strconv"
	"strings"

	"quwoquan_service/services/product-ops-service/internal/application"
	productopsgenerated "quwoquan_service/services/product-ops-service/internal/generated"
)

// serviceRouteREDItem 是单个接口的 RED 指标行（每接口平均/P99 延迟、流量、成功率）。
type serviceRouteREDItem struct {
	Service     string  `json:"service"`
	Route       string  `json:"route"`
	Method      string  `json:"method,omitempty"`
	QPS         float64 `json:"qps"`
	AvgMs       float64 `json:"avgMs"`
	P99Ms       float64 `json:"p99Ms"`
	SuccessRate float64 `json:"successRatePercent"`
}

type serviceRouteREDResponse struct {
	Items  []serviceRouteREDItem `json:"items"`
	Window string                `json:"window"`
	Source string                `json:"source"`
}

// handleGetServiceRouteRED 按 route 下钻服务 RED：数据源是 Prometheus 的
// http_server_requests_total / http_server_duration_seconds（service+route 维度）。
func (s *productService) handleGetServiceRouteRED(w http.ResponseWriter, r *http.Request) {
	vectorQuery, ok := s.prometheus.(application.PrometheusVectorQuery)
	if s.prometheus == nil || !ok {
		writeEventAppError(w, r, productopsgenerated.AppErrorFromLogstoreUnavailable("prometheus reader is not configured"))
		return
	}
	service := strings.TrimSpace(r.URL.Query().Get("service"))
	if service == "" {
		writeEventAppError(w, r, productopsgenerated.AppErrorFromQueryWindowInvalid("service is required"))
		return
	}
	const window = "5m"
	selector := "{service=" + strconv.Quote(service) + "}"
	errorSelector := "{service=" + strconv.Quote(service) + `,status=~"5.."}`

	qps, err := queryRouteVector(r.Context(), vectorQuery,
		`sum(rate(http_server_requests_total`+selector+`[`+window+`])) by (route)`)
	if err != nil {
		writeEventAppError(w, r, productopsgenerated.AppErrorFromLogstoreUnavailable(err.Error()))
		return
	}
	errorRate, err := queryRouteVector(r.Context(), vectorQuery,
		`sum(rate(http_server_requests_total`+errorSelector+`[`+window+`])) by (route)`)
	if err != nil {
		writeEventAppError(w, r, productopsgenerated.AppErrorFromLogstoreUnavailable(err.Error()))
		return
	}
	avgMs, err := queryRouteVector(r.Context(), vectorQuery,
		`1000 * sum(rate(http_server_duration_seconds_sum`+selector+`[`+window+`])) by (route)`+
			` / (sum(rate(http_server_duration_seconds_count`+selector+`[`+window+`])) by (route) + 0.000001)`)
	if err != nil {
		writeEventAppError(w, r, productopsgenerated.AppErrorFromLogstoreUnavailable(err.Error()))
		return
	}
	p99Ms, err := queryRouteVector(r.Context(), vectorQuery,
		`1000 * histogram_quantile(0.99, sum(rate(http_server_duration_seconds_bucket`+selector+`[`+window+`])) by (le, route))`)
	if err != nil {
		writeEventAppError(w, r, productopsgenerated.AppErrorFromLogstoreUnavailable(err.Error()))
		return
	}

	routes := map[string]*serviceRouteREDItem{}
	ensure := func(route string) *serviceRouteREDItem {
		if item, exists := routes[route]; exists {
			return item
		}
		item := &serviceRouteREDItem{Service: service, Route: route, SuccessRate: 100}
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
	items := make([]serviceRouteREDItem, 0, len(routes))
	for _, item := range routes {
		items = append(items, *item)
	}
	sort.Slice(items, func(i, j int) bool { return items[i].QPS > items[j].QPS })
	writeJSON(w, http.StatusOK, serviceRouteREDResponse{
		Items:  items,
		Window: window,
		Source: "prometheus",
	})
}

func queryRouteVector(
	ctx context.Context,
	reader application.PrometheusVectorQuery,
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
