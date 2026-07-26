package local_contract

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"strings"
	"sync"
	"testing"
	"time"

	challengeapp "quwoquan_service/services/user-service/internal/account/authentication_challenge/application"
	challengemodel "quwoquan_service/services/user-service/internal/account/authentication_challenge/domain/model"
	challengeports "quwoquan_service/services/user-service/internal/account/authentication_challenge/domain/ports"
)

func TestAuthenticationChallengeFacadeCreatesIdempotentlyAndReplaysSuccess(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, 7, 19, 12, 0, 0, 0, time.UTC)
	store := newFakeAuthenticationChallengeStore()
	facade := challengeapp.NewAuthenticationChallengeCommandFacade(
		store,
		fakeChallengeVerifier{},
		challengeapp.WithClock(func() time.Time { return now }),
		challengeapp.WithMaxVerificationAttempts(3),
	)

	created, err := facade.CreateChallenge(context.Background(), challengeapp.CreateChallengeCommand{
		ID:              "challenge-1",
		AccountID:       "account-1",
		Purpose:         "phone_login",
		Channel:         "sms",
		DestinationHash: "destination-fingerprint",
		SecretRef:       fakeChallengeSecretRef("correct-code"),
		IdempotencyKey:  "send-otp-1",
		ExpiresAt:       now.Add(5 * time.Minute),
	})
	if err != nil {
		t.Fatalf("首次创建 challenge: %v", err)
	}
	replayedCreate, err := facade.CreateChallenge(context.Background(), challengeapp.CreateChallengeCommand{
		ID:              "challenge-retry-generated-id",
		AccountID:       "account-1",
		Purpose:         "phone_login",
		Channel:         "sms",
		DestinationHash: "destination-fingerprint",
		SecretRef:       fakeChallengeSecretRef("retry-generated-code"),
		IdempotencyKey:  "send-otp-1",
		ExpiresAt:       now.Add(6 * time.Minute),
	})
	if err != nil {
		t.Fatalf("幂等重放创建: %v", err)
	}
	if !replayedCreate.IdempotentReplay ||
		replayedCreate.Challenge.ID != created.Challenge.ID ||
		store.createCalls != 2 ||
		store.challengeCount() != 1 {
		t.Fatalf("同 idempotency key 应返回首次创建结果: %+v", replayedCreate)
	}

	verified, err := facade.VerifyChallenge(context.Background(), challengeapp.VerifyChallengeCommand{
		Purpose:         "phone_login",
		Channel:         "sms",
		DestinationHash: "destination-fingerprint",
		Credential:      []byte("correct-code"),
	})
	if err != nil {
		t.Fatalf("首次成功验证: %v", err)
	}
	if verified.IdempotentReplay ||
		verified.Challenge.Status != challengemodel.StatusCompleted ||
		store.commitCalls != 1 {
		t.Fatalf("首次验证应原子完成一次: %+v", verified)
	}

	// completed 是终态，原凭据即使在原 expiresAt 之后重放也必须返回原结果，
	// 不能退化为 otp_expired。
	now = now.Add(10 * time.Minute)
	replayedVerify, err := facade.VerifyChallenge(context.Background(), challengeapp.VerifyChallengeCommand{
		ChallengeID: "challenge-1",
		Credential:  []byte("correct-code"),
	})
	if err != nil {
		t.Fatalf("相同凭据成功重放: %v", err)
	}
	if !replayedVerify.IdempotentReplay ||
		replayedVerify.Challenge.Version != verified.Challenge.Version ||
		store.commitCalls != 1 {
		t.Fatalf("成功重放不得再次提交状态: %+v", replayedVerify)
	}

	_, err = facade.VerifyChallenge(context.Background(), challengeapp.VerifyChallengeCommand{
		ChallengeID: "challenge-1",
		Credential:  []byte("different-code"),
	})
	if err == nil || !strings.Contains(err.Error(), "USER.AUTH.challenge_consumed") {
		t.Fatalf("不同凭据不得复用完成回执，得到: %v", err)
	}
}

func TestAuthenticationChallengeFacadePersistsLockAndExpiryBeforeReturningError(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, 7, 19, 12, 0, 0, 0, time.UTC)
	store := newFakeAuthenticationChallengeStore()
	facade := challengeapp.NewAuthenticationChallengeCommandFacade(
		store,
		fakeChallengeVerifier{},
		challengeapp.WithClock(func() time.Time { return now }),
		challengeapp.WithMaxVerificationAttempts(3),
	)
	createChallengeForFacadeTest(t, facade, "challenge-lock", "lock-key", now.Add(time.Minute))

	for attempt := 1; attempt <= 3; attempt++ {
		_, err := facade.VerifyChallenge(context.Background(), challengeapp.VerifyChallengeCommand{
			ChallengeID: "challenge-lock",
			Credential:  []byte("wrong-code"),
		})
		if attempt < 3 && (err == nil || !strings.Contains(err.Error(), "USER.AUTH.otp_mismatch")) {
			t.Fatalf("第 %d 次错误应返回 otp_mismatch，得到: %v", attempt, err)
		}
		if attempt == 3 && (err == nil ||
			!strings.Contains(err.Error(), "USER.AUTH.otp_attempts_exceeded")) {
			t.Fatalf("第 3 次错误应锁定，得到: %v", err)
		}
	}
	locked := store.mustLoad(t, "challenge-lock").Snapshot()
	if locked.Status != challengemodel.StatusLocked || locked.AttemptCount != 3 {
		t.Fatalf("错误上限必须持久化 locked: %+v", locked)
	}

	createChallengeForFacadeTest(t, facade, "challenge-expire", "expire-key", now.Add(time.Second))
	now = now.Add(time.Second)
	_, err := facade.VerifyChallenge(context.Background(), challengeapp.VerifyChallengeCommand{
		ChallengeID: "challenge-expire",
		Credential:  []byte("correct-code"),
	})
	if err == nil || !strings.Contains(err.Error(), "USER.AUTH.otp_expired") {
		t.Fatalf("过期应返回 otp_expired，得到: %v", err)
	}
	expired := store.mustLoad(t, "challenge-expire").Snapshot()
	if expired.Status != challengemodel.StatusExpired {
		t.Fatalf("返回过期错误前必须持久化 expired: %+v", expired)
	}
}

func createChallengeForFacadeTest(
	t *testing.T,
	facade *challengeapp.AuthenticationChallengeCommandFacade,
	id string,
	idempotencyKey string,
	expiresAt time.Time,
) {
	t.Helper()
	if _, err := facade.CreateChallenge(context.Background(), challengeapp.CreateChallengeCommand{
		ID:              id,
		Purpose:         "phone_login",
		Channel:         "sms",
		DestinationHash: "destination-" + id,
		SecretRef:       fakeChallengeSecretRef("correct-code"),
		IdempotencyKey:  idempotencyKey,
		ExpiresAt:       expiresAt,
	}); err != nil {
		t.Fatalf("创建 %s: %v", id, err)
	}
}

type fakeChallengeVerifier struct{}

func (fakeChallengeVerifier) VerifyCredential(
	_ context.Context,
	input challengeports.CredentialVerificationInput,
) (challengeports.CredentialVerificationEvidence, error) {
	sum := sha256.Sum256(append(
		[]byte(input.ChallengeID+"\x00"+input.DestinationHash+"\x00"),
		input.Credential...,
	))
	return challengeports.CredentialVerificationEvidence{
		CompletionFingerprint: hex.EncodeToString(sum[:]),
		Matched: input.SecretRef ==
			fakeChallengeSecretRef(string(input.Credential)),
	}, nil
}

func fakeChallengeSecretRef(credential string) string {
	sum := sha256.Sum256([]byte(credential))
	return "sha256:" + hex.EncodeToString(sum[:])
}

type fakeAuthenticationChallengeStore struct {
	mu          sync.Mutex
	byID        map[string]challengemodel.AuthenticationChallenge
	receipts    map[string]fakeChallengeCreationReceipt
	createCalls int
	commitCalls int
}

type fakeChallengeCreationReceipt struct {
	challengeID        string
	commandFingerprint string
}

func newFakeAuthenticationChallengeStore() *fakeAuthenticationChallengeStore {
	return &fakeAuthenticationChallengeStore{
		byID:     map[string]challengemodel.AuthenticationChallenge{},
		receipts: map[string]fakeChallengeCreationReceipt{},
	}
}

func (store *fakeAuthenticationChallengeStore) Create(
	_ context.Context,
	commit challengeports.CreateCommit,
) (challengeports.CreateResult, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	store.createCalls++
	if receipt, found := store.receipts[commit.IdempotencyKey]; found {
		if receipt.commandFingerprint != commit.CommandFingerprint {
			return challengeports.CreateResult{}, challengeports.ErrIdempotencyConflict
		}
		return challengeports.CreateResult{
			Aggregate: store.byID[receipt.challengeID],
			Replayed:  true,
		}, nil
	}
	state := commit.Aggregate.State()
	store.byID[state.ID] = commit.Aggregate
	store.receipts[commit.IdempotencyKey] = fakeChallengeCreationReceipt{
		challengeID:        state.ID,
		commandFingerprint: commit.CommandFingerprint,
	}
	return challengeports.CreateResult{Aggregate: commit.Aggregate}, nil
}

func (store *fakeAuthenticationChallengeStore) LoadByID(
	_ context.Context,
	challengeID string,
) (challengemodel.AuthenticationChallenge, bool, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	challenge, found := store.byID[challengeID]
	return challenge, found, nil
}

func (store *fakeAuthenticationChallengeStore) LoadLatest(
	_ context.Context,
	lookup challengeports.LatestChallengeLookup,
) (challengemodel.AuthenticationChallenge, bool, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	var latest challengemodel.AuthenticationChallenge
	found := false
	for _, challenge := range store.byID {
		snapshot := challenge.Snapshot()
		if snapshot.Purpose != lookup.Purpose ||
			snapshot.Channel != lookup.Channel ||
			snapshot.DestinationHash != lookup.DestinationHash {
			continue
		}
		if !found || snapshot.CreatedAt.After(latest.Snapshot().CreatedAt) {
			latest = challenge
			found = true
		}
	}
	return latest, found, nil
}

func (store *fakeAuthenticationChallengeStore) Commit(
	_ context.Context,
	expectedVersion int64,
	aggregate challengemodel.AuthenticationChallenge,
) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	store.commitCalls++
	id := aggregate.Snapshot().ID
	current, found := store.byID[id]
	if !found || current.Snapshot().Version != expectedVersion {
		return challengemodel.ErrVersionConflict
	}
	store.byID[id] = aggregate
	return nil
}

func (store *fakeAuthenticationChallengeStore) challengeCount() int {
	store.mu.Lock()
	defer store.mu.Unlock()
	return len(store.byID)
}

func (store *fakeAuthenticationChallengeStore) mustLoad(
	t *testing.T,
	id string,
) challengemodel.AuthenticationChallenge {
	t.Helper()
	challenge, found, err := store.LoadByID(context.Background(), id)
	if err != nil {
		t.Fatalf("读取 %s: %v", id, err)
	}
	if !found {
		t.Fatalf("未找到 %s", id)
	}
	return challenge
}

var _ challengeports.AggregateStore = (*fakeAuthenticationChallengeStore)(nil)
var _ challengeports.CredentialVerifier = fakeChallengeVerifier{}
