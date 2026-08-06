package operationguard

import (
	"net/http"

	"quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
)

// Handler applies the generated entity-domain operation contract on the service
// process boundary: verified principal, authorization, idempotency, version
// precondition and the declared reliability.timeout_ms deadline.
// Keeping this outside cmd makes the runtime authorization boundary directly
// testable without duplicating generated route decisions.
//
// Commercial fail-closed stays at api-edge; inside the owner process a blocked
// operation must remain callable so its release evidence can be produced.
func Handler(next http.Handler) http.Handler {
	return rtauth.EnforceRuntimeOperationContract(
		operationsecurity.ForDomain("entity"),
	)(next)
}

// Descriptors exposes the generated table so the composition root derives its
// transport ceilings from the same operation budgets this guard enforces.
func Descriptors() []rtauth.OperationSecurityDescriptor {
	return operationsecurity.ForDomain("entity")
}
