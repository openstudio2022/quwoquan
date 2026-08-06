package http

import (
	nethttp "net/http"

	operationsecurity "quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
)

// GeneratedOperationContractHandler applies the generated assistant descriptor
// table to every inbound assistant route, not only the privileged ones: the
// declared reliability.timeout_ms is only a real budget where this middleware
// runs, so persona routes without it were bounded by nothing but the transport.
//
// Commercial fail-closed stays at api-edge. Inside the owner process a blocked
// operation must remain callable, otherwise it can never produce the candidate
// evidence that turns it ready.
func GeneratedOperationContractHandler(next nethttp.Handler) nethttp.Handler {
	return rtauth.EnforceRuntimeOperationContract(
		operationsecurity.ForDomain("assistant"),
	)(next)
}

func GeneratedOperationPathTemplateResolver() func(*nethttp.Request) string {
	return rtauth.NewOperationPathTemplateResolver(
		operationsecurity.ForDomain("assistant"),
	)
}

// AssistantOperationDescriptors exposes the generated table to the composition
// root so transport ceilings are derived from the same descriptors that carry
// the operation budgets.
func AssistantOperationDescriptors() []rtauth.OperationSecurityDescriptor {
	return operationsecurity.ForDomain("assistant")
}
