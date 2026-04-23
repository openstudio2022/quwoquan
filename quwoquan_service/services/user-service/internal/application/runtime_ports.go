package application

import (
	"context"

	runtimesync "quwoquan_service/runtime/sync"
)

type UserEventPublisher interface {
	PublishUserEvent(ctx context.Context, eventType, userID, actorID string, payload map[string]any) error
}

type UserSyncStream interface {
	AppendPatch(ctx context.Context, userID string, patchType string, payload map[string]any) (runtimesync.Patch, error)
	Pull(ctx context.Context, userID string, afterSeq int64, limit int) (runtimesync.PullResponse, error)
}

type noopUserEventPublisher struct{}

func (noopUserEventPublisher) PublishUserEvent(context.Context, string, string, string, map[string]any) error {
	return nil
}

func NoopUserEventPublisher() UserEventPublisher { return noopUserEventPublisher{} }
