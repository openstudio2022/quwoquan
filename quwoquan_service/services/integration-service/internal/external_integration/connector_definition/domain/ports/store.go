package ports

import (
	"context"

	"quwoquan_service/services/integration-service/internal/external_integration/connector_definition/domain/model"
)

type Reader interface {
	Get(context.Context, string) (model.Definition, error)
	List(context.Context, string, int) ([]model.Definition, error)
}

type Store interface {
	Reader
	Publish(context.Context, model.PublishCommand) (model.MutationResult, error)
}
