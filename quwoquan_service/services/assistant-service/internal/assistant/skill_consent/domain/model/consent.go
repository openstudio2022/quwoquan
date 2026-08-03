// Package model 定义 SkillConsent 聚合及其唯一命令语义。
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
	CommandGrant  = "GrantSkillConsent"
	CommandRevoke = "RevokeSkillConsent"

	EventGranted = "SkillConsentGranted"
	EventRevoked = "SkillConsentRevoked"
)

var (
	ErrInvalidArgument     = errors.New("skill consent command is invalid")
	ErrIdempotencyConflict = errors.New("skill consent idempotency conflict")
	ErrScopeConflict       = errors.New("skill consent scope set conflicts with active consent")
	ErrStorageUnavailable  = errors.New("skill consent storage unavailable")
	ErrConsentRequired     = errors.New("skill consent is required")
)

// Consent 是一次不可删除的授权事实。当前生效性只由 RevokedAt 是否为空决定。
type Consent struct {
	ID            string     `json:"id"`
	AccountID     string     `json:"accountId"`
	SkillID       string     `json:"skillId"`
	GrantedScopes []string   `json:"grantedScopes"`
	GrantedAt     time.Time  `json:"grantedAt"`
	RevokedAt     *time.Time `json:"revokedAt,omitempty"`
}

func (consent Consent) IsGranted() bool {
	return strings.TrimSpace(consent.ID) != "" && consent.RevokedAt == nil
}

// Command 是进入 Store 前已经规范化的命令。RequestDigest 是 payload 的稳定摘要，
// 与 IdempotencyKey 一起防止同一请求身份被复用于不同命令。
type Command struct {
	Operation      string
	AccountID      string
	SkillID        string
	GrantedScopes  []string
	IdempotencyKey string
	RequestDigest  string
	OccurredAt     time.Time
}

func NewGrantCommand(
	accountID, skillID string,
	grantedScopes []string,
	idempotencyKey string,
	occurredAt time.Time,
) (Command, error) {
	accountID = strings.TrimSpace(accountID)
	skillID = strings.TrimSpace(skillID)
	idempotencyKey = strings.TrimSpace(idempotencyKey)
	normalizedScopes, err := normalizeScopes(grantedScopes)
	if err != nil {
		return Command{}, err
	}
	return newCommand(
		CommandGrant, accountID, skillID, normalizedScopes, idempotencyKey, occurredAt,
	)
}

func NewRevokeCommand(
	accountID, skillID, idempotencyKey string,
	occurredAt time.Time,
) (Command, error) {
	return newCommand(
		CommandRevoke,
		strings.TrimSpace(accountID),
		strings.TrimSpace(skillID),
		nil,
		strings.TrimSpace(idempotencyKey),
		occurredAt,
	)
}

func newCommand(
	operation, accountID, skillID string,
	grantedScopes []string,
	idempotencyKey string,
	occurredAt time.Time,
) (Command, error) {
	if accountID == "" || skillID == "" || idempotencyKey == "" ||
		(operation == CommandGrant && len(grantedScopes) == 0) ||
		len(idempotencyKey) > 160 || occurredAt.IsZero() {
		return Command{}, ErrInvalidArgument
	}
	canonical := strings.Join(
		[]string{operation, accountID, skillID, strings.Join(grantedScopes, "\x1e")}, "\x1f",
	)
	digest := sha256.Sum256([]byte(canonical))
	return Command{
		Operation:      operation,
		AccountID:      accountID,
		SkillID:        skillID,
		GrantedScopes:  append([]string(nil), grantedScopes...),
		IdempotencyKey: idempotencyKey,
		RequestDigest:  hex.EncodeToString(digest[:]),
		OccurredAt:     occurredAt.UTC(),
	}, nil
}

type MutationResult struct {
	Consent  *Consent `json:"consent,omitempty"`
	Changed  bool     `json:"changed"`
	Replayed bool     `json:"replayed"`
}

type Event struct {
	EventID       string    `json:"eventId"`
	EventName     string    `json:"eventName"`
	AggregateID   string    `json:"aggregateId"`
	AccountID     string    `json:"accountId"`
	SkillID       string    `json:"skillId"`
	GrantedScopes []string  `json:"grantedScopes,omitempty"`
	OccurredAt    time.Time `json:"occurredAt"`
}

func EqualScopes(left, right []string) bool {
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

func normalizeScopes(values []string) ([]string, error) {
	if len(values) == 0 || len(values) > 32 {
		return nil, ErrInvalidArgument
	}
	seen := make(map[string]struct{}, len(values))
	result := make([]string, 0, len(values))
	for _, raw := range values {
		value := strings.TrimSpace(raw)
		if value == "" || len(value) > 160 {
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
