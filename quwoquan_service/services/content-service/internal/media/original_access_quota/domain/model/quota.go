package model

import (
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"strings"
	"time"
)

var ErrInvalidOriginalAccessQuota = errors.New("invalid original access quota reservation")

// Policy carries the window and TTL invariants of the OriginalAccessQuota
// aggregate. It is sourced from original_access_policy.yaml codegen constants.
type Policy struct {
	MaxGrants int
	Window    time.Duration
	GrantTTL  time.Duration
}

func (policy Policy) IsValid() bool {
	return policy.MaxGrants > 0 && policy.Window > 0 && policy.GrantTTL > 0
}

// Reservation is one quota slot held by a viewer for an asset and purpose
// inside a fixed window. GrantExpiresAt is decided when the slot is first
// reserved and can never be recomputed for the same idempotency key.
type Reservation struct {
	QuotaID         string
	IdempotencyKey  string
	CommandDigest   string
	ViewerID        string
	AssetID         string
	Purpose         string
	WindowStartedAt time.Time
	WindowExpiresAt time.Time
	GrantExpiresAt  time.Time
}

func (reservation Reservation) Validate() error {
	if strings.TrimSpace(reservation.QuotaID) == "" ||
		strings.TrimSpace(reservation.IdempotencyKey) == "" ||
		strings.TrimSpace(reservation.CommandDigest) == "" ||
		strings.TrimSpace(reservation.ViewerID) == "" ||
		strings.TrimSpace(reservation.AssetID) == "" ||
		reservation.WindowStartedAt.IsZero() {
		return ErrInvalidOriginalAccessQuota
	}
	purpose := strings.ToLower(strings.TrimSpace(reservation.Purpose))
	if purpose != "view" && purpose != "save" {
		return ErrInvalidOriginalAccessQuota
	}
	if !reservation.WindowExpiresAt.After(reservation.WindowStartedAt) ||
		!reservation.GrantExpiresAt.After(reservation.WindowStartedAt) {
		return ErrInvalidOriginalAccessQuota
	}
	return nil
}

// NewReservation derives the quota identity and both absolute deadlines from
// the decision instant. QuotaID must stay byte-identical to the pre-split
// digest so the existing quota rows keep their identity without migration.
func NewReservation(
	idempotencyKey string,
	commandDigest string,
	viewerID string,
	assetID string,
	purpose string,
	decidedAt time.Time,
	policy Policy,
) (Reservation, error) {
	if !policy.IsValid() {
		return Reservation{}, ErrInvalidOriginalAccessQuota
	}
	windowStart := decidedAt.UTC().Truncate(policy.Window)
	reservation := Reservation{
		QuotaID:         QuotaID(viewerID, assetID, purpose, windowStart),
		IdempotencyKey:  strings.TrimSpace(idempotencyKey),
		CommandDigest:   strings.TrimSpace(commandDigest),
		ViewerID:        strings.TrimSpace(viewerID),
		AssetID:         strings.TrimSpace(assetID),
		Purpose:         strings.ToLower(strings.TrimSpace(purpose)),
		WindowStartedAt: windowStart,
		WindowExpiresAt: windowStart.Add(policy.Window),
		GrantExpiresAt:  decidedAt.UTC().Add(policy.GrantTTL),
	}
	if err := reservation.Validate(); err != nil {
		return Reservation{}, err
	}
	return reservation, nil
}

func QuotaID(viewerID string, assetID string, purpose string, windowStart time.Time) string {
	digest := sha256.Sum256([]byte(strings.Join([]string{
		strings.TrimSpace(viewerID),
		strings.TrimSpace(assetID),
		strings.ToLower(strings.TrimSpace(purpose)),
		windowStart.UTC().Format(time.RFC3339Nano),
	}, ":")))
	return hex.EncodeToString(digest[:])
}
