package auth

import (
	"context"
	"errors"
	"strings"
	"sync"
	"testing"
	"time"
)

type delegatedGrantTestAuthority struct {
	snapshot AccountSecuritySnapshot
	err      error
}

func (a delegatedGrantTestAuthority) ReadAccountSecurity(
	context.Context,
	string,
) (AccountSecuritySnapshot, error) {
	return a.snapshot, a.err
}

type delegatedGrantMemoryJTIStore struct {
	mu       sync.Mutex
	consumed map[string]time.Time
	err      error
}

func (s *delegatedGrantMemoryJTIStore) Consume(
	_ context.Context,
	jti string,
	expiresAt time.Time,
) (bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.err != nil {
		return false, s.err
	}
	if s.consumed == nil {
		s.consumed = map[string]time.Time{}
	}
	if _, exists := s.consumed[jti]; exists {
		return false, nil
	}
	s.consumed[jti] = expiresAt
	return true, nil
}

func TestDelegatedQueryGrantRejectsMismatchedBindings(
	t *testing.T,
) {
	t.Parallel()
	now := time.Unix(2_000_000_000, 0).UTC()
	signer, verifier := delegatedGrantTestSignerVerifier(t, now, 7)
	claims := delegatedGrantTestClaims(now, DelegatedGrantTypeQuery)
	token, err := signer.SignQuery(DelegatedQueryGrant{Claims: claims})
	if err != nil {
		t.Fatalf("sign query grant: %v", err)
	}
	expected := delegatedGrantTestExpectation(claims)
	tests := []struct {
		name   string
		mutate func(*DelegatedGrantExpectation)
		target error
	}{
		{
			name: "operation",
			mutate: func(value *DelegatedGrantExpectation) {
				value.OperationID = "assistant.run.Cancel"
			},
			target: ErrDelegatedGrantTargetMismatch,
		},
		{
			name: "resource target",
			mutate: func(value *DelegatedGrantExpectation) {
				value.Resource.ID = "GET /assistant/runs/other"
			},
			target: ErrDelegatedGrantTargetMismatch,
		},
		{
			name: "digest",
			mutate: func(value *DelegatedGrantExpectation) {
				value.RequestDigest = "sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
			},
			target: ErrDelegatedGrantDigestMismatch,
		},
		{
			name: "audience",
			mutate: func(value *DelegatedGrantExpectation) {
				value.Audience = "other-service"
			},
			target: ErrDelegatedGrantAudienceMismatch,
		},
		{
			name: "delegate actor",
			mutate: func(value *DelegatedGrantExpectation) {
				value.DelegateService = "other-service"
			},
			target: ErrDelegatedGrantActorMismatch,
		},
		{
			name: "scope",
			mutate: func(value *DelegatedGrantExpectation) {
				value.Scopes = []string{"assistant.run.write"}
			},
			target: ErrDelegatedGrantScopeMismatch,
		},
		{
			name: "approval",
			mutate: func(value *DelegatedGrantExpectation) {
				value.ApprovalRef = "approval-other"
			},
			target: ErrDelegatedGrantTargetMismatch,
		},
	}
	for _, testCase := range tests {
		t.Run(testCase.name, func(t *testing.T) {
			drifted := expected
			testCase.mutate(&drifted)
			if _, err := verifier.VerifyQuery(
				context.Background(),
				token,
				drifted,
			); !errors.Is(err, testCase.target) {
				t.Fatalf("expected %v, got %v", testCase.target, err)
			}
		})
	}
}

func TestDelegatedGrantRejectsExpiryAndRevokedAuthEpoch(t *testing.T) {
	t.Parallel()
	now := time.Unix(2_000_000_000, 0).UTC()
	signer, verifier := delegatedGrantTestSignerVerifier(t, now, 8)
	expired := delegatedGrantTestClaims(now, DelegatedGrantTypeQuery)
	expired.IssuedAt = now.Add(-10 * time.Minute).Unix()
	expired.ExpiresAt = now.Add(-5 * time.Minute).Unix()
	token, err := signer.SignQuery(DelegatedQueryGrant{Claims: expired})
	if err != nil {
		t.Fatalf("sign expired query grant: %v", err)
	}
	if _, err := verifier.VerifyQuery(
		context.Background(),
		token,
		delegatedGrantTestExpectation(expired),
	); !errors.Is(err, ErrExpiredToken) {
		t.Fatalf("expected expiry rejection, got %v", err)
	}

	active := delegatedGrantTestClaims(now, DelegatedGrantTypeQuery)
	activeToken, err := signer.SignQuery(DelegatedQueryGrant{Claims: active})
	if err != nil {
		t.Fatalf("sign query grant: %v", err)
	}
	if _, err := verifier.VerifyQuery(
		context.Background(),
		activeToken,
		delegatedGrantTestExpectation(active),
	); !errors.Is(err, ErrDelegatedGrantAuthEpoch) {
		t.Fatalf("expected auth epoch rejection, got %v", err)
	}
}

func TestDelegatedCommandGrantConsumesJTIExactlyOnce(t *testing.T) {
	t.Parallel()
	now := time.Unix(2_000_000_000, 0).UTC()
	signer, verifier := delegatedGrantTestSignerVerifier(t, now, 7)
	claims := delegatedGrantTestClaims(now, DelegatedGrantTypeCommand)
	claims.ApprovalRef = "approval-1"
	token, err := signer.SignCommand(DelegatedCommandGrant{Claims: claims})
	if err != nil {
		t.Fatalf("sign command grant: %v", err)
	}
	store := &delegatedGrantMemoryJTIStore{}
	consumer, err := NewDelegatedCommandGrantConsumer(verifier, store)
	if err != nil {
		t.Fatalf("new consumer: %v", err)
	}
	expected := delegatedGrantTestExpectation(claims)
	if _, err := consumer.Consume(
		context.Background(),
		token,
		expected,
	); err != nil {
		t.Fatalf("consume command grant: %v", err)
	}
	if _, err := consumer.Consume(
		context.Background(),
		token,
		expected,
	); !errors.Is(err, ErrDelegatedGrantReplay) {
		t.Fatalf("expected replay rejection, got %v", err)
	}
}

func TestDelegatedCommandConsumerFailsFastWithoutPersistentPort(
	t *testing.T,
) {
	t.Parallel()
	now := time.Unix(2_000_000_000, 0).UTC()
	_, verifier := delegatedGrantTestSignerVerifier(t, now, 7)
	if _, err := NewDelegatedCommandGrantConsumer(
		verifier,
		nil,
	); err == nil {
		t.Fatal("missing persistent JTI store must fail at composition")
	}
}

func TestDelegatedCommandGrantRequiresApprovalAndShortTTL(t *testing.T) {
	t.Parallel()
	now := time.Unix(2_000_000_000, 0).UTC()
	signer, _ := delegatedGrantTestSignerVerifier(t, now, 7)
	claims := delegatedGrantTestClaims(now, DelegatedGrantTypeCommand)
	if _, err := signer.SignCommand(
		DelegatedCommandGrant{Claims: claims},
	); !errors.Is(err, ErrDelegatedGrantInvalid) {
		t.Fatalf("command without approval must be rejected, got %v", err)
	}
	claims.ApprovalRef = "approval-1"
	claims.ExpiresAt = now.Add(DelegatedCommandGrantMaxTTL + time.Second).Unix()
	if _, err := signer.SignCommand(
		DelegatedCommandGrant{Claims: claims},
	); !errors.Is(err, ErrDelegatedGrantInvalid) {
		t.Fatalf("long-lived command must be rejected, got %v", err)
	}
}

func delegatedGrantTestSignerVerifier(
	t *testing.T,
	now time.Time,
	authEpoch int64,
) (*DelegatedGrantSigner, *DelegatedGrantVerifier) {
	t.Helper()
	secret := []byte("delegated-grant-local-contract-secret-32-bytes")
	signer, err := NewHS256DelegatedGrantSigner(secret, "account-authority")
	if err != nil {
		t.Fatalf("new signer: %v", err)
	}
	verifier, err := NewHS256DelegatedGrantVerifier(
		DelegatedGrantVerifierConfig{
			Secret:    secret,
			Issuer:    "account-authority",
			ClockSkew: 0,
			AccountSecurityAuthority: delegatedGrantTestAuthority{
				snapshot: AccountSecuritySnapshot{
					AccountState: "active",
					AuthEpoch:    authEpoch,
				},
			},
		},
	)
	if err != nil {
		t.Fatalf("new verifier: %v", err)
	}
	verifier.now = func() time.Time { return now }
	return signer, verifier
}

func delegatedGrantTestClaims(
	now time.Time,
	grantType DelegatedGrantType,
) DelegatedGrantClaims {
	return DelegatedGrantClaims{
		GrantType:        grantType,
		Issuer:           "account-authority",
		Audience:         "assistant-service",
		AccountID:        "account-1",
		PersonaID:        "persona-1",
		AuthEpoch:        7,
		DelegateService:  "assistant-service",
		RunID:            "run-1",
		ToolInvocationID: "tool-1",
		OperationID:      "assistant.run.Get",
		Resource: DelegatedResourceConstraint{
			Type: "http_request",
			ID:   "GET /assistant/runs/run-1",
		},
		RequestDigest:  "sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
		Surface:        "assistant_run",
		Scope:          "assistant.run.read",
		IdempotencyKey: "intent-1",
		JWTID:          "jti-1",
		IssuedAt:       now.Add(-time.Second).Unix(),
		ExpiresAt:      now.Add(59 * time.Second).Unix(),
	}
}

func delegatedGrantTestExpectation(
	claims DelegatedGrantClaims,
) DelegatedGrantExpectation {
	return DelegatedGrantExpectation{
		Audience:         claims.Audience,
		DelegateService:  claims.DelegateService,
		AccountID:        claims.AccountID,
		PersonaID:        claims.PersonaID,
		RunID:            claims.RunID,
		ToolInvocationID: claims.ToolInvocationID,
		OperationID:      claims.OperationID,
		Resource:         claims.Resource,
		RequestDigest:    claims.RequestDigest,
		Surface:          claims.Surface,
		Scopes:           strings.Fields(claims.Scope),
		IdempotencyKey:   claims.IdempotencyKey,
		ApprovalRef:      claims.ApprovalRef,
	}
}
