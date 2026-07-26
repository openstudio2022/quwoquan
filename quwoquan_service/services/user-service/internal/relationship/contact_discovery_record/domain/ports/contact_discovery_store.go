package ports

import (
	"context"

	"quwoquan_service/services/user-service/internal/relationship/contact_discovery_record/domain/model"
)

type ContactDiscoveryStore interface {
	Create(ctx context.Context, r *model.ContactDiscoveryRecord) error
	FindLatestByOwner(ctx context.Context, ownerID string) (*model.ContactDiscoveryRecord, error)
	FindByID(ctx context.Context, id string) (*model.ContactDiscoveryRecord, error)
	UpdateStatus(ctx context.Context, id, status string) error
	Complete(ctx context.Context, id string, matchedSubAccountIDs []string) error
	Dismiss(ctx context.Context, id string) error
	DeleteExpired(ctx context.Context) (int64, error)
	// FindPhoneMatches matches the uploaded hashes against active phone /
	// carrier_phone credentials of non-strict personas. The store hashes each
	// stored credential via phonematch.Hash (single source of truth) and returns
	// only SubAccount-level enrichment — never ownerAccountId or another user's
	// plaintext phone. HashedPhone on each result echoes the matched uploaded hash.
	FindPhoneMatches(ctx context.Context, hashedPhones []string) ([]model.ContactPhoneMatch, error)
	CountTodayByOwner(ctx context.Context, ownerID string) (int, error)
}
