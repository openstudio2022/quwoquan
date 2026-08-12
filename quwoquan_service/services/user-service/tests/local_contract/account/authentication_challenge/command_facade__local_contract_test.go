package local_contract

import (
	"context"
	. "quwoquan_service/services/user-service/internal/account/authentication_challenge/application"
	"sync"
	"testing"
	"time"

	challengemodel "quwoquan_service/services/user-service/internal/account/authentication_challenge/domain/model"
	challengeports "quwoquan_service/services/user-service/internal/account/authentication_challenge/domain/ports"
)

type migratedCommandFacadeMemoryChallengeStore struct {
	mu       sync.Mutex
	items    map[string]challengemodel.AuthenticationChallenge
	receipts map[string]string
}

func migratedCommandFacadeNewMemoryChallengeStore() *migratedCommandFacadeMemoryChallengeStore {
	return &migratedCommandFacadeMemoryChallengeStore{
		items:    map[string]challengemodel.AuthenticationChallenge{},
		receipts: map[string]string{},
	}
}

func (store *migratedCommandFacadeMemoryChallengeStore) Create(
	_ context.Context,
	commit challengeports.CreateCommit,
) (challengeports.CreateResult, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	if fingerprint, found := store.receipts[commit.IdempotencyKey]; found {
		if fingerprint != commit.CommandFingerprint {
			return challengeports.CreateResult{},
				challengeports.ErrIdempotencyConflict
		}
		for _, item := range store.items {
			return challengeports.CreateResult{
				Aggregate: item,
				Replayed:  true,
			}, nil
		}
	}
	state := commit.Aggregate.State()
	store.receipts[commit.IdempotencyKey] = commit.CommandFingerprint
	store.items[state.ID] = commit.Aggregate
	return challengeports.CreateResult{Aggregate: commit.Aggregate}, nil
}

func (store *migratedCommandFacadeMemoryChallengeStore) LoadByID(
	_ context.Context,
	id string,
) (challengemodel.AuthenticationChallenge, bool, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	item, found := store.items[id]
	return item, found, nil
}

func (store *migratedCommandFacadeMemoryChallengeStore) LoadLatest(
	_ context.Context,
	lookup challengeports.LatestChallengeLookup,
) (challengemodel.AuthenticationChallenge, bool, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	var latest challengemodel.AuthenticationChallenge
	found := false
	for _, item := range store.items {
		state := item.State()
		if state.Purpose == lookup.Purpose &&
			state.Channel == lookup.Channel &&
			state.DestinationHash == lookup.DestinationHash &&
			(!found || state.CreatedAt.After(latest.State().CreatedAt)) {
			latest = item
			found = true
		}
	}
	return latest, found, nil
}

func (store *migratedCommandFacadeMemoryChallengeStore) LoadByDeliveryRequestID(
	_ context.Context,
	requestID string,
) (challengemodel.AuthenticationChallenge, bool, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	for _, item := range store.items {
		if item.State().DeliveryRequestID == requestID {
			return item, true, nil
		}
	}
	return challengemodel.AuthenticationChallenge{}, false, nil
}

func (store *migratedCommandFacadeMemoryChallengeStore) Commit(
	_ context.Context,
	expectedVersion int64,
	aggregate challengemodel.AuthenticationChallenge,
) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	state := aggregate.State()
	current, found := store.items[state.ID]
	if !found || current.State().Version != expectedVersion {
		return challengemodel.ErrVersionConflict
	}
	store.items[state.ID] = aggregate
	return nil
}

func TestAuthenticationChallengeInlineReceiptAndLocking(t *testing.T) {
	now := time.Date(2026, 7, 20, 0, 0, 0, 0, time.UTC)
	store := migratedCommandFacadeNewMemoryChallengeStore()
	facade := NewAuthenticationChallengeCommandFacade(
		store,
		OTPCredentialVerifier{},
		WithClock(func() time.Time { return now }),
	)
	const (
		challengeID = "otp_ch_contract"
		destination = "phone-hash"
		code        = "123456"
	)
	create := CreateChallengeCommand{
		ID:              challengeID,
		Purpose:         "phone_login",
		Channel:         "sms",
		DestinationHash: destination,
		SecretRef: OTPSecretReference(
			challengeID,
			destination,
			[]byte(code),
		),
		IdempotencyKey: "otp-create-1",
		ExpiresAt:      now.Add(5 * time.Minute),
	}
	first, err := facade.CreateChallenge(context.Background(), create)
	if err != nil {
		t.Fatalf("create challenge: %v", err)
	}
	replayedCreate, err := facade.CreateChallenge(context.Background(), create)
	if err != nil || !replayedCreate.IdempotentReplay {
		t.Fatalf("create replay: result=%+v err=%v", replayedCreate, err)
	}

	verify := VerifyChallengeCommand{
		Purpose:         "phone_login",
		Channel:         "sms",
		DestinationHash: destination,
		Credential:      []byte(code),
	}
	verified, err := facade.VerifyChallenge(context.Background(), verify)
	if err != nil || verified.IdempotentReplay {
		t.Fatalf("verify: result=%+v err=%v", verified, err)
	}
	replayed, err := facade.VerifyChallenge(context.Background(), verify)
	if err != nil || !replayed.IdempotentReplay {
		t.Fatalf("same credential replay: result=%+v err=%v", replayed, err)
	}
	_, err = facade.VerifyChallenge(context.Background(), VerifyChallengeCommand{
		Purpose:         "phone_login",
		Channel:         "sms",
		DestinationHash: destination,
		Credential:      []byte("654321"),
	})
	if err == nil {
		t.Fatal("different credential must not replay completed challenge")
	}

	lockedID := "otp_ch_locked"
	_, err = facade.CreateChallenge(context.Background(), CreateChallengeCommand{
		ID:              lockedID,
		Purpose:         "bind_phone",
		Channel:         "sms",
		DestinationHash: destination,
		SecretRef: OTPSecretReference(
			lockedID,
			destination,
			[]byte(code),
		),
		IdempotencyKey: "otp-create-locked",
		ExpiresAt:      now.Add(5 * time.Minute),
	})
	if err != nil {
		t.Fatalf("create lock challenge: %v", err)
	}
	for attempt := 1; attempt <= 5; attempt++ {
		_, err = facade.VerifyChallenge(context.Background(), VerifyChallengeCommand{
			ChallengeID: lockedID,
			Credential:  []byte("wrong"),
		})
		if attempt < 5 && err == nil {
			t.Fatalf("attempt %d must mismatch", attempt)
		}
	}
	if err == nil {
		t.Fatal("fifth mismatch must lock challenge")
	}
	loaded, found, err := store.LoadByID(context.Background(), lockedID)
	if err != nil || !found {
		t.Fatalf("load locked challenge: found=%v err=%v", found, err)
	}
	if loaded.State().Status != challengemodel.StatusLocked {
		t.Fatalf("challenge status=%s, want locked", loaded.State().Status)
	}
	if err := loaded.Validate(); err != nil {
		t.Fatalf("locked challenge must remain valid: %v", err)
	}
	_ = first
}
