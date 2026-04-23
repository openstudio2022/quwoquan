package application

import (
	"context"

	runtimemedia "quwoquan_service/runtime/media"
	runtimesync "quwoquan_service/runtime/sync"
)

type GroupAvatarAssetizer interface {
	Register(ctx context.Context, req runtimemedia.RegisterGroupAvatarRequest) (runtimemedia.DerivedAvatarAsset, error)
}

type UserSyncPublisher interface {
	AppendPatch(ctx context.Context, userID string, patchType string, payload map[string]any) (runtimesync.Patch, error)
	AppendPatchBatch(ctx context.Context, userIDs []string, patchType string, payload map[string]any) (runtimesync.BatchAppendResult, error)
}

type GroupAvatarTaskScheduler interface {
	EnqueueRecompute(ctx context.Context, task GroupAvatarRecomputeTask) error
	EnqueueConversationAvatarPatch(ctx context.Context, task ConversationAvatarPatchTask) error
}

type noopGroupAvatarTaskScheduler struct{}

func (noopGroupAvatarTaskScheduler) EnqueueRecompute(context.Context, GroupAvatarRecomputeTask) error {
	return nil
}

func (noopGroupAvatarTaskScheduler) EnqueueConversationAvatarPatch(context.Context, ConversationAvatarPatchTask) error {
	return nil
}

func NoopGroupAvatarTaskScheduler() GroupAvatarTaskScheduler {
	return noopGroupAvatarTaskScheduler{}
}
