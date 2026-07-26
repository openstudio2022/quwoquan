package operationguard

import (
	"net/http"

	"quwoquan_service/generated/operationsecurity"
	rtauth "quwoquan_service/runtime/auth"
)

// Handler applies the generated entity-domain operation authorization map.
// Keeping this outside cmd makes the runtime authorization boundary directly
// testable without duplicating generated route decisions.
func Handler(next http.Handler) http.Handler {
	return rtauth.RequireGeneratedOperationAuthorization(
		operationsecurity.ForDomain("entity"),
	)(next)
}
