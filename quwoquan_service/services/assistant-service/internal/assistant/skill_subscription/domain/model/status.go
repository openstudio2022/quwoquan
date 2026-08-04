// Package domain owns SkillSubscription lifecycle invariants.
package model

import (
	"errors"
	"strings"
)

var (
	ErrInvalidArgument     = errors.New("invalid skill subscription argument")
	ErrInvalidStatus       = errors.New("invalid skill subscription status")
	ErrInvalidTransition   = errors.New("invalid skill subscription transition")
	ErrIdempotencyConflict = errors.New("skill subscription command identity already has different intent")
	ErrVersionConflict     = errors.New("skill subscription aggregate version changed")
	ErrNotFound            = errors.New("skill subscription not found")
)

func ParseStatus(raw string) (string, error) {
	status := strings.TrimSpace(raw)
	switch status {
	case SkillSubscriptionStatusActive,
		SkillSubscriptionStatusPaused,
		SkillSubscriptionStatusArchived:
		return status, nil
	default:
		return "", ErrInvalidStatus
	}
}

// ValidateTransition enforces archived as terminal. Setting the current state
// again is an idempotent no-op and does not create a new aggregate revision.
func ValidateTransition(current, target string) error {
	from, err := ParseStatus(current)
	if err != nil {
		return err
	}
	to, err := ParseStatus(target)
	if err != nil {
		return err
	}
	if from == to {
		return nil
	}
	switch from {
	case SkillSubscriptionStatusActive:
		if to == SkillSubscriptionStatusPaused || to == SkillSubscriptionStatusArchived {
			return nil
		}
	case SkillSubscriptionStatusPaused:
		if to == SkillSubscriptionStatusActive || to == SkillSubscriptionStatusArchived {
			return nil
		}
	}
	return ErrInvalidTransition
}
