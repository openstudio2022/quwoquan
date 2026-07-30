// Package model 定义 SubjectFollow 聚合：persona 对非 persona 主体
// （homepage/circle/location）的版本化关注关系。persona 间关系只能写
// PersonaRelationship，本聚合在构造命令时即拒绝 persona 主体。
package model

import (
	"errors"
	"fmt"
	"strings"
	"time"
)

const (
	StateFollowing  = "following"
	StateUnfollowed = "unfollowed"
)

const (
	CommandFollow   = "FollowSubject"
	CommandUnfollow = "UnfollowSubject"
)

// allowedSubjectTypes 是 metadata FollowSubjectKind 在 SubjectFollow
// 能力内的允许子集；persona 关系只归 PersonaRelationship。
var allowedSubjectTypes = map[string]struct{}{
	"homepage": {},
	"circle":   {},
	"location": {},
}

var (
	ErrInvalidSubjectType = errors.New("subject follow: invalid subject type")
	ErrInvalidCommand     = errors.New("subject follow: invalid command")
)

// Command 是 follow/unfollow 的规范化命令输入。
type Command struct {
	Kind           string
	PersonaID      string
	SubjectType    string
	SubjectID      string
	Source         string
	IdempotencyKey string
}

func NewCommand(kind, personaID, subjectType, subjectID, source, idempotencyKey string) (Command, error) {
	command := Command{
		Kind:           strings.TrimSpace(kind),
		PersonaID:      strings.TrimSpace(personaID),
		SubjectType:    strings.TrimSpace(strings.ToLower(subjectType)),
		SubjectID:      strings.TrimSpace(subjectID),
		Source:         strings.TrimSpace(source),
		IdempotencyKey: strings.TrimSpace(idempotencyKey),
	}
	if command.Kind != CommandFollow && command.Kind != CommandUnfollow {
		return Command{}, ErrInvalidCommand
	}
	if command.PersonaID == "" || command.SubjectID == "" {
		return Command{}, fmt.Errorf("%w: personaId and subjectId are required", ErrInvalidCommand)
	}
	if _, ok := allowedSubjectTypes[command.SubjectType]; !ok {
		return Command{}, ErrInvalidSubjectType
	}
	return command, nil
}

// SubjectFollow 是聚合状态快照。
type SubjectFollow struct {
	ID          string
	PersonaID   string
	SubjectType string
	SubjectID   string
	State       string
	Version     int64
	FollowedAt  *time.Time
	UpdatedAt   time.Time
}

// MutationResult 是命令提交后的版本化结果。
type MutationResult struct {
	Follow           SubjectFollow
	Changed          bool
	IdempotentReplay bool
	OccurredAt       time.Time
}

// OutboxEvent 是与聚合同事务追加的 SubjectFollowStateChanged 事实。
type OutboxEvent struct {
	EventID     string
	AggregateID string
	Version     int64
	EventName   string
	Payload     EventPayload
	OccurredAt  time.Time
}

const EventSubjectFollowStateChanged = "SubjectFollowStateChanged"

type EventPayload struct {
	ID          string    `json:"id"`
	PersonaID   string    `json:"personaId"`
	SubjectType string    `json:"subjectType"`
	SubjectID   string    `json:"subjectId"`
	State       string    `json:"state"`
	Version     int64     `json:"version"`
	OccurredAt  time.Time `json:"occurredAt"`
}

// Apply 在当前快照上应用命令（set/unset 语义）。exists 为 false 表示聚合尚不
// 存在；unfollow 一个不存在或已 unfollowed 的关注是幂等 no-op。
func Apply(current SubjectFollow, exists bool, command Command, now time.Time) (SubjectFollow, bool) {
	now = now.UTC()
	if !exists {
		if command.Kind == CommandUnfollow {
			return SubjectFollow{
				PersonaID:   command.PersonaID,
				SubjectType: command.SubjectType,
				SubjectID:   command.SubjectID,
				State:       StateUnfollowed,
				Version:     0,
				UpdatedAt:   now,
			}, false
		}
		followedAt := now
		return SubjectFollow{
			PersonaID:   command.PersonaID,
			SubjectType: command.SubjectType,
			SubjectID:   command.SubjectID,
			State:       StateFollowing,
			Version:     1,
			FollowedAt:  &followedAt,
			UpdatedAt:   now,
		}, true
	}
	target := StateFollowing
	if command.Kind == CommandUnfollow {
		target = StateUnfollowed
	}
	if current.State == target {
		return current, false
	}
	next := current
	next.State = target
	next.Version = current.Version + 1
	next.UpdatedAt = now
	if target == StateFollowing {
		followedAt := now
		next.FollowedAt = &followedAt
	}
	return next, true
}
