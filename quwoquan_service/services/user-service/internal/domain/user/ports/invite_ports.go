package ports

import (
	"context"

	"quwoquan_service/services/user-service/internal/domain/user/model"
)

type InviteReader interface {
	FindByID(ctx context.Context, id string) (*model.InviteRecord, error)
	FindByLinkCode(ctx context.Context, linkCode string) (*model.InviteRecord, error)
	FindIdempotent(ctx context.Context, inviterSubAccountID, channel, inviteePhoneHash string) (*model.InviteRecord, error)
	ListByInviter(ctx context.Context, inviterSubAccountID, statusFilter string, limit, offset int) ([]model.InviteRecord, error)
	CountTodayByInviter(ctx context.Context, inviterSubAccountID string) (int, error)
}

type InviteWriter interface {
	Create(ctx context.Context, r *model.InviteRecord) error
	UpdateStatus(ctx context.Context, id, status string) error
	MarkDelivered(ctx context.Context, id string) error
	MarkViewed(ctx context.Context, id string) error
	Accept(ctx context.Context, id string) error
	Convert(ctx context.Context, id string) error
}
