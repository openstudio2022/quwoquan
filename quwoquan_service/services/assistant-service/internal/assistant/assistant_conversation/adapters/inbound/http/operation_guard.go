package http

import (
	nethttp "net/http"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
)

// GeneratedPrivilegedOperationHandler applies the generated service/operator
// guards before dispatching privileged Assistant routes to their owner
// handlers. Public owner routes continue through the fallback unchanged.
func GeneratedPrivilegedOperationHandler(next nethttp.Handler) nethttp.Handler {
	descriptors := operationsecurity.ForDomain("assistant")
	mux := nethttp.NewServeMux()
	for _, descriptor := range descriptors {
		if descriptor.Principal != "service" && descriptor.Principal != "operator" {
			continue
		}
		guarded := rtauth.RequireGeneratedOperationAuthorizationForRoute(
			descriptors,
			descriptor.Method,
			descriptor.PathTemplate,
		)(next)
		mux.Handle(descriptor.Method+" "+descriptor.PathTemplate, guarded)
	}
	mux.Handle("/", next)
	return mux
}
