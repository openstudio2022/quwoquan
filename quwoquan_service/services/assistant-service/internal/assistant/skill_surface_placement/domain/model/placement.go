// Package model 定义 SkillSurfacePlacement 聚合及其唯一 PUT 语义。
package model

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"sort"
	"strings"
	"time"
)

const (
	SurfaceConversation = "conversation"
	SurfaceCircle       = "circle"

	PolicyAllSharedEligible = "all_shared_eligible"

	StatusActive   = "active"
	StatusArchived = "archived"

	CommandPut   = "PutSkillSurfacePlacement"
	EventChanged = "SkillSurfacePlacementChanged"
)

var (
	ErrInvalidArgument      = errors.New("skill surface placement command is invalid")
	ErrNotFound             = errors.New("skill surface placement is not found")
	ErrForbidden            = errors.New("skill surface placement access is forbidden")
	ErrRevisionConflict     = errors.New("skill surface placement revision conflict")
	ErrIdempotencyConflict  = errors.New("skill surface placement idempotency conflict")
	ErrUnknownSkill         = errors.New("skill surface placement references an unknown shared Skill")
	ErrAuthorityUnavailable = errors.New("skill surface authority is unavailable")
	ErrPackageUnavailable   = errors.New("shared Skill package is unavailable")
	ErrStorageUnavailable   = errors.New("skill surface placement storage is unavailable")
)

type Placement struct {
	ID                 string    `json:"id"`
	SurfaceKind        string    `json:"surfaceKind"`
	SurfaceID          string    `json:"surfaceId"`
	Policy             string    `json:"policy"`
	DisabledSkillIDs   []string  `json:"disabledSkillIds"`
	Status             string    `json:"status"`
	Revision           int64     `json:"revision"`
	CreatedByAccountID string    `json:"-"`
	UpdatedByAccountID string    `json:"-"`
	CreatedAt          time.Time `json:"createdAt"`
	UpdatedAt          time.Time `json:"updatedAt"`
}

type PutInput struct {
	SurfaceKind      string
	SurfaceID        string
	ActorAccountID   string
	ActorPersonaID   string
	Policy           string
	DisabledSkillIDs []string
	Status           string
	ExpectedRevision int64
	IdempotencyKey   string
	OccurredAt       time.Time
}

type Command struct {
	PutInput
	RequestDigest string
}

type MutationResult struct {
	Placement Placement `json:"placement"`
	Changed   bool      `json:"changed"`
	Replayed  bool      `json:"replayed"`
}

func NewPutCommand(input PutInput) (Command, error) {
	input.SurfaceKind = strings.TrimSpace(input.SurfaceKind)
	input.SurfaceID = strings.TrimSpace(input.SurfaceID)
	input.ActorAccountID = strings.TrimSpace(input.ActorAccountID)
	input.ActorPersonaID = strings.TrimSpace(input.ActorPersonaID)
	input.Policy = strings.TrimSpace(input.Policy)
	input.Status = strings.TrimSpace(input.Status)
	input.IdempotencyKey = strings.TrimSpace(input.IdempotencyKey)
	if !validSurfaceKind(input.SurfaceKind) || input.SurfaceID == "" ||
		len(input.SurfaceID) > 128 || input.ActorAccountID == "" ||
		input.ActorPersonaID == "" ||
		input.Policy != PolicyAllSharedEligible || !validStatus(input.Status) ||
		input.ExpectedRevision < 0 || input.IdempotencyKey == "" ||
		len(input.IdempotencyKey) > 160 || input.OccurredAt.IsZero() {
		return Command{}, ErrInvalidArgument
	}
	disabled, err := normalizeSkillIDs(input.DisabledSkillIDs)
	if err != nil {
		return Command{}, err
	}
	input.DisabledSkillIDs = disabled
	input.OccurredAt = input.OccurredAt.UTC()
	payload, err := json.Marshal(struct {
		Operation        string   `json:"operation"`
		SurfaceKind      string   `json:"surfaceKind"`
		SurfaceID        string   `json:"surfaceId"`
		ActorAccountID   string   `json:"actorAccountId"`
		ActorPersonaID   string   `json:"actorPersonaId"`
		Policy           string   `json:"policy"`
		DisabledSkillIDs []string `json:"disabledSkillIds"`
		Status           string   `json:"status"`
		ExpectedRevision int64    `json:"expectedRevision"`
	}{
		CommandPut,
		input.SurfaceKind,
		input.SurfaceID,
		input.ActorAccountID,
		input.ActorPersonaID,
		input.Policy,
		input.DisabledSkillIDs,
		input.Status,
		input.ExpectedRevision,
	})
	if err != nil {
		return Command{}, ErrInvalidArgument
	}
	sum := sha256.Sum256(payload)
	return Command{PutInput: input, RequestDigest: hex.EncodeToString(sum[:])}, nil
}

func (placement Placement) Equivalent(command Command) bool {
	return placement.Policy == command.Policy &&
		placement.Status == command.Status &&
		strings.Join(placement.DisabledSkillIDs, "\x1f") ==
			strings.Join(command.DisabledSkillIDs, "\x1f")
}

func (placement Placement) Allows(skillID string) bool {
	if placement.Status != StatusActive || placement.Policy != PolicyAllSharedEligible {
		return false
	}
	skillID = strings.TrimSpace(skillID)
	index := sort.SearchStrings(placement.DisabledSkillIDs, skillID)
	return index >= len(placement.DisabledSkillIDs) || placement.DisabledSkillIDs[index] != skillID
}

func validSurfaceKind(value string) bool {
	return value == SurfaceConversation || value == SurfaceCircle
}

func validStatus(value string) bool {
	return value == StatusActive || value == StatusArchived
}

func normalizeSkillIDs(values []string) ([]string, error) {
	if values == nil || len(values) > 64 {
		return nil, ErrInvalidArgument
	}
	seen := make(map[string]struct{}, len(values))
	result := make([]string, 0, len(values))
	for _, raw := range values {
		value := strings.TrimSpace(raw)
		if value == "" || len(value) > 128 {
			return nil, ErrInvalidArgument
		}
		if _, duplicate := seen[value]; duplicate {
			return nil, ErrInvalidArgument
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	sort.Strings(result)
	return result, nil
}
