package main

import (
	"net/http"

	generatedcontrolplane "quwoquan_service/generated/control_plane"
	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
)

// productOpsGeneratedOperationDescriptors is the only composition-level
// authorization table for Product Ops HTTP operations. The list is generated
// from canonical contracts; object handlers must not copy operation scopes or
// principal-role policy.
func productOpsGeneratedOperationDescriptors() []rtauth.OperationSecurityDescriptor {
	opsDescriptors := operationsecurity.ForDomain("ops")
	descriptors := make(
		[]rtauth.OperationSecurityDescriptor,
		0,
		len(opsDescriptors)+len(generatedcontrolplane.ProductOperationSecurityDescriptors),
	)
	descriptors = append(descriptors, opsDescriptors...)
	descriptors = append(
		descriptors,
		generatedcontrolplane.ProductOperationSecurityDescriptors...,
	)
	return descriptors
}

func requireProductOpsGeneratedOperationAuthorization(
	next http.Handler,
) http.Handler {
	return rtauth.RequireGeneratedOperationAuthorization(
		productOpsGeneratedOperationDescriptors(),
	)(next)
}
