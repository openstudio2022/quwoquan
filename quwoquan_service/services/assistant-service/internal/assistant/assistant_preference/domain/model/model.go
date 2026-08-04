package model

import (
	"errors"
	"strings"
	"time"
	"unicode"
)

type Scope string

const (
	ScopeSession  Scope = "session"
	ScopeLongTerm Scope = "long_term"
)

type Kind string

const (
	KindResponseStyle       Kind = "response_style"
	KindReplyLength         Kind = "reply_length"
	KindTone                Kind = "tone"
	KindLanguage            Kind = "language"
	KindFrequentLocations   Kind = "frequent_locations"
	KindFamilyTerms         Kind = "family_terms"
	KindDietaryRestrictions Kind = "dietary_restrictions"
	KindTravelPreferences   Kind = "travel_preferences"
)

type SourceType string

const (
	SourceExplicitRewrite  SourceType = "explicit_rewrite"
	SourceManagement       SourceType = "management"
	SourceSessionConfirmed SourceType = "session_confirmed"
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

type AssistantPreference struct {
	PreferenceID       string     `json:"preferenceId" bson:"_id"`
	UserID             string     `json:"userId" bson:"userId"`
	Scope              Scope      `json:"scope" bson:"scope"`
	SessionID          string     `json:"sessionId,omitempty" bson:"sessionId,omitempty"`
	Kind               Kind       `json:"kind" bson:"kind"`
	Value              string     `json:"value" bson:"value"`
	SourceType         SourceType `json:"sourceType" bson:"sourceType"`
	SourceSessionID    string     `json:"sourceSessionId,omitempty" bson:"sourceSessionId,omitempty"`
	ConfirmedAt        *time.Time `json:"confirmedAt,omitempty" bson:"confirmedAt,omitempty"`
	Status             Status     `json:"status" bson:"status"`
	RevokedAt          *time.Time `json:"revokedAt,omitempty" bson:"revokedAt,omitempty"`
	RevocationDeadline *time.Time `json:"revocationDeadline,omitempty" bson:"revocationDeadline,omitempty"`
	CreatedAt          time.Time  `json:"createdAt" bson:"createdAt"`
	UpdatedAt          time.Time  `json:"updatedAt" bson:"updatedAt"`
	Version            int64      `json:"version" bson:"version"`
}

type AssistantPreferenceSnapshot struct {
	PreferenceID    string     `json:"preferenceId" bson:"preferenceId"`
	Scope           Scope      `json:"scope" bson:"scope"`
	Kind            Kind       `json:"kind" bson:"kind"`
	Value           string     `json:"value" bson:"value"`
	SourceType      SourceType `json:"sourceType" bson:"sourceType"`
	SourceSessionID string     `json:"sourceSessionId,omitempty" bson:"sourceSessionId,omitempty"`
	ConfirmedAt     *time.Time `json:"confirmedAt,omitempty" bson:"confirmedAt,omitempty"`
	Version         int64      `json:"version" bson:"version"`
}

func (preference AssistantPreference) Snapshot() AssistantPreferenceSnapshot {
	return AssistantPreferenceSnapshot{
		PreferenceID:    preference.PreferenceID,
		Scope:           preference.Scope,
		Kind:            preference.Kind,
		Value:           preference.Value,
		SourceType:      preference.SourceType,
		SourceSessionID: preference.SourceSessionID,
		ConfirmedAt:     preference.ConfirmedAt,
		Version:         preference.Version,
	}
}

func Normalize(
	scope string,
	sessionID string,
	kind string,
	value string,
	sourceType string,
	sourceSessionID string,
	confirmed bool,
) (Scope, string, Kind, string, SourceType, string, error) {
	normalizedScope := Scope(strings.TrimSpace(scope))
	normalizedSessionID := strings.TrimSpace(sessionID)
	normalizedKind := Kind(strings.TrimSpace(kind))
	normalizedValue := strings.TrimSpace(value)
	normalizedSource := SourceType(strings.TrimSpace(sourceType))
	normalizedSourceSessionID := strings.TrimSpace(sourceSessionID)

	switch normalizedScope {
	case ScopeSession:
		if normalizedSessionID == "" {
			return "", "", "", "", "", "", ErrInvalidPreference
		}
	case ScopeLongTerm:
		if normalizedSessionID != "" {
			return "", "", "", "", "", "", ErrInvalidPreference
		}
	default:
		return "", "", "", "", "", "", ErrInvalidPreference
	}
	if RequiresExplicitConfirmation(normalizedKind) {
		if normalizedScope != ScopeLongTerm || !confirmed ||
			!validConfirmedValue(normalizedValue) {
			return "", "", "", "", "", "", ErrInvalidPreference
		}
		normalizedValue = strings.Join(strings.Fields(normalizedValue), " ")
	} else if _, ok := allowedValues[normalizedKind][normalizedValue]; !ok {
		return "", "", "", "", "", "", ErrInvalidPreference
	}
	switch normalizedSource {
	case SourceExplicitRewrite, SourceManagement, SourceSessionConfirmed:
	default:
		return "", "", "", "", "", "", ErrInvalidPreference
	}
	if RequiresExplicitConfirmation(normalizedKind) {
		switch normalizedSource {
		case SourceSessionConfirmed:
			if normalizedSourceSessionID == "" {
				return "", "", "", "", "", "", ErrInvalidPreference
			}
		case SourceManagement:
			normalizedSourceSessionID = ""
		default:
			return "", "", "", "", "", "", ErrInvalidPreference
		}
	} else {
		normalizedSourceSessionID = ""
	}
	return normalizedScope, normalizedSessionID, normalizedKind, normalizedValue,
		normalizedSource, normalizedSourceSessionID, nil
}

func RequiresExplicitConfirmation(kind Kind) bool {
	switch kind {
	case KindFrequentLocations,
		KindFamilyTerms,
		KindDietaryRestrictions,
		KindTravelPreferences:
		return true
	default:
		return false
	}
}

func validConfirmedValue(value string) bool {
	if value == "" || len([]rune(value)) > 512 {
		return false
	}
	for _, current := range value {
		if unicode.IsControl(current) && !unicode.IsSpace(current) {
			return false
		}
	}
	return true
}
