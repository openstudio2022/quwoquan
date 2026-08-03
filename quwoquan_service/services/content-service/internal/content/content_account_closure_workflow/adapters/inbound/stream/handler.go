package stream

import (
	"context"

	closureapp "quwoquan_service/services/content-service/internal/content/content_account_closure_workflow/application"
	closuremodel "quwoquan_service/services/content-service/internal/content/content_account_closure_workflow/domain/model"
)

// Handler is the canonical typed subscription entrypoint between the Redis
// transport consumer and the workflow application facade.
type Handler struct {
	ingress *closureapp.Ingress
}

func NewHandler(ingress *closureapp.Ingress) *Handler {
	if ingress == nil {
		panic("ContentAccountClosureWorkflow stream handler requires ingress")
	}
	return &Handler{ingress: ingress}
}

func (handler *Handler) Apply(
	ctx context.Context,
	event closuremodel.UserAccountClosedEvent,
) (closureapp.ApplyResult, error) {
	return handler.ingress.Apply(ctx, event)
}
