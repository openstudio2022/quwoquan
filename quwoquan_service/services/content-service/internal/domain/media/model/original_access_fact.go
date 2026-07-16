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
	IdempotencyKey string
	GrantedAt      time.Time
	ExpiresAt      time.Time
}

func (fact MediaOriginalAccessFact) Validate() error {
	if strings.TrimSpace(fact.AuditID) == "" ||
		strings.TrimSpace(fact.AssetID) == "" ||
		strings.TrimSpace(fact.ViewerID) == "" ||
		strings.TrimSpace(fact.IdempotencyKey) == "" ||
		fact.GrantedAt.IsZero() ||
		!fact.ExpiresAt.After(fact.GrantedAt) {
		return ErrInvalidMediaOriginalAccessFact
	}
	purpose := strings.ToLower(strings.TrimSpace(fact.Purpose))
	if purpose != "view" && purpose != "save" {
		return ErrInvalidMediaOriginalAccessFact
	}
	return nil
}
