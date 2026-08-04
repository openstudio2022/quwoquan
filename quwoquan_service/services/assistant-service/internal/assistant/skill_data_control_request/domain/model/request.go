// Package model owns SkillDataControlRequest lifecycle invariants.
package model

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"sort"
	"strconv"
	"strings"
	"time"
)

const (
	ActionHideActivityHistory  = "hide_activity_history"
	ActionRevokeConsent        = "revoke_consent"
	ActionArchiveSubscriptions = "archive_subscriptions"

	StatusPendingConfirmation = "pending_confirmation"
	StatusExecuting           = "executing"
	StatusCompleted           = "completed"
	StatusCancelled           = "cancelled"
	StatusFailed              = "failed"

	CommandCreate  = "CreateSkillDataControlRequest"
	CommandConfirm = "ConfirmSkillDataControlRequest"

	EventRequested = "SkillDataControlRequested"
	EventConfirmed = "SkillDataControlConfirmed"
	EventCompleted = "SkillDataControlCompleted"
	EventCancelled = "SkillDataControlCancelled"
	EventFailed    = "SkillDataControlFailed"
)

var (
	ErrInvalidArgument     = errors.New("skill data control request is invalid")
	ErrNotFound            = errors.New("skill data control request not found")
	ErrRevisionConflict    = errors.New("skill data control request revision conflict")
	ErrIdempotencyConflict = errors.New("skill data control idempotency conflict")
	ErrActionFailed        = errors.New("skill data control action failed")
	ErrStorageUnavailable  = errors.New("skill data control storage unavailable")
)

type Request struct {
	RequestID        string     `json:"requestId" bson:"_id"`
	AccountID        string     `json:"-" bson:"accountId"`
	SkillID          string     `json:"skillId" bson:"skillId"`
	RequestedActions []string   `json:"requestedActions" bson:"requestedActions"`
	CompletedActions []string   `json:"completedActions" bson:"completedActions"`
	Status           string     `json:"status" bson:"status"`
	FailedAction     string     `json:"failedAction,omitempty" bson:"failedAction,omitempty"`
	FailureCode      string     `json:"failureCode,omitempty" bson:"failureCode,omitempty"`
	ConfirmedAt      *time.Time `json:"confirmedAt,omitempty" bson:"confirmedAt,omitempty"`
	CompletedAt      *time.Time `json:"completedAt,omitempty" bson:"completedAt,omitempty"`
	CreatedAt        time.Time  `json:"createdAt" bson:"createdAt"`
	UpdatedAt        time.Time  `json:"updatedAt" bson:"updatedAt"`
	Revision         int64      `json:"revision" bson:"revision"`
	LeaseOwner       string     `json:"-" bson:"leaseOwner,omitempty"`
	LeaseToken       int64      `json:"-" bson:"leaseToken"`
	LeaseExpiresAt   *time.Time `json:"-" bson:"leaseExpiresAt,omitempty"`
	LeaseHeartbeatAt *time.Time `json:"-" bson:"leaseHeartbeatAt,omitempty"`
}

type ExecutionFence struct {
	AccountID      string
	RequestID      string
	WorkerID       string
	Token          int64
	LeaseExpiresAt time.Time
}

type ExecutionClaim struct {
	Request Request
	Fence   ExecutionFence
}

func NewRequest(
	requestID string,
	accountID string,
	skillID string,
	actions []string,
	at time.Time,
) (Request, error) {
	requestID = strings.TrimSpace(requestID)
	accountID = strings.TrimSpace(accountID)
	skillID = strings.TrimSpace(skillID)
	actions, err := NormalizeActions(actions)
	if err != nil || requestID == "" || accountID == "" || skillID == "" || at.IsZero() {
		return Request{}, ErrInvalidArgument
	}
	at = at.UTC()
	return Request{
		RequestID:        requestID,
		AccountID:        accountID,
		SkillID:          skillID,
		RequestedActions: actions,
		CompletedActions: []string{},
		Status:           StatusPendingConfirmation,
		CreatedAt:        at,
		UpdatedAt:        at,
		Revision:         1,
	}, nil
}

func (request Request) HasCompleted(action string) bool {
	action = strings.TrimSpace(action)
	for _, completed := range request.CompletedActions {
		if completed == action {
			return true
		}
	}
	return false
}

func (request Request) Validate() error {
	if strings.TrimSpace(request.RequestID) == "" ||
		strings.TrimSpace(request.AccountID) == "" ||
		strings.TrimSpace(request.SkillID) == "" ||
		request.Revision < 1 || request.CreatedAt.IsZero() || request.UpdatedAt.IsZero() {
		return ErrInvalidArgument
	}
	if request.LeaseToken < 0 {
		return ErrInvalidArgument
	}
	actions, err := NormalizeActions(request.RequestedActions)
	if err != nil || len(actions) != len(request.RequestedActions) {
		return ErrInvalidArgument
	}
	for index := range actions {
		if actions[index] != request.RequestedActions[index] {
			return ErrInvalidArgument
		}
	}
	seen := map[string]struct{}{}
	for _, action := range request.CompletedActions {
		if !contains(actions, action) {
			return ErrInvalidArgument
		}
		if _, duplicate := seen[action]; duplicate {
			return ErrInvalidArgument
		}
		seen[action] = struct{}{}
	}
	switch request.Status {
	case StatusPendingConfirmation, StatusExecuting, StatusCompleted, StatusCancelled, StatusFailed:
	default:
		return ErrInvalidArgument
	}
	leaseOwner := strings.TrimSpace(request.LeaseOwner)
	if leaseOwner == "" {
		if request.LeaseExpiresAt != nil || request.LeaseHeartbeatAt != nil {
			return ErrInvalidArgument
		}
	} else if request.Status != StatusExecuting || request.LeaseToken < 1 ||
		request.LeaseExpiresAt == nil || request.LeaseHeartbeatAt == nil ||
		request.LeaseExpiresAt.IsZero() || request.LeaseHeartbeatAt.IsZero() ||
		!request.LeaseExpiresAt.After(*request.LeaseHeartbeatAt) {
		return ErrInvalidArgument
	}
	return nil
}

func NewExecutionFence(request Request) (ExecutionFence, error) {
	if err := request.Validate(); err != nil || request.Status != StatusExecuting ||
		strings.TrimSpace(request.LeaseOwner) == "" || request.LeaseExpiresAt == nil {
		return ExecutionFence{}, ErrInvalidArgument
	}
	return ExecutionFence{
		AccountID:      request.AccountID,
		RequestID:      request.RequestID,
		WorkerID:       request.LeaseOwner,
		Token:          request.LeaseToken,
		LeaseExpiresAt: request.LeaseExpiresAt.UTC(),
	}, nil
}

type CreateCommand struct {
	Request        Request
	IdempotencyKey string
	RequestDigest  string
}

func NewCreateCommand(request Request, idempotencyKey string) (CreateCommand, error) {
	idempotencyKey = strings.TrimSpace(idempotencyKey)
	if err := request.Validate(); err != nil || idempotencyKey == "" || len(idempotencyKey) > 160 {
		return CreateCommand{}, ErrInvalidArgument
	}
	digest := digestParts(
		CommandCreate,
		request.AccountID,
		request.SkillID,
		strings.Join(request.RequestedActions, "\x1e"),
	)
	return CreateCommand{Request: request, IdempotencyKey: idempotencyKey, RequestDigest: digest}, nil
}

type ConfirmCommand struct {
	AccountID        string
	RequestID        string
	ExpectedRevision int64
	Confirmed        bool
	IdempotencyKey   string
	RequestDigest    string
	OccurredAt       time.Time
}

func NewConfirmCommand(
	accountID string,
	requestID string,
	expectedRevision int64,
	confirmed bool,
	idempotencyKey string,
	at time.Time,
) (ConfirmCommand, error) {
	accountID = strings.TrimSpace(accountID)
	requestID = strings.TrimSpace(requestID)
	idempotencyKey = strings.TrimSpace(idempotencyKey)
	if accountID == "" || requestID == "" || expectedRevision < 1 ||
		idempotencyKey == "" || len(idempotencyKey) > 160 || at.IsZero() {
		return ConfirmCommand{}, ErrInvalidArgument
	}
	confirmedWire := "false"
	if confirmed {
		confirmedWire = "true"
	}
	return ConfirmCommand{
		AccountID:        accountID,
		RequestID:        requestID,
		ExpectedRevision: expectedRevision,
		Confirmed:        confirmed,
		IdempotencyKey:   idempotencyKey,
		RequestDigest: digestParts(
			CommandConfirm,
			accountID,
			requestID,
			confirmedWire,
			strconv.FormatInt(expectedRevision, 10),
		),
		OccurredAt: at.UTC(),
	}, nil
}

type MutationResult struct {
	Request  Request `json:"request"`
	Replayed bool    `json:"replayed"`
}

type ActivityEvent struct {
	EventID      string
	EventType    string
	RequestID    string
	AccountID    string
	SkillID      string
	Status       string
	FailedAction string
	FailureCode  string
	Revision     int64
	OccurredAt   time.Time
}

func NormalizeActions(values []string) ([]string, error) {
	if len(values) == 0 || len(values) > 3 {
		return nil, ErrInvalidArgument
	}
	seen := map[string]struct{}{}
	result := make([]string, 0, len(values))
	for _, raw := range values {
		action := strings.TrimSpace(raw)
		switch action {
		case ActionHideActivityHistory, ActionRevokeConsent, ActionArchiveSubscriptions:
		default:
			return nil, ErrInvalidArgument
		}
		if _, duplicate := seen[action]; duplicate {
			return nil, ErrInvalidArgument
		}
		seen[action] = struct{}{}
		result = append(result, action)
	}
	sort.Strings(result)
	return result, nil
}

func digestParts(parts ...string) string {
	digest := sha256.Sum256([]byte(strings.Join(parts, "\x1f")))
	return hex.EncodeToString(digest[:])
}

func contains(values []string, value string) bool {
	for _, candidate := range values {
		if candidate == value {
			return true
		}
	}
	return false
}
