package repository

import (
	"context"

	"quwoquan_service/services/user-service/internal/domain/user/model"
)

type GreetingRepository interface {
	Create(ctx context.Context, greeting *model.GreetingRequest) error
	Update(ctx context.Context, greeting *model.GreetingRequest) error
	FindByID(ctx context.Context, id string) (*model.GreetingRequest, error)
	FindPendingBetween(ctx context.Context, requesterID, targetID string) (*model.GreetingRequest, error)
	HasPendingBetween(ctx context.Context, subAccountA, subAccountB string) (bool, error)
	HasRepliedBetween(ctx context.Context, subAccountA, subAccountB string) (bool, error)
	ListInbox(ctx context.Context, targetID, status, cursor string, limit int) ([]model.GreetingRequest, string, error)
	ListOutbox(ctx context.Context, requesterID, status, cursor string, limit int) ([]model.GreetingRequest, string, error)
	MarkPendingBlockedBetween(ctx context.Context, subAccountA, subAccountB string) error
}
