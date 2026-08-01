// Package model 定义 SkillConsent 聚合及其唯一命令语义。
package model

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
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
	ErrStorageUnavailable  = errors.New("skill consent storage unavailable")
	ErrConsentRequired     = errors.New("skill consent is required")
)

// Consent 是一次不可删除的授权事实。当前生效性只由 RevokedAt 是否为空决定。
type Consent struct {
	ID           string     `json:"id"`
	AccountID    string     `json:"accountId"`
	SkillID      string     `json:"skillId"`
	GrantedScope string     `json:"grantedScope"`
	GrantedAt    time.Time  `json:"grantedAt"`
	RevokedAt    *time.Time `json:"revokedAt,omitempty"`
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
	GrantedScope   string
	IdempotencyKey string
	RequestDigest  string
	OccurredAt     time.Time
}

func NewGrantCommand(
	accountID, skillID, grantedScope, idempotencyKey string,
	occurredAt time.Time,
) (Command, error) {
	accountID = strings.TrimSpace(accountID)
	skillID = strings.TrimSpace(skillID)
	grantedScope = strings.TrimSpace(grantedScope)
	idempotencyKey = strings.TrimSpace(idempotencyKey)
	return newCommand(
		CommandGrant, accountID, skillID, grantedScope, idempotencyKey, occurredAt,
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
		"",
		strings.TrimSpace(idempotencyKey),
		occurredAt,
	)
}

func newCommand(
	operation, accountID, skillID, grantedScope, idempotencyKey string,
	occurredAt time.Time,
) (Command, error) {
	if accountID == "" || skillID == "" || idempotencyKey == "" ||
		(operation == CommandGrant && grantedScope == "") ||
		len(idempotencyKey) > 160 || occurredAt.IsZero() {
		return Command{}, ErrInvalidArgument
	}
	canonical := strings.Join(
		[]string{operation, accountID, skillID, grantedScope}, "\x1f",
	)
	digest := sha256.Sum256([]byte(canonical))
	return Command{
		Operation:      operation,
		AccountID:      accountID,
		SkillID:        skillID,
		GrantedScope:   grantedScope,
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
	EventID      string    `json:"eventId"`
	EventName    string    `json:"eventName"`
	AggregateID  string    `json:"aggregateId"`
	AccountID    string    `json:"accountId"`
	SkillID      string    `json:"skillId"`
	GrantedScope string    `json:"grantedScope,omitempty"`
	OccurredAt   time.Time `json:"occurredAt"`
}
