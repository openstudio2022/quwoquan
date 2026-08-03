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
	StatusPending = "pending"
	StatusActive  = "active"
	StatusExpired = "expired"
	StatusRevoked = "revoked"
	StatusFailed  = "failed"
)

var (
	ErrInvalidArgument     = errors.New("connector connection request is invalid")
	ErrNotFound            = errors.New("connector connection not found")
	ErrDefinitionNotFound  = errors.New("connector definition not found")
	ErrCapabilityDenied    = errors.New("connector capability denied")
	ErrGrantReceiptInvalid = errors.New("connector grant receipt is invalid")
	ErrRevisionConflict    = errors.New("connector connection revision conflict")
	ErrIdempotencyConflict = errors.New("connector connection idempotency conflict")
	ErrStorageUnavailable  = errors.New("connector connection storage unavailable")
)

type Connection struct {
	ConnectionID        string     `json:"connectionId" bson:"connectionId"`
	AccountID           string     `json:"-" bson:"accountId"`
	ConnectorID         string     `json:"connectorId" bson:"connectorId"`
	GrantedCapabilities []string   `json:"grantedCapabilities" bson:"grantedCapabilities"`
	Status              string     `json:"status" bson:"status"`
	CredentialRef       string     `json:"-" bson:"credentialRef,omitempty"`
	GrantReceiptDigest  string     `json:"-" bson:"grantReceiptDigest"`
	FreshnessAt         time.Time  `json:"freshnessAt" bson:"freshnessAt"`
	ExpiresAt           *time.Time `json:"expiresAt,omitempty" bson:"expiresAt,omitempty"`
	RevokedAt           *time.Time `json:"revokedAt,omitempty" bson:"revokedAt,omitempty"`
	Revision            int64      `json:"revision" bson:"revision"`
	CreatedAt           time.Time  `json:"createdAt" bson:"createdAt"`
	UpdatedAt           time.Time  `json:"updatedAt" bson:"updatedAt"`
}

type VerifiedGrant struct {
	AuthorizationID     string
	CredentialRef       string
	ReceiptDigest       string
	GrantedCapabilities []string
	ExpiresAt           *time.Time
}

type CreateInput struct {
	AccountID             string
	ConnectorID           string
	RequestedCapabilities []string
	GrantReceiptRef       string
	IdempotencyKey        string
}

type CreateCommand struct {
	AccountID           string
	ConnectorID         string
	AuthorizationID     string
	GrantedCapabilities []string
	CredentialRef       string
	GrantReceiptDigest  string
	ExpiresAt           *time.Time
	IdempotencyKey      string
	CommandDigest       string
	OccurredAt          time.Time
}

type RevokeInput struct {
	AccountID        string
	ConnectionID     string
	ExpectedRevision int64
	IdempotencyKey   string
	OccurredAt       time.Time
}

type MutationResult struct {
	Connection Connection
	Replayed   bool
}

type ResolveCapabilityInput struct {
	AccountID      string
	CapabilityKey  string
	SurfaceKind    string
	ConnectionRefs []string
}

type CapabilityGrantDecision struct {
	Allowed       bool       `json:"allowed"`
	CapabilityKey string     `json:"capabilityKey"`
	SurfaceKind   string     `json:"surfaceKind"`
	ConnectionID  string     `json:"connectionId,omitempty"`
	ConnectorID   string     `json:"connectorId,omitempty"`
	FreshnessAt   *time.Time `json:"freshnessAt,omitempty"`
	ExpiresAt     *time.Time `json:"expiresAt,omitempty"`
	Reason        string     `json:"reason"`
}

const (
	CapabilityReasonAllowed           = "allowed"
	CapabilityReasonNoConnection      = "no_connection"
	CapabilityReasonConnectionInactive = "connection_inactive"
	CapabilityReasonCapabilityDenied  = "capability_denied"
	CapabilityReasonSurfaceDenied     = "surface_denied"
	CapabilityReasonDefinitionMissing = "definition_missing"
)

func NormalizeResolveCapabilityInput(input ResolveCapabilityInput) (ResolveCapabilityInput, error) {
	input.AccountID = strings.TrimSpace(input.AccountID)
	input.CapabilityKey = strings.TrimSpace(input.CapabilityKey)
	input.SurfaceKind = strings.TrimSpace(input.SurfaceKind)
	input.ConnectionRefs = normalizeUnique(input.ConnectionRefs)
	if input.AccountID == "" || input.CapabilityKey == "" ||
		!oneOf(input.SurfaceKind, "personal", "conversation", "circle") ||
		len(input.ConnectionRefs) == 0 || len(input.ConnectionRefs) > 32 {
		return ResolveCapabilityInput{}, ErrInvalidArgument
	}
	return input, nil
}

func NewCreateCommand(
	input CreateInput,
	grant VerifiedGrant,
	now time.Time,
) (CreateCommand, error) {
	input.AccountID = strings.TrimSpace(input.AccountID)
	input.ConnectorID = strings.TrimSpace(input.ConnectorID)
	input.IdempotencyKey = strings.TrimSpace(input.IdempotencyKey)
	input.GrantReceiptRef = strings.TrimSpace(input.GrantReceiptRef)
	grant.CredentialRef = strings.TrimSpace(grant.CredentialRef)
	grant.AuthorizationID = strings.TrimSpace(grant.AuthorizationID)
	grant.ReceiptDigest = strings.TrimSpace(grant.ReceiptDigest)
	grant.GrantedCapabilities = normalizeUnique(grant.GrantedCapabilities)
	requested := normalizeUnique(input.RequestedCapabilities)
	if input.AccountID == "" || input.ConnectorID == "" ||
		input.IdempotencyKey == "" || len(requested) == 0 ||
		grant.AuthorizationID == "" || grant.ReceiptDigest == "" || len(grant.GrantedCapabilities) == 0 ||
		!sameValues(requested, grant.GrantedCapabilities) {
		return CreateCommand{}, ErrInvalidArgument
	}
	commandDigest, err := CreateCommandDigest(input)
	if err != nil {
		return CreateCommand{}, err
	}
	return CreateCommand{
		AccountID:           input.AccountID,
		ConnectorID:         input.ConnectorID,
		AuthorizationID:     grant.AuthorizationID,
		GrantedCapabilities: requested,
		CredentialRef:       grant.CredentialRef,
		GrantReceiptDigest:  grant.ReceiptDigest,
		ExpiresAt:           normalizeTimePointer(grant.ExpiresAt),
		IdempotencyKey:      input.IdempotencyKey,
		CommandDigest:       commandDigest,
		OccurredAt:          now.UTC(),
	}, nil
}

func CreateCommandDigest(input CreateInput) (string, error) {
	accountID := strings.TrimSpace(input.AccountID)
	connectorID := strings.TrimSpace(input.ConnectorID)
	grantReceiptRef := strings.TrimSpace(input.GrantReceiptRef)
	idempotencyKey := strings.TrimSpace(input.IdempotencyKey)
	capabilities := normalizeUnique(input.RequestedCapabilities)
	if accountID == "" || connectorID == "" || grantReceiptRef == "" ||
		idempotencyKey == "" || len(capabilities) == 0 {
		return "", ErrInvalidArgument
	}
	digest := sha256.Sum256([]byte(strings.Join([]string{
		accountID,
		connectorID,
		strings.Join(capabilities, ","),
		hashValue(grantReceiptRef),
		idempotencyKey,
	}, "\x00")))
	return "sha256:" + hex.EncodeToString(digest[:]), nil
}

func hashValue(value string) string {
	digest := sha256.Sum256([]byte(value))
	return hex.EncodeToString(digest[:])
}

func NewRevokeInput(input RevokeInput) (RevokeInput, error) {
	input.AccountID = strings.TrimSpace(input.AccountID)
	input.ConnectionID = strings.TrimSpace(input.ConnectionID)
	input.IdempotencyKey = strings.TrimSpace(input.IdempotencyKey)
	input.OccurredAt = input.OccurredAt.UTC()
	if input.AccountID == "" || input.ConnectionID == "" ||
		input.IdempotencyKey == "" || input.ExpectedRevision <= 0 ||
		input.OccurredAt.IsZero() {
		return RevokeInput{}, ErrInvalidArgument
	}
	return input, nil
}

func (connection Connection) IsActive(now time.Time) bool {
	if connection.Status != StatusActive || connection.RevokedAt != nil {
		return false
	}
	return connection.ExpiresAt == nil || connection.ExpiresAt.After(now.UTC())
}

func (connection Connection) Grants(capability string) bool {
	capability = strings.TrimSpace(capability)
	for _, granted := range connection.GrantedCapabilities {
		if granted == capability {
			return true
		}
	}
	return false
}

func normalizeUnique(values []string) []string {
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

func sameValues(left []string, right []string) bool {
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

func oneOf(value string, allowed ...string) bool {
	for _, candidate := range allowed {
		if value == candidate {
			return true
		}
	}
	return false
}

func normalizeTimePointer(value *time.Time) *time.Time {
	if value == nil || value.IsZero() {
		return nil
	}
	normalized := value.UTC()
	return &normalized
}
