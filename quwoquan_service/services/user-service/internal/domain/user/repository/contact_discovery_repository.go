package repository

import (
	"context"

	"quwoquan_service/services/user-service/internal/domain/user/model"
)

type ContactDiscoveryRepository interface {
	Create(ctx context.Context, r *model.ContactDiscoveryRecord) error
	FindLatestByOwner(ctx context.Context, ownerID string) (*model.ContactDiscoveryRecord, error)
	FindByID(ctx context.Context, id string) (*model.ContactDiscoveryRecord, error)
	UpdateStatus(ctx context.Context, id, status string) error
	Complete(ctx context.Context, id string, matchedSubAccountIDs []string) error
	Dismiss(ctx context.Context, id string) error
	DeleteExpired(ctx context.Context) (int64, error)
	// FindSubAccountIDsByPhoneHashes returns subAccountIds for phones that are registered.
	// Returns only SubAccount-level identifiers, never ownerAccountId.
	FindSubAccountIDsByPhoneHashes(ctx context.Context, hashedPhones []string) ([]string, error)
	CountTodayByOwner(ctx context.Context, ownerID string) (int, error)
}
