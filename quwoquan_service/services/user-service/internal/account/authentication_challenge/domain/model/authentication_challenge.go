// Package model 定义 AuthenticationChallenge 聚合及其短生命周期状态机。
// 聚合只保存不可逆 secretRef 与 completion fingerprint；明文凭据只能作为
// application 层的瞬时输入，不能进入本包状态、错误或事件。
package model

import (
	"crypto/subtle"
	"errors"
	"fmt"
	"strings"
	"time"
)

var (
	ErrInvalidChallenge = errors.New("authentication challenge is invalid")
	ErrVersionConflict  = errors.New("authentication challenge version conflict")
)

type Status string

const (
	StatusPending   Status = "pending"
	StatusCompleted Status = "completed"
	StatusExpired   Status = "expired"
	StatusLocked    Status = "locked"
	StatusCancelled Status = "cancelled"
)

func (status Status) Valid() bool {
	switch status {
	case StatusPending, StatusCompleted, StatusExpired, StatusLocked, StatusCancelled:
		return true
	default:
		return false
	}
}

type VerificationOutcome string

const (
	VerificationSucceeded VerificationOutcome = "succeeded"
	VerificationReplayed  VerificationOutcome = "replayed"
	VerificationMismatch  VerificationOutcome = "mismatch"
	VerificationLocked    VerificationOutcome = "locked"
	VerificationExpired   VerificationOutcome = "expired"
	VerificationConsumed  VerificationOutcome = "consumed"
	VerificationCancelled VerificationOutcome = "cancelled"
)

type CreateParams struct {
	ID              string
	AccountID       string
	Purpose         string
	Channel         string
	DestinationHash string
	SecretRef       string
	ExpiresAt       time.Time
	CreatedAt       time.Time
}

// State 是对象专属 Store 的持久化形态。SecretRef 与 CompletionFingerprint
// 均为不可逆引用；禁止给该类型增加 JSON 标签或向 transport 暴露。
type State struct {
	ID                    string
	AccountID             string
	Purpose               string
	Channel               string
	DestinationHash       string
	SecretRef             string
	Status                Status
	AttemptCount          int
	ExpiresAt             time.Time
	CreatedAt             time.Time
	CompletedAt           *time.Time
	CompletionFingerprint string
	Version               int64
	UpdatedAt             time.Time
}

// Snapshot 是 application 可返回的脱敏聚合快照，不含 secretRef 或完成凭据指纹。
type Snapshot struct {
	ID              string
	AccountID       string
	Purpose         string
	Channel         string
	DestinationHash string
	Status          Status
	AttemptCount    int
	ExpiresAt       time.Time
	CreatedAt       time.Time
	CompletedAt     *time.Time
	Version         int64
	UpdatedAt       time.Time
}

type AuthenticationChallenge struct {
	state State
}

func New(params CreateParams) (AuthenticationChallenge, error) {
	state := State{
		ID:              strings.TrimSpace(params.ID),
		AccountID:       strings.TrimSpace(params.AccountID),
		Purpose:         strings.TrimSpace(params.Purpose),
		Channel:         strings.TrimSpace(params.Channel),
		DestinationHash: strings.TrimSpace(params.DestinationHash),
		SecretRef:       strings.TrimSpace(params.SecretRef),
		Status:          StatusPending,
		ExpiresAt:       params.ExpiresAt.UTC(),
		CreatedAt:       params.CreatedAt.UTC(),
		Version:         1,
		UpdatedAt:       params.CreatedAt.UTC(),
	}
	return Restore(state)
}

func Restore(state State) (AuthenticationChallenge, error) {
	state.ID = strings.TrimSpace(state.ID)
	state.AccountID = strings.TrimSpace(state.AccountID)
	state.Purpose = strings.TrimSpace(state.Purpose)
	state.Channel = strings.TrimSpace(state.Channel)
	state.DestinationHash = strings.TrimSpace(state.DestinationHash)
	state.SecretRef = strings.TrimSpace(state.SecretRef)
	state.CompletionFingerprint = strings.TrimSpace(state.CompletionFingerprint)
	state.ExpiresAt = state.ExpiresAt.UTC()
	state.CreatedAt = state.CreatedAt.UTC()
	state.UpdatedAt = state.UpdatedAt.UTC()
	state.CompletedAt = cloneTime(state.CompletedAt)
	if err := validateState(state); err != nil {
		return AuthenticationChallenge{}, err
	}
	return AuthenticationChallenge{state: state}, nil
}

func (challenge AuthenticationChallenge) State() State {
	state := challenge.state
	state.CompletedAt = cloneTime(challenge.state.CompletedAt)
	return state
}

func (challenge AuthenticationChallenge) Snapshot() Snapshot {
	state := challenge.State()
	return Snapshot{
		ID:              state.ID,
		AccountID:       state.AccountID,
		Purpose:         state.Purpose,
		Channel:         state.Channel,
		DestinationHash: state.DestinationHash,
		Status:          state.Status,
		AttemptCount:    state.AttemptCount,
		ExpiresAt:       state.ExpiresAt,
		CreatedAt:       state.CreatedAt,
		CompletedAt:     cloneTime(state.CompletedAt),
		Version:         state.Version,
		UpdatedAt:       state.UpdatedAt,
	}
}

func (challenge AuthenticationChallenge) Validate() error {
	return validateState(challenge.state)
}

type VerificationAttempt struct {
	CompletionFingerprint string
	Matched               bool
	AttemptedAt           time.Time
	MaxAttempts           int
}

type VerificationTransition struct {
	Aggregate AuthenticationChallenge
	Outcome   VerificationOutcome
	Changed   bool
}

func (challenge AuthenticationChallenge) Verify(
	attempt VerificationAttempt,
) (VerificationTransition, error) {
	if err := challenge.Validate(); err != nil {
		return VerificationTransition{}, err
	}
	attempt.CompletionFingerprint = strings.TrimSpace(attempt.CompletionFingerprint)
	if attempt.CompletionFingerprint == "" ||
		attempt.AttemptedAt.IsZero() ||
		attempt.MaxAttempts <= 0 {
		return VerificationTransition{}, fmt.Errorf(
			"%w: verification evidence, clock and positive attempt limit are required",
			ErrInvalidChallenge,
		)
	}
	attempt.AttemptedAt = attempt.AttemptedAt.UTC()

	switch challenge.state.Status {
	case StatusCompleted:
		outcome := VerificationConsumed
		if equalFingerprint(
			challenge.state.CompletionFingerprint,
			attempt.CompletionFingerprint,
		) {
			outcome = VerificationReplayed
		}
		return unchangedVerification(challenge, outcome), nil
	case StatusExpired:
		return unchangedVerification(challenge, VerificationExpired), nil
	case StatusLocked:
		return unchangedVerification(challenge, VerificationLocked), nil
	case StatusCancelled:
		return unchangedVerification(challenge, VerificationCancelled), nil
	case StatusPending:
		// 继续执行下面的 pending 状态迁移。
	default:
		return VerificationTransition{}, fmt.Errorf(
			"%w: unknown challenge status",
			ErrInvalidChallenge,
		)
	}

	next := challenge.State()
	if !attempt.AttemptedAt.Before(next.ExpiresAt) {
		next.Status = StatusExpired
		return changedVerification(next, attempt.AttemptedAt, VerificationExpired)
	}
	if attempt.Matched {
		completedAt := attempt.AttemptedAt
		next.Status = StatusCompleted
		next.CompletedAt = &completedAt
		next.CompletionFingerprint = attempt.CompletionFingerprint
		return changedVerification(next, attempt.AttemptedAt, VerificationSucceeded)
	}

	next.AttemptCount++
	outcome := VerificationMismatch
	if next.AttemptCount >= attempt.MaxAttempts {
		next.Status = StatusLocked
		outcome = VerificationLocked
	}
	return changedVerification(next, attempt.AttemptedAt, outcome)
}

type Mutation struct {
	Aggregate AuthenticationChallenge
	Changed   bool
}

// Cancel 只允许 pending -> cancelled；所有终态重复取消均为稳定 no-op。
func (challenge AuthenticationChallenge) Cancel(now time.Time) (Mutation, error) {
	if err := challenge.Validate(); err != nil {
		return Mutation{}, err
	}
	if now.IsZero() {
		return Mutation{}, fmt.Errorf("%w: cancellation clock is required", ErrInvalidChallenge)
	}
	if challenge.state.Status != StatusPending {
		return Mutation{Aggregate: challenge}, nil
	}
	state := challenge.State()
	state.Status = StatusCancelled
	state.Version++
	state.UpdatedAt = now.UTC()
	cancelled, err := Restore(state)
	if err != nil {
		return Mutation{}, err
	}
	return Mutation{Aggregate: cancelled, Changed: true}, nil
}

func changedVerification(
	state State,
	occurredAt time.Time,
	outcome VerificationOutcome,
) (VerificationTransition, error) {
	state.Version++
	state.UpdatedAt = occurredAt.UTC()
	updated, err := Restore(state)
	if err != nil {
		return VerificationTransition{}, err
	}
	return VerificationTransition{
		Aggregate: updated,
		Outcome:   outcome,
		Changed:   true,
	}, nil
}

func unchangedVerification(
	challenge AuthenticationChallenge,
	outcome VerificationOutcome,
) VerificationTransition {
	return VerificationTransition{
		Aggregate: challenge,
		Outcome:   outcome,
	}
}

func validateState(state State) error {
	if invalidText(state.ID, 128) ||
		invalidOptionalText(state.AccountID, 96) ||
		invalidText(state.Purpose, 64) ||
		invalidText(state.Channel, 32) ||
		invalidOptionalText(state.DestinationHash, 256) ||
		invalidText(state.SecretRef, 1024) {
		return fmt.Errorf("%w: identity or immutable attributes are invalid", ErrInvalidChallenge)
	}
	if !state.Status.Valid() ||
		state.AttemptCount < 0 ||
		state.Version < 1 ||
		state.CreatedAt.IsZero() ||
		state.ExpiresAt.IsZero() ||
		state.UpdatedAt.IsZero() ||
		!state.ExpiresAt.After(state.CreatedAt) ||
		state.UpdatedAt.Before(state.CreatedAt) {
		return fmt.Errorf("%w: lifecycle attributes are invalid", ErrInvalidChallenge)
	}
	if state.Status == StatusCompleted {
		if state.CompletedAt == nil ||
			state.CompletedAt.Before(state.CreatedAt) ||
			state.CompletionFingerprint == "" {
			return fmt.Errorf("%w: completed receipt is incomplete", ErrInvalidChallenge)
		}
		return nil
	}
	if state.CompletedAt != nil || state.CompletionFingerprint != "" {
		return fmt.Errorf(
			"%w: only completed challenges may hold completion receipt",
			ErrInvalidChallenge,
		)
	}
	return nil
}

func invalidText(value string, maxLength int) bool {
	return value == "" || strings.TrimSpace(value) != value || len(value) > maxLength
}

func invalidOptionalText(value string, maxLength int) bool {
	return value != "" && (strings.TrimSpace(value) != value || len(value) > maxLength)
}

func equalFingerprint(left, right string) bool {
	leftBytes := []byte(left)
	rightBytes := []byte(right)
	return len(leftBytes) == len(rightBytes) &&
		subtle.ConstantTimeCompare(leftBytes, rightBytes) == 1
}

func cloneTime(value *time.Time) *time.Time {
	if value == nil {
		return nil
	}
	cloned := value.UTC()
	return &cloned
}
