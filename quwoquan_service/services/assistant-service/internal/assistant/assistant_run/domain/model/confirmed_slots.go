package model

import (
	"errors"
	"strings"
	"unicode"
)

const (
	maxAssistantRunConfirmedSlots     = 16
	maxAssistantRunConfirmedSlotRunes = 128
)

var ErrInvalidAssistantRunConfirmedSlots = errors.New(
	"invalid assistant run confirmed slots",
)

// AssistantRunConfirmedSlots is the current Run's immutable, descriptor-
// derived slot fact. It is deliberately separate from the AssistantSession
// continuity snapshot so terminal compaction can merge the current turn with
// the previous summary without treating old slots as newly confirmed.
type AssistantRunConfirmedSlots map[string]string

func NewAssistantRunConfirmedSlots(
	values map[string]string,
) (AssistantRunConfirmedSlots, error) {
	if len(values) == 0 {
		return nil, nil
	}
	if len(values) > maxAssistantRunConfirmedSlots {
		return nil, ErrInvalidAssistantRunConfirmedSlots
	}
	confirmed := make(AssistantRunConfirmedSlots, len(values))
	for rawKey, rawValue := range values {
		key := strings.TrimSpace(rawKey)
		value := strings.TrimSpace(rawValue)
		if !validAssistantRunSlotID(key) || value == "" ||
			len([]rune(value)) > maxAssistantRunConfirmedSlotRunes ||
			containsControlRune(value) {
			return nil, ErrInvalidAssistantRunConfirmedSlots
		}
		if _, duplicate := confirmed[key]; duplicate {
			return nil, ErrInvalidAssistantRunConfirmedSlots
		}
		confirmed[key] = value
	}
	return confirmed, nil
}

func (slots AssistantRunConfirmedSlots) Clone() AssistantRunConfirmedSlots {
	if len(slots) == 0 {
		return nil
	}
	cloned := make(AssistantRunConfirmedSlots, len(slots))
	for key, value := range slots {
		cloned[key] = value
	}
	return cloned
}

func (slots AssistantRunConfirmedSlots) Merge(
	next AssistantRunConfirmedSlots,
) (AssistantRunConfirmedSlots, error) {
	current, err := NewAssistantRunConfirmedSlots(slots)
	if err != nil {
		return nil, err
	}
	incoming, err := NewAssistantRunConfirmedSlots(next)
	if err != nil {
		return nil, err
	}
	merged := current.Clone()
	if merged == nil && len(incoming) > 0 {
		merged = make(AssistantRunConfirmedSlots, len(incoming))
	}
	for key, value := range incoming {
		merged[key] = value
	}
	return NewAssistantRunConfirmedSlots(merged)
}

func (slots AssistantRunConfirmedSlots) Equal(
	other AssistantRunConfirmedSlots,
) bool {
	if len(slots) != len(other) {
		return false
	}
	for key, value := range slots {
		if other[key] != value {
			return false
		}
	}
	return true
}

func validAssistantRunSlotID(value string) bool {
	if value == "" || len([]rune(value)) > 64 {
		return false
	}
	for _, current := range value {
		if unicode.IsLower(current) || unicode.IsDigit(current) || current == '_' {
			continue
		}
		return false
	}
	return true
}

func containsControlRune(value string) bool {
	for _, current := range value {
		if unicode.IsControl(current) {
			return true
		}
	}
	return false
}
