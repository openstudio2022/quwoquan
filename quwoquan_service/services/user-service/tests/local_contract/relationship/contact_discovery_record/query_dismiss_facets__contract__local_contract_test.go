// spec_ref: specs/feature-tree/user-identity-profile-relationship/spec.md#dom-001
// readiness_case: get-latest-contact-discovery-local
// readiness_case: dismiss-contact-discovery-local
package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	contactapp "quwoquan_service/services/user-service/internal/relationship/contact_discovery_record/application"
	contactmodel "quwoquan_service/services/user-service/internal/relationship/contact_discovery_record/domain/model"
	contactports "quwoquan_service/services/user-service/internal/relationship/contact_discovery_record/domain/ports"
)

func TestGetLatestContactDiscoveryForwardsOwnerAndExpiresStaleRecord(t *testing.T) {
	store := &contactQueryDismissStore{
		latest: &contactmodel.ContactDiscoveryRecord{
			ID: "discovery-expired", OwnerAccountID: "account-owner",
			Status: "completed", ExpireAt: time.Now().UTC().Add(-time.Minute),
		},
	}
	service := contactapp.NewContactDiscoveryService(store, contactFacetEventPublisher{})

	result, err := service.GetLatest(context.Background(), "account-owner")
	if err != nil {
		t.Fatal(err)
	}
	if store.latestOwnerID != "account-owner" || result == nil || result.Status != "expired" {
		t.Fatalf("latest query lost owner or expiry semantics: owner=%q result=%+v", store.latestOwnerID, result)
	}
}

func TestDismissContactDiscoveryBindsStableOwnerScopedCommand(t *testing.T) {
	store := &contactQueryDismissStore{}
	service := contactapp.NewContactDiscoveryService(store, contactFacetEventPublisher{})

	if err := service.Dismiss(
		context.Background(), "account-owner", "discovery-1", "dismiss-key-1",
	); err != nil {
		t.Fatal(err)
	}
	if store.dismissRecordID != "discovery-1" ||
		store.dismissCommand.Operation != "DismissContactDiscovery" ||
		store.dismissCommand.OwnerAccountID != "account-owner" ||
		store.dismissCommand.IdempotencyKey != "dismiss-key-1" ||
		len(store.dismissCommand.CommandDigest) != 64 {
		t.Fatalf("dismiss command identity drifted: id=%q command=%+v", store.dismissRecordID, store.dismissCommand)
	}

	store.dismissCalls = 0
	if err := service.Dismiss(
		context.Background(), "account-owner", "discovery-1", "",
	); err == nil {
		t.Fatal("missing stable Idempotency-Key must fail closed")
	}
	if store.dismissCalls != 0 {
		t.Fatalf("invalid dismissal reached store: calls=%d", store.dismissCalls)
	}
}

type contactQueryDismissStore struct {
	latest          *contactmodel.ContactDiscoveryRecord
	latestOwnerID   string
	dismissRecordID string
	dismissCommand  contactports.CommandIdentity
	dismissCalls    int
}

func (store *contactQueryDismissStore) CreateIdempotent(
	context.Context,
	*contactmodel.ContactDiscoveryRecord,
	int,
	contactports.CommandIdentity,
) (*contactmodel.ContactDiscoveryRecord, bool, error) {
	return nil, false, errors.New("unexpected create")
}

func (store *contactQueryDismissStore) FindLatestByOwner(
	_ context.Context,
	ownerID string,
) (*contactmodel.ContactDiscoveryRecord, error) {
	store.latestOwnerID = ownerID
	if store.latest == nil {
		return nil, nil
	}
	copy := *store.latest
	return &copy, nil
}

func (*contactQueryDismissStore) FindByID(context.Context, string) (*contactmodel.ContactDiscoveryRecord, error) {
	return nil, errors.New("unexpected find by id")
}

func (*contactQueryDismissStore) UpdateStatus(context.Context, string, string) error {
	return errors.New("unexpected update status")
}

func (*contactQueryDismissStore) CompleteIdempotent(
	context.Context,
	string,
	[]string,
	contactports.CommandIdentity,
) (*contactmodel.ContactDiscoveryRecord, bool, error) {
	return nil, false, errors.New("unexpected complete")
}

func (store *contactQueryDismissStore) DismissIdempotent(
	_ context.Context,
	recordID string,
	command contactports.CommandIdentity,
) error {
	store.dismissCalls++
	store.dismissRecordID = recordID
	store.dismissCommand = command
	return nil
}

func (*contactQueryDismissStore) DeleteExpired(context.Context) (int64, error) {
	return 0, nil
}

func (*contactQueryDismissStore) FindPhoneMatches(
	context.Context,
	[]string,
) ([]contactmodel.ContactPhoneMatch, error) {
	return nil, errors.New("unexpected phone match")
}

func (*contactQueryDismissStore) CountTodayByOwner(context.Context, string) (int, error) {
	return 0, nil
}

type contactFacetEventPublisher struct{}

func (contactFacetEventPublisher) PublishUserEvent(
	context.Context,
	string,
	string,
	string,
	map[string]any,
) error {
	return nil
}
