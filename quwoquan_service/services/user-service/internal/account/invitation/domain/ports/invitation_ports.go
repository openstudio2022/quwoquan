package ports

import (
	"context"
	"errors"
	"time"

	invitationmodel "quwoquan_service/services/user-service/internal/account/invitation/domain/model"
)

var (
	ErrNotFound   = errors.New("invitation not found")
	ErrDailyLimit = errors.New("invitation daily limit exceeded")
)

type InvitationStore interface {
	Generate(
		ctx context.Context,
		invitation *invitationmodel.Invitation,
		dailyLimit int,
	) (stored *invitationmodel.Invitation, created bool, err error)
	FindByLinkCode(ctx context.Context, linkCode string) (*invitationmodel.Invitation, error)
	ListByInviter(
		ctx context.Context,
		inviterSubAccountID string,
		status string,
		limit int,
		offset int,
	) ([]invitationmodel.Invitation, error)
	MarkDelivered(ctx context.Context, linkCode string, now time.Time) (*invitationmodel.Invitation, error)
	Accept(ctx context.Context, linkCode string, now time.Time) (*invitationmodel.Invitation, error)
}

type PersonaOwnerReader interface {
	ResolveOwnerAccountID(
		ctx context.Context,
		subAccountID string,
	) (accountID string, found bool, err error)
}
