package model

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"sort"
	"strings"
	"time"
)

const (
	StatusPending  = "pending"
	StatusVerified = "verified"
	StatusConsumed = "consumed"
	StatusExpired  = "expired"
	StatusRevoked  = "revoked"
	StatusFailed   = "failed"

	ModeDeviceNative = "device_native"
	ModeOAuth2       = "oauth2"
)

var (
	ErrInvalidArgument      = errors.New("connector authorization request is invalid")
	ErrNotFound             = errors.New("connector authorization not found")
	ErrUnauthorized         = errors.New("connector authorization is not owned by the account")
	ErrDefinitionNotFound   = errors.New("connector definition not found")
	ErrCapabilityDenied     = errors.New("connector authorization capability denied")
	ErrModeUnsupported      = errors.New("connector authorization mode is unsupported")
	ErrModeMismatch         = errors.New("connector authorization mode mismatch")
	ErrExpired              = errors.New("connector authorization expired")
	ErrNativeProofInvalid   = errors.New("connector native grant proof is invalid")
	ErrOAuthCallbackInvalid = errors.New("connector oauth callback is invalid")
	ErrProviderUnavailable  = errors.New("connector authorization provider unavailable")
	ErrRevisionConflict     = errors.New("connector authorization revision conflict")
	ErrIdempotencyConflict  = errors.New("connector authorization idempotency conflict")
	ErrStorageUnavailable   = errors.New("connector authorization storage unavailable")
	ErrGrantAlreadyConsumed = errors.New("connector authorization grant already consumed")
)

type Authorization struct {
	AuthorizationID       string     `json:"authorizationId" bson:"authorizationId"`
	AccountID             string     `json:"-" bson:"accountId"`
	ConnectorID           string     `json:"connectorId" bson:"connectorId"`
	AuthorizationMode     string     `json:"authorizationMode" bson:"authorizationMode"`
	RequestedCapabilities []string   `json:"requestedCapabilities" bson:"requestedCapabilities"`
	GrantedCapabilities   []string   `json:"grantedCapabilities" bson:"grantedCapabilities"`
	Status                string     `json:"status" bson:"status"`
	ContinuationDigest    string     `json:"-" bson:"continuationDigest"`
	ProofDigest           string     `json:"-" bson:"proofDigest,omitempty"`
	GrantReceiptDigest    string     `json:"-" bson:"grantReceiptDigest,omitempty"`
	CredentialRef         string     `json:"-" bson:"credentialRef,omitempty"`
	ExpiresAt             time.Time  `json:"expiresAt" bson:"expiresAt"`
	VerifiedAt            *time.Time `json:"verifiedAt,omitempty" bson:"verifiedAt,omitempty"`
	ConsumedAt            *time.Time `json:"-" bson:"consumedAt,omitempty"`
	Revision              int64      `json:"revision" bson:"revision"`
	CreatedAt             time.Time  `json:"createdAt" bson:"createdAt"`
	UpdatedAt             time.Time  `json:"updatedAt" bson:"updatedAt"`
}

type GrantReceipt struct {
	AuthorizationID        string     `bson:"authorizationId"`
	AccountID              string     `bson:"accountId"`
	ConnectorID            string     `bson:"connectorId"`
	AuthorizationMode      string     `bson:"authorizationMode"`
	GrantedCapabilities    []string   `bson:"grantedCapabilities"`
	CredentialRef          string     `bson:"credentialRef"`
	ProofDigest            string     `bson:"proofDigest"`
	GrantReceiptDigest     string     `bson:"grantReceiptDigest"`
	ExpiresAt              time.Time  `bson:"expiresAt"`
	CredentialExpiresAt    *time.Time `bson:"credentialExpiresAt,omitempty"`
	ConsumedByConnectionID string     `bson:"consumedByConnectionId,omitempty"`
	ConsumedAt             *time.Time `bson:"consumedAt,omitempty"`
	CreatedAt              time.Time  `bson:"createdAt"`
}

type StartInput struct {
	AccountID             string
	ConnectorID           string
	RequestedCapabilities []string
	IdempotencyKey        string
}

type StartCommand struct {
	Authorization   Authorization
	ContinuationRef string
	IdempotencyKey  string
	CommandDigest   string
}

type CompleteInput struct {
	AccountID        string
	AuthorizationID  string
	ExpectedRevision int64
	ProofRef         string
	IdempotencyKey   string
}

type VerifiedProof struct {
	CredentialRef       string
	ProofDigest         string
	GrantedCapabilities []string
	CredentialExpiresAt *time.Time
}

type VerifyCommand struct {
	Authorization    Authorization
	GrantReceipt     GrantReceipt
	GrantReceiptRef  string
	ExpectedRevision int64
	IdempotencyKey   string
	CommandDigest    string
	OccurredAt       time.Time
}

type MutationResult struct {
	Authorization   Authorization `json:"authorization" bson:"authorization"`
	ContinuationRef string        `json:"-" bson:"continuationRef,omitempty"`
	GrantReceiptRef string        `json:"-" bson:"grantReceiptRef,omitempty"`
	Replayed        bool          `json:"replayed" bson:"replayed"`
}

func NewStartCommand(
	input StartInput,
	authorizationID string,
	mode string,
	continuationRef string,
	continuationDigest string,
	now time.Time,
	expiresAt time.Time,
) (StartCommand, error) {
	input.AccountID = strings.TrimSpace(input.AccountID)
	input.ConnectorID = strings.TrimSpace(input.ConnectorID)
	input.IdempotencyKey = strings.TrimSpace(input.IdempotencyKey)
	authorizationID = strings.TrimSpace(authorizationID)
	mode = strings.TrimSpace(mode)
	continuationRef = strings.TrimSpace(continuationRef)
	continuationDigest = strings.TrimSpace(continuationDigest)
	capabilities := NormalizeCapabilities(input.RequestedCapabilities)
	now = now.UTC()
	expiresAt = expiresAt.UTC()
	if input.AccountID == "" || input.ConnectorID == "" || input.IdempotencyKey == "" ||
		authorizationID == "" || len(capabilities) == 0 || continuationRef == "" ||
		!ValidDigest(continuationDigest) || !validMode(mode) || now.IsZero() || !expiresAt.After(now) {
		return StartCommand{}, ErrInvalidArgument
	}
	authorization := Authorization{
		AuthorizationID:       authorizationID,
		AccountID:             input.AccountID,
		ConnectorID:           input.ConnectorID,
		AuthorizationMode:     mode,
		RequestedCapabilities: capabilities,
		GrantedCapabilities:   []string{},
		Status:                StatusPending,
		ContinuationDigest:    continuationDigest,
		ExpiresAt:             expiresAt,
		Revision:              1,
		CreatedAt:             now,
		UpdatedAt:             now,
	}
	digest := Hash(strings.Join([]string{
		input.AccountID,
		input.ConnectorID,
		mode,
		strings.Join(capabilities, ","),
	}, "\x00"))
	return StartCommand{
		Authorization:   authorization,
		ContinuationRef: continuationRef,
		IdempotencyKey:  input.IdempotencyKey,
		CommandDigest:   digest,
	}, nil
}

func NewVerifyCommand(
	current Authorization,
	input CompleteInput,
	mode string,
	proof VerifiedProof,
	grantReceiptRef string,
	grantReceiptDigest string,
	commandDigest string,
	now time.Time,
	grantExpiresAt time.Time,
) (VerifyCommand, error) {
	input.AccountID = strings.TrimSpace(input.AccountID)
	input.AuthorizationID = strings.TrimSpace(input.AuthorizationID)
	input.ProofRef = strings.TrimSpace(input.ProofRef)
	input.IdempotencyKey = strings.TrimSpace(input.IdempotencyKey)
	mode = strings.TrimSpace(mode)
	proof.CredentialRef = strings.TrimSpace(proof.CredentialRef)
	proof.ProofDigest = strings.TrimSpace(proof.ProofDigest)
	proof.GrantedCapabilities = NormalizeCapabilities(proof.GrantedCapabilities)
	grantReceiptRef = strings.TrimSpace(grantReceiptRef)
	grantReceiptDigest = strings.TrimSpace(grantReceiptDigest)
	commandDigest = strings.TrimSpace(commandDigest)
	now = now.UTC()
	grantExpiresAt = grantExpiresAt.UTC()
	if input.AccountID == "" || input.AuthorizationID == "" || input.IdempotencyKey == "" ||
		input.ProofRef == "" || input.ExpectedRevision <= 0 || current.AuthorizationID != input.AuthorizationID ||
		current.AccountID != input.AccountID || current.Status != StatusPending ||
		current.Revision != input.ExpectedRevision || current.AuthorizationMode != mode ||
		proof.CredentialRef == "" || !ValidDigest(proof.ProofDigest) ||
		grantReceiptRef == "" || !ValidDigest(grantReceiptDigest) ||
		!ValidDigest(commandDigest) ||
		now.IsZero() || !grantExpiresAt.After(now) {
		return VerifyCommand{}, ErrInvalidArgument
	}
	if !current.ExpiresAt.After(now) {
		return VerifyCommand{}, ErrExpired
	}
	if !sameCapabilities(current.RequestedCapabilities, proof.GrantedCapabilities) {
		return VerifyCommand{}, ErrCapabilityDenied
	}
	credentialExpiresAt := normalizeTimePointer(proof.CredentialExpiresAt)
	next := current
	next.GrantedCapabilities = append([]string(nil), proof.GrantedCapabilities...)
	next.Status = StatusVerified
	next.ProofDigest = proof.ProofDigest
	next.GrantReceiptDigest = grantReceiptDigest
	next.CredentialRef = proof.CredentialRef
	next.ExpiresAt = grantExpiresAt
	next.VerifiedAt = timePointer(now)
	next.Revision++
	next.UpdatedAt = now
	receipt := GrantReceipt{
		AuthorizationID:     next.AuthorizationID,
		AccountID:           next.AccountID,
		ConnectorID:         next.ConnectorID,
		AuthorizationMode:   next.AuthorizationMode,
		GrantedCapabilities: append([]string(nil), next.GrantedCapabilities...),
		CredentialRef:       next.CredentialRef,
		ProofDigest:         next.ProofDigest,
		GrantReceiptDigest:  grantReceiptDigest,
		ExpiresAt:           grantExpiresAt,
		CredentialExpiresAt: credentialExpiresAt,
		CreatedAt:           now,
	}
	return VerifyCommand{
		Authorization:    next,
		GrantReceipt:     receipt,
		GrantReceiptRef:  grantReceiptRef,
		ExpectedRevision: input.ExpectedRevision,
		IdempotencyKey:   input.IdempotencyKey,
		CommandDigest:    commandDigest,
		OccurredAt:       now,
	}, nil
}

func CompletionCommandDigest(input CompleteInput, mode string) (string, error) {
	accountID := strings.TrimSpace(input.AccountID)
	authorizationID := strings.TrimSpace(input.AuthorizationID)
	proofRef := strings.TrimSpace(input.ProofRef)
	mode = strings.TrimSpace(mode)
	if accountID == "" || authorizationID == "" || proofRef == "" ||
		input.ExpectedRevision <= 0 || !validMode(mode) {
		return "", ErrInvalidArgument
	}
	return Hash(strings.Join([]string{
		accountID,
		authorizationID,
		mode,
		Hash(proofRef),
		strings.TrimSpace(input.IdempotencyKey),
	}, "\x00")), nil
}

func (authorization Authorization) IsPending(now time.Time) bool {
	return authorization.Status == StatusPending && authorization.ExpiresAt.After(now.UTC())
}

func NormalizeCapabilities(values []string) []string {
	result := make([]string, 0, len(values))
	seen := make(map[string]struct{}, len(values))
	for _, raw := range values {
		value := strings.TrimSpace(raw)
		if value == "" {
			continue
		}
		if _, exists := seen[value]; exists {
			continue
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	sort.Strings(result)
	return result
}

func Hash(value string) string {
	sum := sha256.Sum256([]byte(value))
	return "sha256:" + hex.EncodeToString(sum[:])
}

func ValidDigest(value string) bool {
	if !strings.HasPrefix(value, "sha256:") || len(value) != len("sha256:")+sha256.Size*2 {
		return false
	}
	_, err := hex.DecodeString(strings.TrimPrefix(value, "sha256:"))
	return err == nil
}

func validMode(value string) bool {
	return value == ModeDeviceNative || value == ModeOAuth2
}

func sameCapabilities(left, right []string) bool {
	left = NormalizeCapabilities(left)
	right = NormalizeCapabilities(right)
	if len(left) != len(right) {
		return false
	}
	for index := range left {
		if left[index] != right[index] {
			return false
		}
	}
	return true
}

func normalizeTimePointer(value *time.Time) *time.Time {
	if value == nil || value.IsZero() {
		return nil
	}
	normalized := value.UTC()
	return &normalized
}

func timePointer(value time.Time) *time.Time {
	normalized := value.UTC()
	return &normalized
}
