// spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-003
// readiness_case: reserve-original-image-access-grant-local
package application_test

import (
	"context"
	"fmt"
	"testing"
	"time"

	"quwoquan_service/runtime/commandmeta"
	rterr "quwoquan_service/runtime/errors"
	quotagenerated "quwoquan_service/services/content-service/generated/media/original_access_quota"
	mediaassetports "quwoquan_service/services/content-service/internal/media/media_asset/domain/ports"
	quotaapp "quwoquan_service/services/content-service/internal/media/original_access_quota/application"
	quotamodel "quwoquan_service/services/content-service/internal/media/original_access_quota/domain/model"
	quotaports "quwoquan_service/services/content-service/internal/media/original_access_quota/domain/ports"
)

func TestReserveOriginalImageAccessGrantHoldsTheQuotaInvariant(t *testing.T) {
	now := time.Date(2030, time.September, 10, 11, 12, 13, 0, time.UTC)
	quotas := newMemoryQuotaStore()
	audits := newMemoryAuditAppender()
	service := quotaapp.NewService(
		quotas,
		audits,
		readyOriginalAccessAsset{},
		visibleOriginalAccessPost{},
		originalAccessSigner{},
		quotaapp.WithClock(func() time.Time { return now }),
	)
	ctx := commandmeta.WithIdempotencyKey(context.Background(), "original-access-local")
	command := quotaapp.Command{
		AssetID: "media-original-local", ViewerID: "persona-original-owner", Purpose: "save",
	}
	first, err := service.Reserve(ctx, command)
	if err != nil {
		t.Fatalf("reserve original image access grant: %v", err)
	}
	replayed, err := service.Reserve(ctx, command)
	if err != nil {
		t.Fatalf("replay original image access grant: %v", err)
	}
	if first.AssetID != command.AssetID || first.Status != "granted" ||
		first.OriginalURL == "" || first.AuditID == "" || first.ExpiresAt != now.Add(5*time.Minute) {
		t.Fatalf("original access result drift: %+v", first)
	}
	if replayed != first {
		t.Fatalf("replay changed the grant: first=%+v replay=%+v", first, replayed)
	}
	if audits.records != 1 {
		t.Fatalf("replay must not append a second audit fact, got %d", audits.records)
	}
	if consumed := quotas.consumed(first.AssetID); consumed != 1 {
		t.Fatalf("replay must not consume a second quota slot, got %d", consumed)
	}
}

func TestReserveOriginalImageAccessGrantRejectsAnExhaustedWindow(t *testing.T) {
	now := time.Date(2030, time.September, 10, 11, 12, 13, 0, time.UTC)
	quotas := newMemoryQuotaStore()
	audits := newMemoryAuditAppender()
	service := quotaapp.NewService(
		quotas, audits, readyOriginalAccessAsset{}, visibleOriginalAccessPost{},
		originalAccessSigner{}, quotaapp.WithClock(func() time.Time { return now }),
	)
	command := quotaapp.Command{
		AssetID: "media-original-local", ViewerID: "persona-original-owner", Purpose: "save",
	}
	maxGrants := quotagenerated.ContentMediaOriginalAccessRateLimitMaxGrants
	for attempt := 0; attempt < maxGrants; attempt++ {
		ctx := commandmeta.WithIdempotencyKey(context.Background(), fmt.Sprintf("grant-%d", attempt))
		if _, err := service.Reserve(ctx, command); err != nil {
			t.Fatalf("reserve attempt %d: %v", attempt, err)
		}
	}
	ctx := commandmeta.WithIdempotencyKey(context.Background(), "grant-overflow")
	_, err := service.Reserve(ctx, command)
	if err == nil {
		t.Fatal("exhausted window must not produce a grant")
	}
	appError, ok := err.(*rterr.AppError)
	if !ok || appError.Code.String() != quotagenerated.AppErrorFromOriginalAccessRateLimited("").Code.String() {
		t.Fatalf("exhausted window must surface the rate limited code, got %v", err)
	}
	if audits.lastOutcome != "rate_limited" {
		t.Fatalf("exhausted window must be audited as rate_limited, got %q", audits.lastOutcome)
	}
	if consumed := quotas.consumed(command.AssetID); consumed != maxGrants {
		t.Fatalf("rejected request must not consume a slot, consumed=%d max=%d", consumed, maxGrants)
	}
}

type memoryQuotaStore struct {
	counts       map[string]int
	reservations map[string]quotamodel.Reservation
}

func newMemoryQuotaStore() *memoryQuotaStore {
	return &memoryQuotaStore{
		counts:       map[string]int{},
		reservations: map[string]quotamodel.Reservation{},
	}
}

func (store *memoryQuotaStore) consumed(assetID string) int {
	total := 0
	for _, reservation := range store.reservations {
		if reservation.AssetID == assetID {
			total++
		}
	}
	return total
}

func (store *memoryQuotaStore) Reserve(
	_ context.Context,
	requested quotamodel.Reservation,
	policy quotamodel.Policy,
) (quotaports.ReserveResult, error) {
	if existing, found := store.reservations[requested.IdempotencyKey]; found {
		return quotaports.ReserveResult{Reservation: existing, Replayed: true}, nil
	}
	if store.counts[requested.QuotaID] >= policy.MaxGrants {
		return quotaports.ReserveResult{}, quotagenerated.AppErrorFromOriginalAccessRateLimited(
			"media original access rate limit exhausted",
		)
	}
	store.counts[requested.QuotaID]++
	store.reservations[requested.IdempotencyKey] = requested
	return quotaports.ReserveResult{Reservation: requested}, nil
}

type memoryAuditAppender struct {
	facts       map[string]quotaports.AuditRecord
	records     int
	lastOutcome string
}

func newMemoryAuditAppender() *memoryAuditAppender {
	return &memoryAuditAppender{facts: map[string]quotaports.AuditRecord{}}
}

func (appender *memoryAuditAppender) AppendOriginalAccessAudit(
	_ context.Context,
	decision quotaports.AuditDecision,
) (quotaports.AuditRecord, error) {
	appender.lastOutcome = decision.Outcome
	if existing, found := appender.facts[decision.IdempotencyKey]; found {
		existing.Replayed = true
		return existing, nil
	}
	record := quotaports.AuditRecord{
		AuditID: "moa_" + decision.IdempotencyKey,
		Outcome: decision.Outcome,
	}
	if decision.Outcome == "granted" {
		record.ExpiresAt = decision.GrantExpiresAt
	}
	appender.facts[decision.IdempotencyKey] = record
	appender.records++
	return record, nil
}

type readyOriginalAccessAsset struct{}

func (readyOriginalAccessAsset) FindOriginalAccessAsset(
	context.Context,
	string,
) (mediaassetports.OriginalAccessSlice, bool, error) {
	return mediaassetports.OriginalAccessSlice{
		AssetID: "media-original-local", OwnerID: "persona-original-owner",
		ObjectKey: "media/original/local.jpg", MediaType: "image", MimeType: "image/jpeg",
		FileSize: 512, ProcessingStatus: "ready", AccessPolicy: "owner_only",
	}, true, nil
}

type visibleOriginalAccessPost struct{}

func (visibleOriginalAccessPost) CanViewerAccessPublishedMedia(
	context.Context,
	string,
	string,
) (bool, error) {
	return true, nil
}

type originalAccessSigner struct{}

func (originalAccessSigner) DeliveryURLUntil(
	_ context.Context,
	objectKey string,
	expiresAt time.Time,
) (string, error) {
	return fmt.Sprintf("https://cdn.example.test/%s?expires=%d", objectKey, expiresAt.Unix()), nil
}
