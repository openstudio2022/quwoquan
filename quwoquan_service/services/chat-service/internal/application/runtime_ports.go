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

type RelationshipCapability struct {
	CanCreateDirectConversation bool
	CanSendMessage              bool
	HasFormalConversation       bool
	IsMutual                    bool
	IsBlocked                   bool
	IsBlockedBy                 bool
}

type RelationshipGate interface {
	GetCapability(ctx context.Context, viewerID, targetID string) (RelationshipCapability, error)
}

type GroupAvatarRecomputeTask struct {
	ConversationID string
	ActorID        string
	Trigger        string
}

type ConversationAvatarPatchTask struct {
	ConversationID   string
	ActorID          string
	Trigger          string
	Payload          map[string]any
	RecipientUserIDs []string
}

func requireGroupAvatarTaskScheduler(scheduler GroupAvatarTaskScheduler) GroupAvatarTaskScheduler {
	if scheduler == nil {
		panic("chat application requires GroupAvatarTaskScheduler")
	}
	return scheduler
}

type denyRelationshipGate struct{}

func (denyRelationshipGate) GetCapability(context.Context, string, string) (RelationshipCapability, error) {
	return RelationshipCapability{}, nil
}

func DenyRelationshipGate() RelationshipGate {
	return denyRelationshipGate{}
}

type allowRelationshipGate struct{}

func (allowRelationshipGate) GetCapability(context.Context, string, string) (RelationshipCapability, error) {
	return RelationshipCapability{
		CanCreateDirectConversation: true,
		CanSendMessage:              true,
		HasFormalConversation:       true,
		IsMutual:                    true,
	}, nil
}

func AllowRelationshipGateForTest() RelationshipGate {
	return allowRelationshipGate{}
}
