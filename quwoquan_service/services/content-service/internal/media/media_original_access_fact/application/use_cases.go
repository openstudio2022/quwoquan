package application

import (
	"context"

	media "quwoquan_service/services/content-service/internal/content/post/application/media"
)

type Appender interface {
	RequestOriginalMediaAccess(context.Context, media.RequestOriginalMediaAccessCommand) (media.OriginalMediaAccessResult, error)
}

type UseCases struct{ appender Appender }

func NewUseCases(appender Appender) *UseCases {
	if appender == nil {
		panic("media original-access appender is required")
	}
	return &UseCases{appender: appender}
}

func (s *UseCases) Request(ctx context.Context, command media.RequestOriginalMediaAccessCommand) (media.OriginalMediaAccessResult, error) {
	return s.appender.RequestOriginalMediaAccess(ctx, command)
}
