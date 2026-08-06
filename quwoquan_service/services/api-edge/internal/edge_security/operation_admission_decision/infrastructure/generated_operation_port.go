package infrastructure

import (
	"net/http"

	rtauth "quwoquan_service/runtime/auth"
)

// GeneratedOperationPort is the only adapter from the object-owned typed port
// to runtime/auth's generated, default-deny operation guard.
type GeneratedOperationPort struct {
	descriptors []rtauth.OperationSecurityDescriptor
}

func NewGeneratedOperationPort(
	descriptors []rtauth.OperationSecurityDescriptor,
) *GeneratedOperationPort {
	if len(descriptors) == 0 {
		panic("generated operation descriptors are required")
	}
	owned := append([]rtauth.OperationSecurityDescriptor(nil), descriptors...)
	return &GeneratedOperationPort{descriptors: owned}
}

func (port *GeneratedOperationPort) Wrap(next http.Handler) http.Handler {
	if port == nil || len(port.descriptors) == 0 {
		panic("generated operation admission port is not configured")
	}
	return rtauth.RequireGeneratedOperationAuthorization(port.descriptors)(next)
}
