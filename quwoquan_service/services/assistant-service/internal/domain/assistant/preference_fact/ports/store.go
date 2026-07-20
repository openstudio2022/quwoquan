package ports

import (
	"context"
	"time"

	preferencemodel "quwoquan_service/services/assistant-service/internal/domain/assistant/preference_fact/model"
)

type UpsertInput struct {
	PreferenceID   string
	UserID         string
	Scope          preferencemodel.Scope
	ConversationID string
	Kind           preferencemodel.Kind
	Value          string
	SourceType     preferencemodel.SourceType
	Now            time.Time
}

type ListFilter struct {
	Scope          preferencemodel.Scope
	ConversationID string
	Status         preferencemodel.Status
	Limit          int
}

type StatusUpdate struct {
	Status             preferencemodel.Status
	RevokedAt          *time.Time
	RevocationDeadline *time.Time
	UpdatedAt          time.Time
}

type Reader interface {
	List(
		ctx context.Context,
		userID string,
		filter ListFilter,
	) ([]preferencemodel.Fact, error)
	ListActiveForRun(
		ctx context.Context,
		userID string,
		conversationID string,
		limitPerScope int,
	) ([]preferencemodel.Fact, error)
}

type Store interface {
	Upsert(
		ctx context.Context,
		input UpsertInput,
	) (preferencemodel.Fact, error)
	GetOwned(
		ctx context.Context,
		userID string,
		preferenceID string,
	) (preferencemodel.Fact, bool, error)
	UpdateStatus(
		ctx context.Context,
		userID string,
		preferenceID string,
		expectedVersion int64,
		update StatusUpdate,
	) (preferencemodel.Fact, bool, error)
}
