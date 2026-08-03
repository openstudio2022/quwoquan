package ports

import (
	"context"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_surface_placement/domain/model"
)

type Reader interface {
	Get(context.Context, string, string) (model.Placement, error)
}

type Store interface {
	Reader
	Apply(context.Context, model.Command) (model.MutationResult, error)
}
