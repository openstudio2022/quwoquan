// Package model 定义 FollowedSubjectVisitState：viewer × subject 的私有访问
// 水位。lastVisitedAt 只能单调推进；重复 clientRequestId 返回同一 receipt。
package model

import (
	"errors"
	"strings"
	"time"
)

var ErrInvalidCommand = errors.New("followed subject visit: invalid command")

// subjectTypes 与 metadata FollowingSubjectType 枚举同源（user/circle/homepage）。
var subjectTypes = map[string]struct{}{
	"user":     {},
	"circle":   {},
	"homepage": {},
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
