package model

import (
	"errors"
	"strings"
	"time"
)

var ErrInvalidMediaOriginalAccessFact = errors.New("invalid media original access fact")

// MediaOriginalAccessFact is the immutable audit record for a granted
// original-media URL. It is not aggregate state and can only be appended.
type MediaOriginalAccessFact struct {
	AuditID        string
	AssetID        string
	ViewerID       string
	Purpose        string
	Outcome        string
	Reason         string
	IdempotencyKey string
	GrantedAt      time.Time
	ExpiresAt      time.Time
}

func (fact MediaOriginalAccessFact) Validate() error {
	if strings.TrimSpace(fact.AuditID) == "" ||
		strings.TrimSpace(fact.AssetID) == "" ||
		strings.TrimSpace(fact.ViewerID) == "" ||
		strings.TrimSpace(fact.Outcome) == "" ||
		strings.TrimSpace(fact.Reason) == "" ||
		strings.TrimSpace(fact.IdempotencyKey) == "" ||
		fact.GrantedAt.IsZero() {
		return ErrInvalidMediaOriginalAccessFact
	}
	purpose := strings.ToLower(strings.TrimSpace(fact.Purpose))
	if purpose != "view" && purpose != "save" {
		return ErrInvalidMediaOriginalAccessFact
	}
	switch strings.ToLower(strings.TrimSpace(fact.Outcome)) {
	case "granted":
		if strings.TrimSpace(fact.Reason) != "authorized" ||
			!fact.ExpiresAt.After(fact.GrantedAt) {
			return ErrInvalidMediaOriginalAccessFact
		}
	case "denied":
		if !fact.ExpiresAt.IsZero() ||
			!isOriginalAccessDenialReason(fact.Reason) {
			return ErrInvalidMediaOriginalAccessFact
		}
	case "rate_limited":
		if !fact.ExpiresAt.IsZero() ||
			strings.TrimSpace(fact.Reason) != "rate_limit_exhausted" {
			return ErrInvalidMediaOriginalAccessFact
		}
	default:
		return ErrInvalidMediaOriginalAccessFact
	}
	return nil
}

func isOriginalAccessDenialReason(reason string) bool {
	switch strings.TrimSpace(reason) {
	case "asset_not_ready",
		"asset_policy",
		"post_visibility",
		"unsupported_media_type":
		return true
	default:
		return false
	}
}
