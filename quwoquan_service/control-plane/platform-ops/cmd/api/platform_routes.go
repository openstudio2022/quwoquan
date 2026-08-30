package main

import "net/http"

// newServerMux 只挂领域路由。/healthz、/readyz 与 /metrics 由骨架统一装配，
// 服务侧不得覆盖（覆盖会把浅存活与深就绪重新混成一件事）。
func newServerMux(service *platformService) *http.ServeMux {
	mux := http.NewServeMux()
	mux.HandleFunc(configAckConvergencePath, service.handleConfigAckConvergence)
	for _, route := range []struct {
		path    string
		handler http.Handler
	}{
		{"/control-plane/platform/catalog/services", service.configTopology},
		{"/control-plane/platform/topology/planes", service.configTopology},
		{"/control-plane/platform/topology/prod-plane-access-isolation", service.configTopology},
		{"/control-plane/platform/topology/environments", service.configTopology},
		{"/control-plane/platform/topology/clusters", service.configTopology},
		{"/control-plane/platform/rollout/routing-policy", service.configTopology},
		{"/control-plane/platform/topology/services", service.configInstanceRuntime},
		{"/control-plane/platform/topology/instances", service.configInstanceRuntime},
		{alertIngestPath, service.configInstanceRuntime},
		{"/control-plane/platform/alerts/active", service.configInstanceRuntime},
		{"/control-plane/platform/alerts/", service.configInstanceRuntime},
		{"/control-plane/platform/audits", service.configInstanceRuntime},
		{"/control-plane/platform/approvals", service.configInstanceRuntime},
		{"/control-plane/platform/projections/summary", service.configInstanceRuntime},
		{"/control-plane/platform/triage/summary", service.configInstanceRuntime},
		{"/control-plane/platform/releases", service.configInstanceRuntime},
		{"/control-plane/platform/configs", service.configLayers},
		{"/control-plane/platform/configs/resolve", service.configLayers},
		{resolveForInstancePath, service.configLayers},
		{"/control-plane/platform/configs/snapshot", service.configLayers},
		{"/control-plane/platform/configs/domains", service.configLayers},
		{"/control-plane/platform/configs/instances", service.configInstanceReports},
		{"/control-plane/platform/configs/instances/", service.configInstanceReports},
	} {
		mux.Handle(route.path, route.handler)
	}
	return mux
}
