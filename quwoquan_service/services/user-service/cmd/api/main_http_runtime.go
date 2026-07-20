package main

import (
	"net/http"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	rthealth "quwoquan_service/runtime/health"
	rtmetrics "quwoquan_service/runtime/metrics"
	httpadapter "quwoquan_service/services/user-service/internal/adapters/http"
)

// buildUserHTTPMux 只收口 transport handler 绑定；业务 operation 路径继续消费
// generated adapter 常量与 operation security descriptor，不维护第二套路由表。
func buildUserHTTPMux(handler http.Handler, healthChecker *rthealth.Checker) *http.ServeMux {
	outerMux := http.NewServeMux()
	outerMux.HandleFunc("/healthz", healthChecker.Handler())
	outerMux.Handle("/metrics", rtmetrics.Handler())
	outerMux.Handle(
		httpadapter.LoginAnonymousPath,
		rtauth.RequireGeneratedOperationAuthorizationForRoute(
			operationsecurity.ForDomain("user"),
			http.MethodPost,
			httpadapter.LoginAnonymousPath,
		)(handler),
	)
	outerMux.Handle(
		httpadapter.PullUserSyncPath,
		rtauth.RequireGeneratedOperationAuthorizationForRoute(
			operationsecurity.ForDomain("user"),
			http.MethodPost,
			httpadapter.PullUserSyncPath,
		)(handler),
	)
	outerMux.Handle(
		"/",
		rtauth.EnforceGeneratedOperationAuthorization(
			operationsecurity.ForDomain("user"),
		)(handler),
	)
	return outerMux
}
