// spec_ref: specs/feature-tree/user-identity-profile-relationship/spec.md#dom-001
// readiness_case: initiate-contact-discovery-local
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

func TestInitiateContactDiscoveryBindsNormalizedCommandAndCompletesOnce(t *testing.T) {
	store := &contactDiscoveryStoreDouble{
		matches: []contactmodel.ContactPhoneMatch{{PersonaID: "persona-1"}},
	}
	events := &contactDiscoveryEventDouble{}
	service := contactapp.NewContactDiscoveryService(store, events)

	result, err := service.Initiate(
		context.Background(),
		"account-1",
		[]string{"hash-z", "hash-a", "hash-z", " "},
		"stable-key-1",
	)
	if err != nil {
		t.Fatal(err)
	}
	if result.Status != "completed" || result.MatchCount != 1 {
		t.Fatalf("unexpected result: %+v", result)
	}
	if got := store.createdRecord.HashedPhones; len(got) != 2 || got[0] != "hash-a" || got[1] != "hash-z" {
		t.Fatalf("command payload was not normalized before persistence: %v", got)
	}
	if store.command.Operation != "InitiateContactDiscovery" ||
		store.command.OwnerAccountID != "account-1" ||
		store.command.IdempotencyKey != "stable-key-1" ||
		len(store.command.CommandDigest) != 64 {
		t.Fatalf("incomplete command identity: %+v", store.command)
	}
	if store.completeCalls != 1 || events.count != 2 {
		t.Fatalf("expected one completion and initiated/completed events: complete=%d events=%d", store.completeCalls, events.count)
	}

	reordered := &contactDiscoveryStoreDouble{}
	_, _ = contactapp.NewContactDiscoveryService(reordered, &contactDiscoveryEventDouble{}).Initiate(
		context.Background(),
		"account-1",
		[]string{"hash-a", "hash-z"},
		"stable-key-1",
	)
	if reordered.command.CommandDigest != store.command.CommandDigest {
		t.Fatalf("equivalent normalized payloads produced different digests: %q != %q", reordered.command.CommandDigest, store.command.CommandDigest)
	}
}

func TestInitiateContactDiscoveryDoesNotTurnDependencyFailureIntoEmptySuccess(t *testing.T) {
	store := &contactDiscoveryStoreDouble{matchErr: errors.New("credential store unavailable")}
	service := contactapp.NewContactDiscoveryService(store, &contactDiscoveryEventDouble{})

	result, err := service.Initiate(
		context.Background(), "account-1", []string{"hash-a"}, "stable-key-2",
	)
	if err == nil || result != nil {
		t.Fatalf("dependency failure must fail closed, got result=%+v err=%v", result, err)
	}
	if store.completeCalls != 0 {
		t.Fatalf("failed dependency must not commit completed result: calls=%d", store.completeCalls)
	}
}

func TestInitiateContactDiscoveryReplayReturnsReceiptWithoutRepeatingSideEffects(t *testing.T) {
	now := time.Now().UTC()
	store := &contactDiscoveryStoreDouble{
		replay: &contactmodel.ContactDiscoveryRecord{
			ID: "first-record", OwnerAccountID: "account-1",
			HashedPhones: []string{"hash-a"}, MatchedPersonaIds: []string{"persona-1"},
			Status: "completed", MatchCount: 1, ExpireAt: now.Add(time.Hour),
			CreatedAt: now, CompletedAt: &now,
		},
	}
	events := &contactDiscoveryEventDouble{}
	result, err := contactapp.NewContactDiscoveryService(store, events).Initiate(
		context.Background(), "account-1", []string{"hash-a"}, "stable-key-3",
	)
	if err != nil || result.ID != "first-record" {
		t.Fatalf("replay failed: result=%+v err=%v", result, err)
	}
	if store.matchCalls != 0 || store.completeCalls != 0 || events.count != 0 {
		t.Fatalf("replay repeated side effects: matches=%d complete=%d events=%d", store.matchCalls, store.completeCalls, events.count)
	}
}

type contactDiscoveryStoreDouble struct {
	createdRecord *contactmodel.ContactDiscoveryRecord
	replay        *contactmodel.ContactDiscoveryRecord
	command       contactports.CommandIdentity
	matches       []contactmodel.ContactPhoneMatch
	matchErr      error
	matchCalls    int
	completeCalls int
}

func (store *contactDiscoveryStoreDouble) CreateIdempotent(
	_ context.Context,
	record *contactmodel.ContactDiscoveryRecord,
	_ int,
	command contactports.CommandIdentity,
) (*contactmodel.ContactDiscoveryRecord, bool, error) {
	store.command = command
	copy := *record
	copy.HashedPhones = append([]string(nil), record.HashedPhones...)
	store.createdRecord = &copy
	if store.replay != nil {
		return store.replay, false, nil
	}
	return &copy, true, nil
}

func (store *contactDiscoveryStoreDouble) CompleteIdempotent(
	_ context.Context,
	recordID string,
	matched []string,
	_ contactports.CommandIdentity,
) (*contactmodel.ContactDiscoveryRecord, bool, error) {
	store.completeCalls++
	now := time.Now().UTC()
	result := *store.createdRecord
	result.ID = recordID
	result.Status = "completed"
	result.MatchedPersonaIds = append([]string(nil), matched...)
	result.MatchCount = int64(len(matched))
	result.CompletedAt = &now
	return &result, true, nil
}

func (store *contactDiscoveryStoreDouble) FindLatestByOwner(context.Context, string) (*contactmodel.ContactDiscoveryRecord, error) {
	return nil, nil
}

func (store *contactDiscoveryStoreDouble) FindByID(context.Context, string) (*contactmodel.ContactDiscoveryRecord, error) {
	return nil, nil
}

func (store *contactDiscoveryStoreDouble) UpdateStatus(context.Context, string, string) error {
	return nil
}

func (store *contactDiscoveryStoreDouble) DismissIdempotent(context.Context, string, contactports.CommandIdentity) error {
	return nil
}

func (store *contactDiscoveryStoreDouble) DeleteExpired(context.Context) (int64, error) {
	return 0, nil
}

func (store *contactDiscoveryStoreDouble) FindPhoneMatches(
	context.Context,
	[]string,
) ([]contactmodel.ContactPhoneMatch, error) {
	store.matchCalls++
	return store.matches, store.matchErr
}

func (store *contactDiscoveryStoreDouble) CountTodayByOwner(context.Context, string) (int, error) {
	return 0, nil
}

type contactDiscoveryEventDouble struct{ count int }

func (publisher *contactDiscoveryEventDouble) PublishUserEvent(
	context.Context,
	string,
	string,
	string,
	map[string]any,
) error {
	publisher.count++
	return nil
}
