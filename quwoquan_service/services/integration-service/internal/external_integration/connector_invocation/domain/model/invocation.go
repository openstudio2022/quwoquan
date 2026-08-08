package model

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"strings"
	"time"
)

const (
	StatusAccepted             = "accepted"
	StatusAwaitingConfirmation = "awaiting_confirmation"
	StatusExecuting            = "executing"
	StatusCompleted            = "completed"
	StatusFailed               = "failed"
	StatusCancelled            = "cancelled"
)

var (
	ErrInvalidArgument      = errors.New("connector invocation request is invalid")
	ErrNotFound             = errors.New("connector invocation not found")
	ErrConnectionNotFound   = errors.New("connector connection not found")
	ErrConnectionInactive   = errors.New("connector connection is inactive")
	ErrCapabilityDenied     = errors.New("connector capability denied")
	ErrConfirmationRequired = errors.New("connector confirmation is required")
	ErrRevisionConflict     = errors.New("connector invocation revision conflict")
	ErrIdempotencyConflict  = errors.New("connector invocation idempotency conflict")
	ErrStorageUnavailable   = errors.New("connector invocation storage unavailable")
)

type Invocation struct {
	InvocationID          string     `json:"invocationId" bson:"invocationId"`
	AccountID             string     `json:"-" bson:"accountId"`
	ResolutionID          string     `json:"-" bson:"resolutionId"`
	ConnectionID          string     `json:"connectionId" bson:"connectionId"`
	AssistantRunID        string     `json:"-" bson:"assistantRunId"`
	Capability            string     `json:"capability" bson:"capability"`
	SurfaceKind           string     `json:"-" bson:"surfaceKind"`
	BindingDigest         string     `json:"-" bson:"bindingDigest"`
	InputDigest           string     `json:"-" bson:"inputDigest"`
	ConfirmationDigest    string     `json:"-" bson:"confirmationDigest"`
	PermitDigest          string     `json:"-" bson:"permitDigest"`
	IdempotencyDigest     string     `json:"-" bson:"idempotencyDigest"`
	Status                string     `json:"status" bson:"status"`
	RequestDigest         string     `json:"-" bson:"requestDigest"`
	ConfirmationRef       string     `json:"-" bson:"confirmationRef,omitempty"`
	PermitRef             string     `json:"-" bson:"permitRef,omitempty"`
	IdempotencyKey        string     `json:"-" bson:"idempotencyKey,omitempty"`
	ContinuationRef       string     `json:"continuationRef,omitempty" bson:"continuationRef,omitempty"`
	ResultRef             string     `json:"-" bson:"resultRef,omitempty"`
	ResultDigest          string     `json:"-" bson:"resultDigest,omitempty"`
	NormalizedFailureCode string     `json:"normalizedFailureCode,omitempty" bson:"normalizedFailureCode,omitempty"`
	RecoveryAction        string     `json:"recoveryAction" bson:"recoveryAction"`
	Revision              int64      `json:"revision" bson:"revision"`
	Attempt               int        `json:"-" bson:"attempt"`
	LeaseOwner            string     `json:"-" bson:"leaseOwner,omitempty"`
	LeaseExpiresAt        *time.Time `json:"-" bson:"leaseExpiresAt,omitempty"`
	CreatedAt             time.Time  `json:"createdAt" bson:"createdAt"`
	UpdatedAt             time.Time  `json:"updatedAt" bson:"updatedAt"`
	CompletedAt           *time.Time `json:"completedAt,omitempty" bson:"completedAt,omitempty"`
}

type AcceptInput struct {
	InvocationID         string
	AccountID            string
	ResolutionID         string
	ConnectionID         string
	AssistantRunID       string
	Capability           string
	SurfaceKind          string
	BindingDigest        string
	InputDigest          string
	PayloadRef           string
	ConfirmationRef      string
	PermitRef            string
	ContinuationRef      string
	IdempotencyKey       string
	ConfirmationRequired bool
	OccurredAt           time.Time
}

type AcceptCommand struct {
	Invocation     Invocation
	PayloadRef     string
	IdempotencyKey string
	CommandDigest  string
}

type ContinueInput struct {
	InvocationID     string
	AccountID        string
	ConfirmationRef  string
	ContinuationRef  string
	ExpectedRevision int64
	IdempotencyKey   string
	OccurredAt       time.Time
}

type MutationResult struct {
	Invocation Invocation
	Replayed   bool
}

type ExecutionClaim struct {
	Invocation Invocation
	PayloadRef string
}

type CompleteInput struct {
	InvocationID          string
	AccountID             string
	LeaseOwner            string
	ExpectedRevision      int64
	Status                string
	ResultRef             string
	ResultDigest          string
	ContinuationRef       string
	NormalizedFailureCode string
	RecoveryAction        string
	OccurredAt            time.Time
}

func NewAcceptCommand(input AcceptInput) (AcceptCommand, error) {
	input.InvocationID = strings.TrimSpace(input.InvocationID)
	input.AccountID = strings.TrimSpace(input.AccountID)
	input.ResolutionID = strings.TrimSpace(input.ResolutionID)
	input.ConnectionID = strings.TrimSpace(input.ConnectionID)
	input.AssistantRunID = strings.TrimSpace(input.AssistantRunID)
	input.Capability = strings.TrimSpace(input.Capability)
	input.SurfaceKind = strings.TrimSpace(input.SurfaceKind)
	input.BindingDigest = strings.TrimSpace(input.BindingDigest)
	input.InputDigest = strings.TrimSpace(input.InputDigest)
	input.PayloadRef = strings.TrimSpace(input.PayloadRef)
	input.ConfirmationRef = strings.TrimSpace(input.ConfirmationRef)
	input.PermitRef = strings.TrimSpace(input.PermitRef)
	input.ContinuationRef = strings.TrimSpace(input.ContinuationRef)
	input.IdempotencyKey = strings.TrimSpace(input.IdempotencyKey)
	input.OccurredAt = input.OccurredAt.UTC()
	if input.InvocationID == "" || input.AccountID == "" || input.ResolutionID == "" ||
		input.ConnectionID == "" ||
		input.AssistantRunID == "" || input.Capability == "" || input.PayloadRef == "" ||
		input.SurfaceKind == "" || !validDigest(input.BindingDigest) ||
		!validDigest(input.InputDigest) || input.ConfirmationRef == "" ||
		input.PermitRef == "" || input.IdempotencyKey == "" || input.OccurredAt.IsZero() {
		return AcceptCommand{}, ErrInvalidArgument
	}
	confirmationDigest := digest(input.ConfirmationRef)
	permitDigest := digest(input.PermitRef)
	idempotencyDigest := digest(input.IdempotencyKey)
	requestDigest := digest(strings.Join([]string{
		input.AccountID, input.ResolutionID, input.ConnectionID, input.AssistantRunID,
		input.Capability, input.SurfaceKind, input.BindingDigest, input.InputDigest,
		confirmationDigest, permitDigest, idempotencyDigest, input.PayloadRef,
	}, "\x00"))
	commandDigest := digest(strings.Join([]string{
		requestDigest, input.ConfirmationRef, input.ContinuationRef,
	}, "\x00"))
	return AcceptCommand{
		Invocation: Invocation{
			InvocationID: input.InvocationID, AccountID: input.AccountID,
			ResolutionID: input.ResolutionID,
			ConnectionID: input.ConnectionID, AssistantRunID: input.AssistantRunID,
			Capability: input.Capability, SurfaceKind: input.SurfaceKind,
			BindingDigest: input.BindingDigest, InputDigest: input.InputDigest,
			ConfirmationDigest: confirmationDigest, PermitDigest: permitDigest,
			IdempotencyDigest: idempotencyDigest,
			Status:            StatusAccepted, RequestDigest: requestDigest,
			ConfirmationRef: input.ConfirmationRef, PermitRef: input.PermitRef,
			IdempotencyKey: input.IdempotencyKey, ContinuationRef: input.ContinuationRef,
			RecoveryAction: "none", Revision: 1,
			CreatedAt: input.OccurredAt, UpdatedAt: input.OccurredAt,
		},
		PayloadRef: input.PayloadRef, IdempotencyKey: input.IdempotencyKey,
		CommandDigest: commandDigest,
	}, nil
}

func NewContinueInput(input ContinueInput) (ContinueInput, error) {
	input.InvocationID = strings.TrimSpace(input.InvocationID)
	input.AccountID = strings.TrimSpace(input.AccountID)
	input.ConfirmationRef = strings.TrimSpace(input.ConfirmationRef)
	input.ContinuationRef = strings.TrimSpace(input.ContinuationRef)
	input.IdempotencyKey = strings.TrimSpace(input.IdempotencyKey)
	input.OccurredAt = input.OccurredAt.UTC()
	if input.InvocationID == "" || input.AccountID == "" ||
		input.ConfirmationRef == "" || input.ExpectedRevision <= 0 ||
		input.IdempotencyKey == "" || input.OccurredAt.IsZero() {
		return ContinueInput{}, ErrInvalidArgument
	}
	return input, nil
}

func NewCompleteInput(input CompleteInput) (CompleteInput, error) {
	input.InvocationID = strings.TrimSpace(input.InvocationID)
	input.AccountID = strings.TrimSpace(input.AccountID)
	input.LeaseOwner = strings.TrimSpace(input.LeaseOwner)
	input.Status = strings.TrimSpace(input.Status)
	input.ResultRef = strings.TrimSpace(input.ResultRef)
	input.ResultDigest = strings.TrimSpace(input.ResultDigest)
	input.ContinuationRef = strings.TrimSpace(input.ContinuationRef)
	input.NormalizedFailureCode = strings.TrimSpace(input.NormalizedFailureCode)
	input.RecoveryAction = strings.TrimSpace(input.RecoveryAction)
	input.OccurredAt = input.OccurredAt.UTC()
	if input.InvocationID == "" || input.AccountID == "" || input.LeaseOwner == "" ||
		input.ExpectedRevision <= 0 || input.OccurredAt.IsZero() ||
		(input.Status != StatusCompleted && input.Status != StatusFailed) {
		return CompleteInput{}, ErrInvalidArgument
	}
	if input.Status == StatusCompleted {
		if input.ResultRef == "" || !validDigest(input.ResultDigest) ||
			input.NormalizedFailureCode != "" || input.RecoveryAction != "none" {
			return CompleteInput{}, ErrInvalidArgument
		}
	}
	if input.Status == StatusFailed {
		if input.ResultRef != "" || input.NormalizedFailureCode == "" ||
			input.RecoveryAction == "" || input.RecoveryAction == "none" {
			return CompleteInput{}, ErrInvalidArgument
		}
	}
	return input, nil
}

func digest(value string) string {
	sum := sha256.Sum256([]byte(value))
	return "sha256:" + hex.EncodeToString(sum[:])
}

func validDigest(value string) bool {
	if !strings.HasPrefix(value, "sha256:") || len(value) != len("sha256:")+sha256.Size*2 {
		return false
	}
	_, err := hex.DecodeString(strings.TrimPrefix(value, "sha256:"))
	return err == nil
}
