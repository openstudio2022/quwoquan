package ports

import (
	"context"
	"time"

	"quwoquan_service/services/integration-service/internal/external_integration/connector_invocation/domain/model"
)

type Reader interface {
	Get(context.Context, string, string) (model.Invocation, error)
	List(context.Context, string, string, int) ([]model.Invocation, error)
}

type Store interface {
	Reader
	Accept(context.Context, model.AcceptCommand) (model.MutationResult, error)
	Continue(context.Context, model.ContinueInput) (model.MutationResult, error)
}

type WorkerStore interface {
	ClaimNext(context.Context, string, time.Time, time.Duration) (model.ExecutionClaim, bool, error)
	Complete(context.Context, model.CompleteInput) (model.MutationResult, error)
}
