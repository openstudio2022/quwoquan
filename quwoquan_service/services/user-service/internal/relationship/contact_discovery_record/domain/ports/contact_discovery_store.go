package ports

import (
	"context"
	"errors"

	"quwoquan_service/services/user-service/internal/relationship/contact_discovery_record/domain/model"
)

var (
	ErrRateLimited         = errors.New("contact discovery daily limit reached")
	ErrIdempotencyConflict = errors.New("contact discovery idempotency key reused for another command")
	ErrNotFound            = errors.New("contact discovery record not found")
)

type CommandIdentity struct {
	Operation      string
	OwnerAccountID string
	IdempotencyKey string
	CommandDigest  string
}

type ContactDiscoveryStore interface {
	CreateIdempotent(
		ctx context.Context,
		record *model.ContactDiscoveryRecord,
		dailyLimit int,
		command CommandIdentity,
	) (stored *model.ContactDiscoveryRecord, created bool, err error)
	FindLatestByOwner(ctx context.Context, ownerID string) (*model.ContactDiscoveryRecord, error)
	FindByID(ctx context.Context, id string) (*model.ContactDiscoveryRecord, error)
	UpdateStatus(ctx context.Context, id, status string) error
	CompleteIdempotent(
		ctx context.Context,
		recordID string,
		matchedPersonaIDs []string,
		command CommandIdentity,
	) (stored *model.ContactDiscoveryRecord, transitioned bool, err error)
	DismissIdempotent(
		ctx context.Context,
		recordID string,
		command CommandIdentity,
	) error
	DeleteExpired(ctx context.Context) (int64, error)
	// FindPhoneMatches matches the uploaded hashes against active phone /
	// carrier_phone CredentialBindings, then projects each matched account onto
	// its non-strict active Personas. The store hashes each stored credential via
	// phonematch.Hash (single source of truth) and returns only Persona-level
	// enrichment — never ownerAccountId or another user's plaintext phone.
	// HashedPhone on each result echoes the matched uploaded hash.
	FindPhoneMatches(ctx context.Context, hashedPhones []string) ([]model.ContactPhoneMatch, error)
	CountTodayByOwner(ctx context.Context, ownerID string) (int, error)
}
