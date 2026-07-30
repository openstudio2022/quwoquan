// Package ports declares AccountEnforcementCase persistence and delivery boundaries.
package ports

import (
	"context"
	"errors"
	"strings"
	"time"

	"quwoquan_service/services/product-ops-service/internal/product_ops/account_enforcement_case/domain/model"
)

var (
	ErrAppealIntakeUnavailable     = errors.New("account appeal intake unavailable")
	ErrAppealIntakeInvalid         = errors.New("account appeal intake invalid")
	ErrAppealIntakeAccountMismatch = errors.New("account appeal intake account mismatch")
	ErrAppealIntakeConsumed        = errors.New("account appeal intake already consumed")
)

// AppealIntakeClaim is the minimum identity-safe cross-domain claim. The User
// owner must bind one intake to one account and one Product Ops case. Replaying
// the same tuple is idempotent; another case or account must fail closed.
type AppealIntakeClaim struct {
	IntakeRef string
	AccountID string
	CaseID    string
}

// Valid enforces only Product Ops-owned and transport safety rules before any
// value reaches a URL path or Idempotency-Key header. User remains the sole
// owner of intakeRef and accountId business formats and rejects format drift
// with its typed errors.
func (claim AppealIntakeClaim) Valid() bool {
	return transportSafeOpaque(claim.IntakeRef, 64) &&
		transportSafeOpaque(claim.AccountID, 96) &&
		canonicalAppealCaseID(claim.CaseID)
}

func canonicalAppealCaseID(value string) bool {
	const prefix = "appeal-"
	return strings.HasPrefix(value, prefix) && len(value) > len(prefix) &&
		len(value) <= 128 && lowerToken(value[len(prefix):])
}

func transportSafeOpaque(value string, maxLength int) bool {
	if value == "" || len(value) > maxLength {
		return false
	}
	for _, current := range value {
		if current >= '0' && current <= '9' ||
			current >= 'a' && current <= 'z' ||
			current >= 'A' && current <= 'Z' ||
			current == '-' || current == '.' || current == '_' || current == '~' {
			continue
		}
		return false
	}
	return true
}

func lowerToken(value string) bool {
	for _, current := range value {
		if current >= '0' && current <= '9' ||
			current >= 'a' && current <= 'z' ||
			current == '-' || current == '_' {
			continue
		}
		return false
	}
	return value != ""
}

type AppealIntakeVerifier interface {
	Claim(ctx context.Context, claim AppealIntakeClaim) error
}

type CaseSnapshot struct {
	Case             model.Case
	CommandResult    *CommandResult
	IdempotentReplay bool
}

// CommandResult is the immutable, non-PII response captured by a command receipt.
// It is distinct from the mutable aggregate snapshot returned by a query.
type CommandResult struct {
	CaseID         string               `json:"caseId"`
	CaseKind       model.CaseKind       `json:"caseKind"`
	Status         model.CaseStatus     `json:"status"`
	Version        int64                `json:"version"`
	ApprovalCount  int                  `json:"approvalCount"`
	DecisionID     string               `json:"decisionId,omitempty"`
	DeliveryStatus model.DeliveryStatus `json:"deliveryStatus,omitempty"`
	UpdatedAt      time.Time            `json:"updatedAt"`
}

type CommandReceipt struct {
	IdempotencyKey string
	CommandDigest  string
	CaseID         string
	ResultVersion  int64
	CreatedAt      time.Time
}

type CaseStore interface {
	Replay(
		ctx context.Context,
		idempotencyKey string,
		commandDigest string,
	) (CaseSnapshot, bool, error)
	CommitOpen(
		ctx context.Context,
		current model.Case,
		receipt CommandReceipt,
	) (CaseSnapshot, error)
	Load(ctx context.Context, caseID string) (model.Case, error)
	CommitReview(
		ctx context.Context,
		expectedVersion int64,
		next model.Case,
		review model.Review,
		decision *model.Decision,
		receipt CommandReceipt,
	) (CaseSnapshot, error)
	RecoverDelivery(
		ctx context.Context,
		caseID string,
		receipt CommandReceipt,
		recoveredAt time.Time,
	) (CaseSnapshot, error)
}

type DeliveryJob struct {
	Decision        model.Decision
	Attempts        int
	RetryGeneration int
}

type DeliveryReceipt struct {
	DecisionID       string
	AccountState     string
	AuthEpoch        int64
	IdempotentReplay bool
	OccurredAt       time.Time
	DeliveredAt      time.Time
}

type DeliveryBacklog struct {
	Pending    int64
	Retrying   int64
	DeadLetter int64
	OldestDue  *time.Time
}

type DeliveryStore interface {
	ClaimDue(
		ctx context.Context,
		owner string,
		now time.Time,
		leaseDuration time.Duration,
		limit int,
	) ([]DeliveryJob, error)
	MarkDelivered(
		ctx context.Context,
		owner string,
		receipt DeliveryReceipt,
	) error
	MarkFailed(
		ctx context.Context,
		owner string,
		job DeliveryJob,
		errorClass string,
		permanent bool,
		maxAttempts int,
		nextAttemptAt time.Time,
		failedAt time.Time,
	) (model.DeliveryStatus, error)
	Backlog(ctx context.Context, now time.Time) (DeliveryBacklog, error)
}

type EnforcementTarget interface {
	Apply(
		ctx context.Context,
		decision model.Decision,
	) (DeliveryReceipt, error)
}

type ClassifiedDeliveryError interface {
	error
	ErrorClass() string
	Permanent() bool
}

type Metrics interface {
	ObserveCaseCommand(operation string, outcome string, duration time.Duration)
	ObserveDelivery(action string, outcome string, duration time.Duration)
	SetDeliveryBacklog(state string, count float64)
}
