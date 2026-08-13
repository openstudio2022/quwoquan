package invitation_test

import (
	"context"
	"errors"
	"testing"
	"time"

	runtimeerrors "quwoquan_service/runtime/errors"
	invitationapp "quwoquan_service/services/user-service/internal/account/invitation/application"
	invitationmodel "quwoquan_service/services/user-service/internal/account/invitation/domain/model"
	invitationports "quwoquan_service/services/user-service/internal/account/invitation/domain/ports"
)

func assertInvitationErrorCode(t *testing.T, err error, wantCode string) {
	t.Helper()
	var appErr *runtimeerrors.AppError
	if !errors.As(err, &appErr) || appErr.Code.String() != wantCode {
		t.Fatalf("expected %s, got %T: %v", wantCode, err, err)
	}
}

type invitationDailyLimitStore struct {
	invitationMemoryStore
}

func (store *invitationDailyLimitStore) Generate(
	_ context.Context,
	_ *invitationmodel.Invitation,
	_ int,
	_ invitationports.CommandIdentity,
) (*invitationmodel.Invitation, bool, error) {
	return nil, false, invitationports.ErrDailyLimit
}

func TestInvitationGenerateSurfacesDailyLimitExceeded(t *testing.T) {
	facade, err := invitationapp.NewFacade(
		&invitationDailyLimitStore{},
		invitationPersonaOwners{"persona-owner": "account-owner"},
	)
	if err != nil {
		t.Fatalf("create facade: %v", err)
	}

	_, err = facade.Generate(
		context.Background(),
		"account-owner",
		"persona-owner",
		"direct",
		"13800138000",
		"generate-over-limit",
	)
	assertInvitationErrorCode(t, err, "USER.INVITATION.daily_limit_exceeded")
}

func TestInvitationGetByCodeSurfacesNotFoundForUnknownLinkCode(t *testing.T) {
	facade, err := invitationapp.NewFacade(
		&invitationMemoryStore{},
		invitationPersonaOwners{"persona-owner": "account-owner"},
	)
	if err != nil {
		t.Fatalf("create facade: %v", err)
	}

	_, err = facade.GetByCode(context.Background(), "unknown-link-code")
	assertInvitationErrorCode(t, err, "USER.INVITATION.not_found")
}

func TestInvitationGetByCodeSurfacesExpiredBeforeDelivery(t *testing.T) {
	now := time.Now().UTC()
	expired := validInvitation(now)
	expired.ExpireAt = now.Add(-time.Minute)
	store := &invitationMemoryStore{record: expired}
	facade, err := invitationapp.NewFacade(
		store,
		invitationPersonaOwners{"persona-owner": "account-owner"},
	)
	if err != nil {
		t.Fatalf("create facade: %v", err)
	}

	_, err = facade.GetByCode(context.Background(), expired.LinkCode)
	assertInvitationErrorCode(t, err, "USER.INVITATION.expired")
}

func TestInvitationAcceptSurfacesInvalidTransitionFromRevokedState(t *testing.T) {
	now := time.Now().UTC()
	stale := validInvitation(now)
	stale.Status = invitationmodel.StatusRevoked
	store := &invitationMemoryStore{record: stale}
	facade, err := invitationapp.NewFacade(
		store,
		invitationPersonaOwners{"persona-owner": "account-owner"},
	)
	if err != nil {
		t.Fatalf("create facade: %v", err)
	}

	_, err = facade.Accept(
		context.Background(),
		"account-acceptor",
		stale.LinkCode,
		"accept-revoked-invitation",
	)
	assertInvitationErrorCode(t, err, "USER.INVITATION.invalid_transition")
}
