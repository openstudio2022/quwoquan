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
	StatusActive  = "active"
	StatusRetired = "retired"

	AuthorizationDeviceNative = "device_native"
	AuthorizationOAuth2       = "oauth2"
	AuthorizationPublicLink   = "public_link"

	ConfirmationNone = "none"
	ConfirmationUser = "user_confirmation"
)

var (
	ErrInvalidArgument     = errors.New("connector definition is invalid")
	ErrNotFound            = errors.New("connector definition not found")
	ErrIdempotencyConflict = errors.New("connector definition idempotency conflict")
	ErrStorageUnavailable  = errors.New("connector definition storage unavailable")
)

type Definition struct {
	ConnectorID           string    `json:"connectorId" bson:"connectorId"`
	DisplayName           string    `json:"displayName" bson:"displayName"`
	Description           string    `json:"description" bson:"description"`
	Capabilities          []string  `json:"capabilities" bson:"capabilities"`
	AuthorizationMode     string    `json:"authorizationMode" bson:"authorizationMode"`
	ConfirmationPolicy    string    `json:"confirmationPolicy" bson:"confirmationPolicy"`
	DataClassification    string    `json:"dataClassification" bson:"dataClassification"`
	SupportedSurfaceKinds []string  `json:"supportedSurfaceKinds" bson:"supportedSurfaceKinds"`
	Status                string    `json:"status" bson:"status"`
	ReleaseDigest         string    `json:"releaseDigest" bson:"releaseDigest"`
	PublishedAt           time.Time `json:"publishedAt" bson:"publishedAt"`
}

type PublishInput struct {
	Definition     Definition
	IdempotencyKey string
	OccurredAt     time.Time
}

type PublishCommand struct {
	Definition     Definition
	IdempotencyKey string
	CommandDigest  string
}

type MutationResult struct {
	Definition Definition
	Replayed   bool
}

func NewPublishCommand(input PublishInput) (PublishCommand, error) {
	definition, err := Normalize(input.Definition, input.OccurredAt)
	if err != nil {
		return PublishCommand{}, err
	}
	key := strings.TrimSpace(input.IdempotencyKey)
	if key == "" {
		return PublishCommand{}, ErrInvalidArgument
	}
	digest := sha256.Sum256([]byte(strings.Join([]string{
		definition.ConnectorID,
		definition.ReleaseDigest,
		definition.Status,
		strings.Join(definition.Capabilities, ","),
		definition.AuthorizationMode,
		definition.ConfirmationPolicy,
	}, "\x00")))
	return PublishCommand{
		Definition:     definition,
		IdempotencyKey: key,
		CommandDigest:  "sha256:" + hex.EncodeToString(digest[:]),
	}, nil
}

func Normalize(input Definition, publishedAt time.Time) (Definition, error) {
	input.ConnectorID = strings.TrimSpace(input.ConnectorID)
	input.DisplayName = strings.TrimSpace(input.DisplayName)
	input.Description = strings.TrimSpace(input.Description)
	input.AuthorizationMode = strings.TrimSpace(input.AuthorizationMode)
	input.ConfirmationPolicy = strings.TrimSpace(input.ConfirmationPolicy)
	input.DataClassification = strings.TrimSpace(input.DataClassification)
	input.Status = strings.TrimSpace(input.Status)
	input.ReleaseDigest = strings.TrimSpace(input.ReleaseDigest)
	input.Capabilities = normalizeUnique(input.Capabilities)
	input.SupportedSurfaceKinds = normalizeUnique(input.SupportedSurfaceKinds)
	input.PublishedAt = publishedAt.UTC()
	if input.ConnectorID == "" || input.DisplayName == "" || input.Description == "" ||
		len(input.Capabilities) == 0 || len(input.SupportedSurfaceKinds) == 0 ||
		!validAuthorization(input.AuthorizationMode) ||
		!validConfirmation(input.ConfirmationPolicy) ||
		!oneOf(input.DataClassification, "public", "private", "sensitive") ||
		!oneOf(input.Status, StatusActive, StatusRetired) ||
		!validDigest(input.ReleaseDigest) || input.PublishedAt.IsZero() {
		return Definition{}, ErrInvalidArgument
	}
	for _, capability := range input.Capabilities {
		if !validCapability(capability) {
			return Definition{}, ErrInvalidArgument
		}
	}
	for _, surface := range input.SupportedSurfaceKinds {
		if !oneOf(surface, "personal", "conversation", "circle") {
			return Definition{}, ErrInvalidArgument
		}
	}
	return input, nil
}

func (definition Definition) Grants(capability string) bool {
	capability = strings.TrimSpace(capability)
	if definition.Status != StatusActive || capability == "" {
		return false
	}
	for _, allowed := range definition.Capabilities {
		if allowed == capability {
			return true
		}
	}
	return false
}

func (definition Definition) SupportsSurface(surfaceKind string) bool {
	surfaceKind = strings.TrimSpace(surfaceKind)
	if definition.Status != StatusActive || surfaceKind == "" {
		return false
	}
	for _, allowed := range definition.SupportedSurfaceKinds {
		if allowed == surfaceKind {
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

func validCapability(value string) bool {
	parts := strings.Split(value, ".")
	if len(parts) < 3 {
		return false
	}
	for _, part := range parts {
		if strings.TrimSpace(part) == "" {
			return false
		}
	}
	return true
}

func validDigest(value string) bool {
	if !strings.HasPrefix(value, "sha256:") || len(value) != len("sha256:")+sha256.Size*2 {
		return false
	}
	_, err := hex.DecodeString(strings.TrimPrefix(value, "sha256:"))
	return err == nil
}

func validAuthorization(value string) bool {
	return oneOf(value, AuthorizationDeviceNative, AuthorizationOAuth2, AuthorizationPublicLink)
}

func validConfirmation(value string) bool {
	return oneOf(value, ConfirmationNone, ConfirmationUser)
}

func oneOf(value string, allowed ...string) bool {
	for _, candidate := range allowed {
		if value == candidate {
			return true
		}
	}
	return false
}
