// spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-003
// spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-003.t1
package model_test

import (
	"errors"
	"testing"
	"time"

	quotamodel "quwoquan_service/services/content-service/internal/media/original_access_quota/domain/model"
)

func TestNewReservationDerivesStableWindowIdentityAndAbsoluteGrantDeadline(t *testing.T) {
	decidedAt := time.Date(2030, time.March, 4, 5, 6, 7, 0, time.UTC)
	policy := quotamodel.Policy{
		MaxGrants: 6,
		Window:    5 * time.Minute,
		GrantTTL:  5 * time.Minute,
	}

	reservation, err := quotamodel.NewReservation(
		"idempotency-key",
		"command-digest",
		"persona-1",
		"media-1",
		"save",
		decidedAt,
		policy,
	)
	if err != nil {
		t.Fatalf("new reservation: %v", err)
	}

	windowStart := time.Date(2030, time.March, 4, 5, 5, 0, 0, time.UTC)
	if reservation.QuotaID != quotamodel.QuotaID("persona-1", "media-1", "save", windowStart) {
		t.Fatalf("quota identity drift: %q", reservation.QuotaID)
	}
	if reservation.WindowStartedAt != windowStart ||
		reservation.WindowExpiresAt != windowStart.Add(5*time.Minute) ||
		reservation.GrantExpiresAt != decidedAt.Add(5*time.Minute) {
		t.Fatalf("reservation deadline drift: %+v", reservation)
	}
}

func TestNewReservationRejectsMissingCommandDigest(t *testing.T) {
	_, err := quotamodel.NewReservation(
		"idempotency-key",
		"",
		"persona-1",
		"media-1",
		"view",
		time.Date(2030, time.March, 4, 5, 6, 7, 0, time.UTC),
		quotamodel.Policy{
			MaxGrants: 1,
			Window:    time.Minute,
			GrantTTL:  time.Minute,
		},
	)
	if !errors.Is(err, quotamodel.ErrInvalidOriginalAccessQuota) {
		t.Fatalf("missing command digest error=%v", err)
	}
}
