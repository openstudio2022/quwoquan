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
}

type MutationResult struct {
	Changed          bool
	IdempotentReplay bool
	State            RelationshipState
	ClearedFollowing []Direction
	EventName        string
	OccurredAt       time.Time
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
