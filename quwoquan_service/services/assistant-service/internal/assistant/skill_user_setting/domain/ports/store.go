package ports

import (
	"context"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_user_setting/domain/model"
)

type Reader interface {
	Get(context.Context, string, string) (model.Setting, error)
	List(context.Context, string, int) ([]model.Setting, error)
}

type Store interface {
	Reader
	Apply(context.Context, model.Command) (model.MutationResult, error)
}
