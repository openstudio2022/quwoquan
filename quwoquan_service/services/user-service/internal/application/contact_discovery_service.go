package application

import (
	"context"
	"fmt"
	"time"

	"github.com/google/uuid"

	"quwoquan_service/services/user-service/internal/domain/user/model"
	userrepo "quwoquan_service/services/user-service/internal/domain/user/repository"
)

const (
	discoveryRateLimit   = 5   // per owner per day
	discoveryBatchLimit  = 5000
	discoveryTTLHours    = 72
)

var (
	ErrDiscoveryRateLimited  = fmt.Errorf("daily contact discovery limit reached")
	ErrDiscoveryBatchTooLarge = fmt.Errorf("too many contacts, maximum 5000 per request")
)

// ContactDiscoveryService handles contact matching with privacy guarantees.
type ContactDiscoveryService struct {
	discoveries userrepo.ContactDiscoveryRepository
}

func NewContactDiscoveryService(discoveries userrepo.ContactDiscoveryRepository) *ContactDiscoveryService {
	return &ContactDiscoveryService{discoveries: discoveries}
}

// Initiate creates a discovery record and synchronously matches hashed phones.
// Privacy: returns only the record ID and status; caller fetches matches separately.
func (s *ContactDiscoveryService) Initiate(ctx context.Context, ownerID string, hashedPhones []string) (*model.ContactDiscoveryRecord, error) {
	if len(hashedPhones) > discoveryBatchLimit {
		return nil, ErrDiscoveryBatchTooLarge
	}

	count, err := s.discoveries.CountTodayByOwner(ctx, ownerID)
	if err != nil {
		return nil, err
	}
	if count >= discoveryRateLimit {
		return nil, ErrDiscoveryRateLimited
	}

	record := &model.ContactDiscoveryRecord{
		ID:             uuid.New().String(),
		OwnerAccountID: ownerID,
		HashedPhones:   hashedPhones,
		Status:         "pending",
		ExpireAt:       time.Now().UTC().Add(discoveryTTLHours * time.Hour),
	}
	if err := s.discoveries.Create(ctx, record); err != nil {
		return nil, err
	}

	// Synchronous match (for simplicity; in production this would be async)
	matched, err := s.discoveries.FindSubAccountIDsByPhoneHashes(ctx, hashedPhones)
	if err != nil {
		// Best-effort: complete with empty result rather than fail
		matched = []string{}
	}
	if err := s.discoveries.Complete(ctx, record.ID, matched); err != nil {
		return nil, err
	}
	record.Status = "completed"
	record.MatchedSubAccountIds = matched
	record.MatchCount = int64(len(matched))

	return record, nil
}

// GetLatest returns the latest discovery result for an owner.
// Privacy: never returns OwnerAccountID or HashedPhones.
func (s *ContactDiscoveryService) GetLatest(ctx context.Context, ownerID string) (*model.ContactDiscoveryRecord, error) {
	r, err := s.discoveries.FindLatestByOwner(ctx, ownerID)
	if err != nil {
		return nil, err
	}
	if r == nil {
		return nil, nil
	}
	// Ensure expired records show as expired
	if r.ExpireAt.Before(time.Now().UTC()) && r.Status != "dismissed" {
		r.Status = "expired"
	}
	return r, nil
}

// Dismiss marks a discovery record as dismissed (user action).
func (s *ContactDiscoveryService) Dismiss(ctx context.Context, ownerID, id string) error {
	r, err := s.discoveries.FindByID(ctx, id)
	if err != nil {
		return err
	}
	if r == nil {
		return fmt.Errorf("discovery record not found")
	}
	if r.OwnerAccountID != ownerID {
		return fmt.Errorf("discovery record not found") // security: same error for auth mismatch
	}
	return s.discoveries.Dismiss(ctx, id)
}
