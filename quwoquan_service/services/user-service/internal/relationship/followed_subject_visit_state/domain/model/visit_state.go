// Package model 定义 FollowedSubjectVisitState：viewer × subject 的私有访问
// 水位。lastVisitedAt 只能单调推进；重复 clientRequestId 返回同一 receipt。
package model

import (
	"errors"
	"strings"
	"time"
)

var ErrInvalidCommand = errors.New("followed subject visit: invalid command")

// subjectTypes 与 canonical FollowSubjectKind 保持完全一致。任何可进入
// following_subjects 的关注对象都必须能推进访问水位，否则 location 会形成
// “关注成功但红点永不消失”的静默断链。persona 取代旧 user wire 值。
var subjectTypes = map[string]struct{}{
	"persona":  {},
	"circle":   {},
	"homepage": {},
	"location": {},
}

type MarkVisitedCommand struct {
	PersonaID       string
	SubjectType     string
	SubjectID       string
	VisitedAt       time.Time
	ClientRequestID string
}

func NewMarkVisitedCommand(
	personaID, subjectType, subjectID string,
	visitedAt time.Time,
	clientRequestID string,
) (MarkVisitedCommand, error) {
	command := MarkVisitedCommand{
		PersonaID:       strings.TrimSpace(personaID),
		SubjectType:     strings.TrimSpace(strings.ToLower(subjectType)),
		SubjectID:       strings.TrimSpace(subjectID),
		VisitedAt:       visitedAt.UTC(),
		ClientRequestID: strings.TrimSpace(clientRequestID),
	}
	if command.PersonaID == "" || command.SubjectID == "" || command.ClientRequestID == "" {
		return MarkVisitedCommand{}, ErrInvalidCommand
	}
	if _, ok := subjectTypes[command.SubjectType]; !ok {
		return MarkVisitedCommand{}, ErrInvalidCommand
	}
	if command.VisitedAt.IsZero() {
		command.VisitedAt = time.Now().UTC()
	}
	return command, nil
}

// VisitResult 是水位提交后的结果（FollowedSubjectVisitResult wire）。
type VisitResult struct {
	SubjectID        string    `json:"subjectId"`
	SubjectType      string    `json:"subjectType"`
	LastVisitedAt    time.Time `json:"lastVisitedAt"`
	HasUnreadChanges bool      `json:"hasUnreadChanges"`
	Replayed         bool      `json:"-"`
}

const EventFollowedSubjectVisited = "FollowedSubjectVisited"

// OutboxEvent 是与水位状态同事务追加的 FollowedSubjectVisited 事实。
// following-subject-projector 与 behavior-service 只从这里取事件，命令路径
// 不再在提交后尽力投递。
type OutboxEvent struct {
	EventID     string
	AggregateID string
	EventName   string
	Payload     EventPayload
	OccurredAt  time.Time
}

// EventPayload 的字段集与 contracts events.yaml 的 payload_fields 一一对应。
type EventPayload struct {
	PersonaID     string    `json:"personaId"`
	SubjectType   string    `json:"subjectType"`
	SubjectID     string    `json:"subjectId"`
	LastVisitedAt time.Time `json:"lastVisitedAt"`
	UpdatedAt     time.Time `json:"updatedAt"`
}

// VisitAggregateID 是 viewer × subject 水位的稳定标识，同时用于 outbox 的
// aggregateId 与消费侧幂等键前缀。
func VisitAggregateID(personaID, subjectType, subjectID string) string {
	return personaID + ":" + subjectType + ":" + subjectID
}

// VisitEventID 由命令的 clientRequestId 派生，保证同一命令重放不会追加第二
// 条事件，消费侧也能以 eventId 去重。
func VisitEventID(command MarkVisitedCommand) string {
	return VisitAggregateID(
		command.PersonaID,
		command.SubjectType,
		command.SubjectID,
	) + ":" + command.ClientRequestID
}
