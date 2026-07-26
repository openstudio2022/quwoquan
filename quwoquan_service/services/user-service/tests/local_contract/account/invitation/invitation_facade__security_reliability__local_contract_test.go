package invitation_test

import (
	"context"
	"testing"
	"time"

	invitationapp "quwoquan_service/services/user-service/internal/account/invitation/application"
	invitationmodel "quwoquan_service/services/user-service/internal/account/invitation/domain/model"
	invitationports "quwoquan_service/services/user-service/internal/account/invitation/domain/ports"
)

func TestInvitationGenerateVerifiesPersonaOwnerAndStoresOnlyPhoneHash(t *testing.T) {
	store := &invitationMemoryStore{}
	facade, err := invitationapp.NewFacade(
		store,
		invitationPersonaOwners{"persona-owner": "account-owner"},
	)
	if err != nil {
		t.Fatalf("create facade: %v", err)
	}

	created, err := facade.Generate(
		context.Background(),
		"account-owner",
		"persona-owner",
		"direct",
		"13800138000",
	)
	if err != nil {
		t.Fatalf("generate invitation: %v", err)
	}
	if created.InviteePhoneHash == "" || created.InviteePhoneHash == "13800138000" {
		t.Fatalf("phone must be stored only as a non-empty digest, got %q", created.InviteePhoneHash)
	}
	if created.InviterOwnerAccountID != "account-owner" {
		t.Fatalf("owner audit snapshot mismatch: %q", created.InviterOwnerAccountID)
	}

	if _, err := facade.Generate(
		context.Background(),
		"spoofed-account",
		"persona-owner",
		"direct",
		"13800138000",
	); err == nil {
		t.Fatal("persona ownership spoof must be rejected")
	}
}

func TestInvitationLifecycleExpiresBeforeDeliveryAndAcceptIsIdempotent(t *testing.T) {
	now := time.Date(2026, 7, 22, 10, 0, 0, 0, time.UTC)
	expired := validInvitation(now)
	expired.ExpireAt = now.Add(-time.Second)
	if err := expired.MarkDelivered(now); err != invitationmodel.ErrExpired {
		t.Fatalf("expired delivery error = %v", err)
	}
	if expired.Status != invitationmodel.StatusExpired {
		t.Fatalf("expired status = %q", expired.Status)
	}

	accepted := validInvitation(now)
	if err := accepted.Accept(now); err != nil {
		t.Fatalf("first accept: %v", err)
	}
	firstAcceptedAt := accepted.AcceptedAt
	if err := accepted.Accept(now.Add(time.Minute)); err != nil {
		t.Fatalf("idempotent accept: %v", err)
	}
	if accepted.AcceptedAt != firstAcceptedAt {
		t.Fatal("idempotent accept must not rewrite acceptedAt")
	}
}

func validInvitation(now time.Time) *invitationmodel.Invitation {
	return &invitationmodel.Invitation{
		ID:                    "invitation-1",
		InviterSubAccountID:   "persona-owner",
		InviterOwnerAccountID: "account-owner",
		Channel:               "direct",
		LinkCode:              "link-code",
		Status:                invitationmodel.StatusGenerated,
		ExpireAt:              now.Add(7 * 24 * time.Hour),
		GeneratedAt:           now,
	}
}

type invitationPersonaOwners map[string]string

func (owners invitationPersonaOwners) ResolveOwnerAccountID(
	_ context.Context,
	subAccountID string,
) (string, bool, error) {
	owner, found := owners[subAccountID]
	return owner, found, nil
}

type invitationMemoryStore struct {
	record *invitationmodel.Invitation
}

func (store *invitationMemoryStore) Generate(
	_ context.Context,
	record *invitationmodel.Invitation,
	_ int,
) (*invitationmodel.Invitation, bool, error) {
	copy := *record
	store.record = &copy
	return &copy, true, nil
}

func (store *invitationMemoryStore) FindByLinkCode(
	_ context.Context,
	_ string,
) (*invitationmodel.Invitation, error) {
	if store.record == nil {
		return nil, invitationports.ErrNotFound
	}
	copy := *store.record
	return &copy, nil
}

func (store *invitationMemoryStore) ListByInviter(
	_ context.Context,
	_ string,
	_ string,
	_ int,
	_ int,
) ([]invitationmodel.Invitation, error) {
	if store.record == nil {
		return nil, nil
	}
	return []invitationmodel.Invitation{*store.record}, nil
}

func (store *invitationMemoryStore) MarkDelivered(
	_ context.Context,
	_ string,
	now time.Time,
) (*invitationmodel.Invitation, error) {
	if store.record == nil {
		return nil, invitationports.ErrNotFound
	}
	if err := store.record.MarkDelivered(now); err != nil {
		return nil, err
	}
	copy := *store.record
	return &copy, nil
}

func (store *invitationMemoryStore) Accept(
	_ context.Context,
	_ string,
	now time.Time,
) (*invitationmodel.Invitation, error) {
	if store.record == nil {
		return nil, invitationports.ErrNotFound
	}
	if err := store.record.Accept(now); err != nil {
		return nil, err
	}
	copy := *store.record
	return &copy, nil
}
