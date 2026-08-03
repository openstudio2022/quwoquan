package ports

import (
	"context"

	"quwoquan_service/services/integration-service/internal/external_integration/connector_connection/domain/model"
)

type Reader interface {
	Get(context.Context, string, string) (model.Connection, error)
	List(context.Context, string, int) ([]model.Connection, error)
}

type Store interface {
	Reader
	Replay(context.Context, string, string, string, string) (model.MutationResult, bool, error)
	Create(context.Context, model.CreateCommand) (model.MutationResult, error)
	Revoke(context.Context, model.RevokeInput) (model.MutationResult, error)
}
