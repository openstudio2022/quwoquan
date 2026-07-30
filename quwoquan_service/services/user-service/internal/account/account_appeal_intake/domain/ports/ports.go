// Package ports declares AccountAppealIntake identity, persistence and
// observability boundaries.
package ports

import (
	"context"
	"errors"
	"time"

	"quwoquan_service/services/user-service/internal/account/account_appeal_intake/domain/model"
)

var (
	ErrIdentityNotFound    = errors.New("account appeal identity not found")
	ErrCredentialInvalid   = errors.New("account appeal credential invalid")
	ErrCredentialExpired   = errors.New("account appeal credential expired")
	ErrCredentialConsumed  = errors.New("account appeal credential consumed")
	ErrAccountNotSuspended = errors.New("account appeal account is not suspended")
	ErrRateLimited         = errors.New("account appeal rate limited")
	ErrIntakeNotFound      = errors.New("account appeal intake not found")
	ErrAccountMismatch     = errors.New("account appeal intake account mismatch")
	ErrIntakeClaimed       = errors.New("account appeal intake claimed")
	ErrIdempotencyConflict = errors.New("account appeal idempotency conflict")
)

type IdentityChallengeEvidence struct {
	ChallengeID string
	AccountID   string
	ExpiresAt   time.Time
}

// IdentityChallengeVerifier consumes the existing AuthenticationChallenge and
// CredentialBinding truths; AccountAppealIntake never creates another phone
// identity registry.
type IdentityChallengeVerifier interface {
	VerifyAccountAppealChallenge(
		ctx context.Context,
		phone string,
		otpCode []byte,
		challengeID string,
	) (IdentityChallengeEvidence, error)
}

type IssueCredentialCommit struct {
	CredentialID     string
	CredentialDigest string
	ChallengeID      string
	AccountID        string
	IssuedAt         time.Time
	ExpiresAt        time.Time
	DeleteAfter      time.Time
}

type CredentialReceipt struct {
	ExpiresAt time.Time
}

type SubmitCommit struct {
	CredentialDigest string
	IntakeRef        string
	IdempotencyKey   string
	CommandDigest    string
	SubmittedAt      time.Time
	DeleteAfter      time.Time
}

type ClaimCommit struct {
	IntakeRef      string
	AccountID      string
	CaseID         string
	IdempotencyKey string
	CommandDigest  string
	ClaimedAt      time.Time
}

type CommandResult struct {
	Intake           model.AccountAppealIntake
	IdempotentReplay bool
}

// Store owns both the aggregate row and its private single-use credential
// entity. Each method is an atomic PostgreSQL packet.
type Store interface {
	IssueCredential(context.Context, IssueCredentialCommit) (CredentialReceipt, error)
	Submit(context.Context, SubmitCommit) (CommandResult, error)
	Claim(context.Context, ClaimCommit) (CommandResult, error)
	PurgeExpired(context.Context, time.Time) (credentials int64, intakes int64, err error)
}

type Metrics interface {
	ObserveCommand(operation string, outcome string, duration time.Duration)
	AddPurged(entity string, count float64)
}
