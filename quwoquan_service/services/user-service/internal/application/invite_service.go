package application

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"time"

	"github.com/google/uuid"

	"quwoquan_service/services/user-service/internal/domain/user/model"
	userrepo "quwoquan_service/services/user-service/internal/domain/user/repository"
)

const (
	inviteDailyLimit  = 1000
	inviteTTLDays     = 7
)

var (
	ErrInviteExpired          = fmt.Errorf("invitation has expired")
	ErrInviteAlreadyAccepted  = fmt.Errorf("invitation already accepted")
	ErrInviteNotFound         = fmt.Errorf("invitation not found")
	ErrInviteDailyLimitExceeded = fmt.Errorf("daily invite limit reached")
)

// InviteService manages invite lifecycle and attribution.
type InviteService struct {
	invites  userrepo.InviteRepository
	personas userrepo.PersonaRepository
}

func NewInviteService(invites userrepo.InviteRepository, personas userrepo.PersonaRepository) *InviteService {
	return &InviteService{invites: invites, personas: personas}
}

// Generate creates an invite record idempotently.
// inviterOwnerAccountID is stored for audit; never returned via API.
func (s *InviteService) Generate(ctx context.Context, inviterSubAccountID, inviterOwnerAccountID, channel, inviteePhone string) (*model.InviteRecord, error) {
	// Rate limit
	count, err := s.invites.CountTodayByInviter(ctx, inviterSubAccountID)
	if err != nil {
		return nil, err
	}
	if count >= inviteDailyLimit {
		return nil, ErrInviteDailyLimitExceeded
	}

	// Idempotency: if same (sub, channel, phone) in generated state, return existing
	if inviteePhone != "" {
		existing, err := s.invites.FindIdempotent(ctx, inviterSubAccountID, channel, inviteePhone)
		if err != nil {
			return nil, err
		}
		if existing != nil && !existing.IsExpired() {
			return existing, nil
		}
	}

	linkCode, err := generateLinkCode()
	if err != nil {
		return nil, err
	}

	record := &model.InviteRecord{
		ID:                    uuid.New().String(),
		InviterSubAccountID:   inviterSubAccountID,
		InviterOwnerAccountID: inviterOwnerAccountID,
		Channel:               channel,
		LinkCode:              linkCode,
		InviteePhoneHash:      inviteePhone, // already hashed by caller
		Status:                "generated",
		ExpireAt:              time.Now().UTC().Add(inviteTTLDays * 24 * time.Hour),
	}
	if err := s.invites.Create(ctx, record); err != nil {
		return nil, err
	}
	return record, nil
}

// GetByCode returns public-facing invite info.
// Privacy: does NOT include inviterOwnerAccountID or inviteePhoneHash.
func (s *InviteService) GetByCode(ctx context.Context, linkCode string) (*model.InviteRecord, error) {
	r, err := s.invites.FindByLinkCode(ctx, linkCode)
	if err != nil {
		return nil, err
	}
	if r == nil {
		return nil, ErrInviteNotFound
	}
	if r.IsExpired() {
		return nil, ErrInviteExpired
	}
	// Mark delivered (first view)
	_ = s.invites.MarkDelivered(ctx, r.ID)
	r.Status = "delivered"
	return r, nil
}

// Accept records that the invitee accepted the invite (idempotent).
func (s *InviteService) Accept(ctx context.Context, linkCode string) (*model.InviteRecord, error) {
	r, err := s.invites.FindByLinkCode(ctx, linkCode)
	if err != nil {
		return nil, err
	}
	if r == nil {
		return nil, ErrInviteNotFound
	}
	if r.IsExpired() {
		return nil, ErrInviteExpired
	}
	if r.Status == "accepted" || r.Status == "activated" {
		return r, nil // idempotent
	}
	if err := s.invites.Accept(ctx, r.ID); err != nil {
		return nil, err
	}
	r.Status = "accepted"
	now := time.Now().UTC()
	r.AcceptedAt = &now
	return r, nil
}

// ListByInviter returns invites for a sub-account (sanitised: no ownerAccountId).
func (s *InviteService) ListByInviter(ctx context.Context, inviterSubAccountID, statusFilter string, limit, offset int) ([]model.InviteRecord, error) {
	if limit <= 0 || limit > 100 {
		limit = 20
	}
	return s.invites.ListByInviter(ctx, inviterSubAccountID, statusFilter, limit, offset)
}

func generateLinkCode() (string, error) {
	b := make([]byte, 12)
	if _, err := rand.Read(b); err != nil {
		return "", err
	}
	return hex.EncodeToString(b), nil
}
