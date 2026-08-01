package ports

import (
	"context"

	"quwoquan_service/services/assistant-service/internal/assistant/page_context/domain/model"
)

type Store interface {
	Put(context.Context, model.PageContext) error
	Get(context.Context, string) (*model.PageContext, error)
}
