package main

import (
	"net/http"

	generatedcontrolplane "quwoquan_service/generated/control_plane"
	rtauth "quwoquan_service/runtime/auth"
)

// productOpsGeneratedOperationDescriptors is the only composition-level
// authorization table for Product Ops HTTP operations. The list is generated
// from canonical contracts; object handlers must not copy operation scopes or
// principal-role policy.
func productOpsGeneratedOperationDescriptors() []rtauth.OperationSecurityDescriptor {
	return append(
		[]rtauth.OperationSecurityDescriptor(nil),
		generatedcontrolplane.ProductOperationSecurityDescriptors...,
	)
}

func requireProductOpsGeneratedOperationAuthorization(
	next http.Handler,
) http.Handler {
	return rtauth.RequireGeneratedOperationAuthorization(
		productOpsGeneratedOperationDescriptors(),
	)(next)
}
