package model

import (
	"crypto/sha256"
	"errors"
	"strings"
	"time"
)

var (
	ErrInvalidPersonaPair = errors.New("persona relationship requires two distinct persona ids")
	ErrFollowBlocked      = errors.New("persona relationship is blocked")
	// ErrIdempotencyKeyRequired 表示命令缺少 canonical 幂等键。空键会让命令
	// 无回执可恢复，因此在写入前拒绝，而不是静默跳过 receipt。
	ErrIdempotencyKeyRequired = errors.New("persona relationship command requires an idempotency key")
	// ErrIdempotencyConflict 表示同一键被复用于不同命令。
	ErrIdempotencyConflict = errors.New("persona relationship idempotency key belongs to a different command")
	// ErrVersionConflict 表示 expectedVersion 与当前聚合版本不符。
	ErrVersionConflict = errors.New("persona relationship version conflict")
	// ErrPairIdentityConflict 表示 pair 摘要命中的行与其 canonical 二元组不一致。
	ErrPairIdentityConflict = errors.New("persona relationship pair digest does not match its identity tuple")
	// ErrCommandAlreadyFinalized 表示该命令已被终结为未执行，不能再被接纳。
	ErrCommandAlreadyFinalized = errors.New("persona relationship command was already finalized")
	// ErrFollowingLimitExceeded 表示 source 已用满系统限额的主动关注名额。
	// 它是确定拒绝，不是可静默重试的瞬时故障。
	ErrFollowingLimitExceeded = errors.New("persona following limit exceeded")
	// ErrFollowPolicyUnavailable 表示读不到生效限额政策。
	// 此时拒绝新接纳，而不是按内存默认值放行。
	ErrFollowPolicyUnavailable = errors.New("persona following policy activation unavailable")
)

// CommandOutcome 是一条命令的终态闭集。
// committed 才有业务结果；rejected 是确定拒绝；expired 表示仲裁已终结且未执行。
// 当前关系态不属于该闭集：它不能替代历史结果。
type CommandOutcome string

const (
	OutcomeCommitted CommandOutcome = "committed"
	OutcomeRejected  CommandOutcome = "rejected"
	OutcomeExpired   CommandOutcome = "expired"
)

// Pair is the stable aggregate identity for two personas. Its ordering is part
// of the domain contract so all stores and consumers address the same row.
type Pair struct {
	ID             string
	LowerPersonaID string
	UpperPersonaID string
}

func NewPair(sourcePersonaID, targetPersonaID string) (Pair, error) {
	sourcePersonaID = strings.TrimSpace(sourcePersonaID)
	targetPersonaID = strings.TrimSpace(targetPersonaID)
	if sourcePersonaID == "" || targetPersonaID == "" || sourcePersonaID == targetPersonaID {
		return Pair{}, ErrInvalidPersonaPair
	}
	lower, upper := sourcePersonaID, targetPersonaID
	if upper < lower {
		lower, upper = upper, lower
	}
	digest := sha256.Sum256([]byte(lower + "\x00" + upper))
	return Pair{
		ID:             stringHex(digest[:]),
		LowerPersonaID: lower,
		UpperPersonaID: upper,
	}, nil
}

// VerifyStoredIdentity 核验按 pair_id 命中的行确实属于本 Pair 的二元组。
// 摘要相同但身份不同意味着 digest 碰撞或调用方拼错身份：此时必须拒绝，
// 不能改写另一对真实身份的方向、计数或成功事件。
func (p Pair) VerifyStoredIdentity(storedLower, storedUpper string) error {
	if strings.TrimSpace(storedLower) != p.LowerPersonaID ||
		strings.TrimSpace(storedUpper) != p.UpperPersonaID {
		return ErrPairIdentityConflict
	}
	return nil
}

// Contains 回答某个身份是否是本 Pair 的端点。
func (p Pair) Contains(personaID string) bool {
	personaID = strings.TrimSpace(personaID)
	return personaID == p.LowerPersonaID || personaID == p.UpperPersonaID
}

func stringHex(value []byte) string {
	const alphabet = "0123456789abcdef"
	encoded := make([]byte, len(value)*2)
	for i, b := range value {
		encoded[i*2] = alphabet[b>>4]
		encoded[i*2+1] = alphabet[b&0x0f]
	}
	return string(encoded)
}

type Direction struct {
	PairID          string     `json:"-"`
	SourcePersonaID string     `json:"sourcePersonaId"`
	TargetPersonaID string     `json:"targetPersonaId"`
	Following       bool       `json:"following"`
	Blocked         bool       `json:"blocked"`
	FollowSource    string     `json:"followSource,omitempty"`
	FollowedAt      *time.Time `json:"followedAt,omitempty"`
	BlockedAt       *time.Time `json:"blockedAt,omitempty"`
	UpdatedAt       time.Time  `json:"updatedAt"`
}

type RelationshipState struct {
	PairID       string    `json:"-"`
	Version      int64     `json:"-"`
	IsFollowing  bool      `json:"-"`
	IsFollowedBy bool      `json:"-"`
	IsMutual     bool      `json:"-"`
	IsBlocked    bool      `json:"-"`
	IsBlockedBy  bool      `json:"-"`
	UpdatedAt    time.Time `json:"-"`
}

func (s RelationshipState) RelationState(viewerPersonaID, targetPersonaID string) string {
	if strings.TrimSpace(viewerPersonaID) == strings.TrimSpace(targetPersonaID) {
		return "self"
	}
	switch {
	case s.IsMutual:
		return "mutual"
	case s.IsFollowing:
		return "following"
	case s.IsFollowedBy:
		return "followed_by"
	default:
		return "not_following"
	}
}

type CommandKind string

const (
	CommandFollow   CommandKind = "follow"
	CommandUnfollow CommandKind = "unfollow"
	CommandBlock    CommandKind = "block"
	CommandUnblock  CommandKind = "unblock"
)

type Command struct {
	Kind            CommandKind
	SourcePersonaID string
	TargetPersonaID string
	FollowSource    string
	IdempotencyKey  string
	// ExpectedVersion 是调用方读到的聚合版本。非 nil 时按它做 CAS：旧版本的
	// 离线请求不能越过较新的决定，包括较新的「保持不变」。
	ExpectedVersion *int64
	// MutationBasis 是服务端签发的写依据 token。它证明来源与接受期限，
	// 不代替当前权限与配额校验。
	MutationBasis string
	// AcceptUntil 来自已验签的 basis；超过它只拒绝新接纳，不影响已有回执读取。
	AcceptUntil time.Time
}

type MutationResult struct {
	CanonicalTargetPersonaID string
	Changed                  bool
	IdempotentReplay         bool
	State                    RelationshipState
	ClearedFollowing         []Direction
	EventName                string
	OccurredAt               time.Time
	// Outcome 是本命令的历史结果。空值表示调用方未走 receipt 仲裁路径。
	Outcome CommandOutcome
}

// OutboxPayload is the versioned cross-service fact emitted by the canonical
// relationship aggregate. It contains only the consumer data needed to build
// read models; persistence-only receipts and pair internals stay private.
type OutboxPayload struct {
	PairID                  string    `json:"pairId"`
	SourcePersonaID         string    `json:"sourcePersonaId"`
	TargetPersonaID         string    `json:"targetPersonaId"`
	Following               bool      `json:"following"`
	SourceFollowCleared     bool      `json:"sourceFollowCleared,omitempty"`
	TargetFollowCleared     bool      `json:"targetFollowCleared,omitempty"`
	ClearedFollowDirections int       `json:"clearedFollowDirections,omitempty"`
	Version                 int64     `json:"version"`
	OccurredAt              time.Time `json:"occurredAt"`
}

type OutboxEvent struct {
	EventID   string        `json:"eventId"`
	EventName string        `json:"eventName"`
	Payload   OutboxPayload `json:"payload"`
}
