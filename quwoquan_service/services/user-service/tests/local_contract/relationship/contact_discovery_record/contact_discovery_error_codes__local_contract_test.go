package local_contract

import (
	"context"
	"errors"
	"fmt"
	"testing"

	runtimeerrors "quwoquan_service/runtime/errors"
	contactapp "quwoquan_service/services/user-service/internal/relationship/contact_discovery_record/application"
	contactmodel "quwoquan_service/services/user-service/internal/relationship/contact_discovery_record/domain/model"
	contactports "quwoquan_service/services/user-service/internal/relationship/contact_discovery_record/domain/ports"
)

func assertContactDiscoveryErrorCode(t *testing.T, err error, wantCode string) {
	t.Helper()
	var appErr *runtimeerrors.AppError
	if !errors.As(err, &appErr) || appErr.Code.String() != wantCode {
		t.Fatalf("expected %s, got %T: %v", wantCode, err, err)
	}
}

type rateLimitedContactDiscoveryStore struct {
	contactDiscoveryStoreDouble
}

func (store *rateLimitedContactDiscoveryStore) CreateIdempotent(
	_ context.Context,
	_ *contactmodel.ContactDiscoveryRecord,
	_ int,
	_ contactports.CommandIdentity,
) (*contactmodel.ContactDiscoveryRecord, bool, error) {
	return nil, false, contactports.ErrRateLimited
}

type dismissNotFoundContactDiscoveryStore struct {
	contactDiscoveryStoreDouble
}

func (store *dismissNotFoundContactDiscoveryStore) DismissIdempotent(
	context.Context,
	string,
	contactports.CommandIdentity,
) error {
	return contactports.ErrNotFound
}

func TestInitiateContactDiscoveryRejectsOversizedBatch(t *testing.T) {
	t.Parallel()
	service := contactapp.NewContactDiscoveryService(
		&contactDiscoveryStoreDouble{},
		&contactDiscoveryEventDouble{},
	)

	oversized := make([]string, 5001)
	for index := range oversized {
		oversized[index] = fmt.Sprintf("hash-%04d", index)
	}
	_, err := service.Initiate(
		context.Background(),
		"account-batch",
		oversized,
		"stable-key-batch",
	)
	assertContactDiscoveryErrorCode(t, err, "USER.CONTACT.too_many_contacts")
}

func TestInitiateContactDiscoverySurfacesRateLimited(t *testing.T) {
	t.Parallel()
	service := contactapp.NewContactDiscoveryService(
		&rateLimitedContactDiscoveryStore{},
		&contactDiscoveryEventDouble{},
	)

	_, err := service.Initiate(
		context.Background(),
		"account-limited",
		[]string{"hash-a"},
		"stable-key-limited",
	)
	assertContactDiscoveryErrorCode(t, err, "USER.CONTACT.rate_limited")
}

func TestDismissContactDiscoverySurfacesNotFound(t *testing.T) {
	t.Parallel()
	service := contactapp.NewContactDiscoveryService(
		&dismissNotFoundContactDiscoveryStore{},
		&contactDiscoveryEventDouble{},
	)

	err := service.Dismiss(
		context.Background(),
		"account-owner",
		"missing-discovery-id",
		"stable-key-dismiss",
	)
	assertContactDiscoveryErrorCode(t, err, "USER.CONTACT.not_found")
}
