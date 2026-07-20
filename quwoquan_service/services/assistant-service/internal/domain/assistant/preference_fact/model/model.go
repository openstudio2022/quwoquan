package model

import (
	"errors"
	"strings"
	"time"
)

type Scope string

const (
	ScopeSession  Scope = "session"
	ScopeLongTerm Scope = "long_term"
)

type Kind string

const (
	KindResponseStyle Kind = "response_style"
	KindReplyLength   Kind = "reply_length"
	KindTone          Kind = "tone"
	KindLanguage      Kind = "language"
)

type SourceType string

const (
	SourceExplicitRewrite SourceType = "explicit_rewrite"
	SourceManagement      SourceType = "management"
)

type Status string

const (
	StatusActive  Status = "active"
	StatusRevoked Status = "revoked"
)

var ErrInvalidPreference = errors.New("invalid assistant preference")

var allowedValues = map[Kind]map[string]struct{}{
	KindResponseStyle: {
		"deep_think": {},
	},
	KindReplyLength: {
		"concise":  {},
		"detailed": {},
	},
	KindTone: {
		"casual":       {},
		"neutral":      {},
		"professional": {},
		"warm":         {},
	},
	KindLanguage: {
		"zh_cn": {},
		"en":    {},
	},
}

type Fact struct {
	PreferenceID       string     `json:"preferenceId" bson:"_id"`
	UserID             string     `json:"userId" bson:"userId"`
	Scope              Scope      `json:"scope" bson:"scope"`
	ConversationID     string     `json:"conversationId,omitempty" bson:"conversationId,omitempty"`
	Kind               Kind       `json:"kind" bson:"kind"`
	Value              string     `json:"value" bson:"value"`
	SourceType         SourceType `json:"sourceType" bson:"sourceType"`
	Status             Status     `json:"status" bson:"status"`
	RevokedAt          *time.Time `json:"revokedAt,omitempty" bson:"revokedAt,omitempty"`
	RevocationDeadline *time.Time `json:"revocationDeadline,omitempty" bson:"revocationDeadline,omitempty"`
	CreatedAt          time.Time  `json:"createdAt" bson:"createdAt"`
	UpdatedAt          time.Time  `json:"updatedAt" bson:"updatedAt"`
	Version            int64      `json:"version" bson:"version"`
}

type Snapshot struct {
	PreferenceID string `json:"preferenceId" bson:"preferenceId"`
	Scope        Scope  `json:"scope" bson:"scope"`
	Kind         Kind   `json:"kind" bson:"kind"`
	Value        string `json:"value" bson:"value"`
	Version      int64  `json:"version" bson:"version"`
}

func (f Fact) Snapshot() Snapshot {
	return Snapshot{
		PreferenceID: f.PreferenceID,
		Scope:        f.Scope,
		Kind:         f.Kind,
		Value:        f.Value,
		Version:      f.Version,
	}
}

func Normalize(
	scope string,
	conversationID string,
	kind string,
	value string,
	sourceType string,
) (Scope, string, Kind, string, SourceType, error) {
	normalizedScope := Scope(strings.TrimSpace(scope))
	normalizedConversationID := strings.TrimSpace(conversationID)
	normalizedKind := Kind(strings.TrimSpace(kind))
	normalizedValue := strings.TrimSpace(value)
	normalizedSource := SourceType(strings.TrimSpace(sourceType))

	switch normalizedScope {
	case ScopeSession:
		if normalizedConversationID == "" {
			return "", "", "", "", "", ErrInvalidPreference
		}
	case ScopeLongTerm:
		if normalizedConversationID != "" {
			return "", "", "", "", "", ErrInvalidPreference
		}
	default:
		return "", "", "", "", "", ErrInvalidPreference
	}
	if _, ok := allowedValues[normalizedKind][normalizedValue]; !ok {
		return "", "", "", "", "", ErrInvalidPreference
	}
	switch normalizedSource {
	case SourceExplicitRewrite, SourceManagement:
	default:
		return "", "", "", "", "", ErrInvalidPreference
	}
	return normalizedScope, normalizedConversationID, normalizedKind, normalizedValue, normalizedSource, nil
}
