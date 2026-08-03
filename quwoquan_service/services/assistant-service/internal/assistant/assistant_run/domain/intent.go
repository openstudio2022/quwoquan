// Package domain owns AssistantRun identity and input invariants independently
// from HTTP decoding and durable persistence.
package domain

import (
	"errors"
	"strings"
)

var ErrInvalidIntent = errors.New("invalid assistant run intent")

type Intent struct {
	Kind               string                    `json:"kind"`
	Answer             *AnswerIntent             `json:"answer"`
	Search             *SearchIntent             `json:"search"`
	CreationAssistance *CreationAssistanceIntent `json:"creationAssistance"`
}

type AnswerIntent struct {
	Text string `json:"text"`
}

type SearchIntent struct {
	Query string `json:"query"`
}

type CreationAssistanceIntent struct {
	DraftTitle   string `json:"draftTitle"`
	DraftSummary string `json:"draftSummary"`
}

// PrimaryText validates the tagged union and derives the immutable execution
// input. Exactly one payload must match Kind; no compatibility fallback exists.
func (intent Intent) PrimaryText() (string, error) {
	switch strings.TrimSpace(intent.Kind) {
	case "answer":
		if intent.Answer == nil || intent.Search != nil ||
			intent.CreationAssistance != nil {
			return "", ErrInvalidIntent
		}
		text := strings.TrimSpace(intent.Answer.Text)
		if text == "" {
			return "", ErrInvalidIntent
		}
		return text, nil
	case "search":
		if intent.Search == nil || intent.Answer != nil ||
			intent.CreationAssistance != nil {
			return "", ErrInvalidIntent
		}
		query := strings.TrimSpace(intent.Search.Query)
		if query == "" {
			return "", ErrInvalidIntent
		}
		return query, nil
	case "creation_assistance":
		if intent.CreationAssistance == nil || intent.Answer != nil ||
			intent.Search != nil {
			return "", ErrInvalidIntent
		}
		text := strings.TrimSpace(
			intent.CreationAssistance.DraftTitle + "\n" +
				intent.CreationAssistance.DraftSummary,
		)
		if text == "" {
			return "", ErrInvalidIntent
		}
		return text, nil
	default:
		return "", ErrInvalidIntent
	}
}
