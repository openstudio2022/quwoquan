package httpadapter

import (
	"net/http"

	"quwoquan_service/services/api-edge/internal/edge_security/operation_admission_decision/application"
)

// Middleware adapts the object-owned OperationAdmissionPort into the public
// HTTP boundary that sits after credential verification and before shared
// admission / owner proxy.
type Middleware struct {
	facade *application.Facade
}

func NewMiddleware(facade *application.Facade) *Middleware {
	if facade == nil {
		panic("operation admission facade is required")
	}
	return &Middleware{facade: facade}
}

func (middleware *Middleware) Wrap(next http.Handler) http.Handler {
	if middleware == nil || middleware.facade == nil {
		panic("operation admission middleware is not configured")
	}
	return middleware.facade.Wrap(next)
}
