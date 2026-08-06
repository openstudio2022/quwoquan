package main

import (
	"net/http"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
	rthealth "quwoquan_service/runtime/health"
	rtmetrics "quwoquan_service/runtime/metrics"
	httpadapter "quwoquan_service/services/user-service/internal/account/user_account/adapters/inbound/http"
)

// userOperationDescriptors 是 user 域 operation 预算的唯一来源，装配层的路由守卫
// 与传输层上限都从它派生。
func userOperationDescriptors() []rtauth.OperationSecurityDescriptor {
	return operationsecurity.ForDomain("user")
}

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
