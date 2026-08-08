// spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-003
// readiness_case: append-original-access-audit-local
package application_test

import (
	"context"
	"testing"
	"time"

	originalaccessapp "quwoquan_service/services/content-service/internal/media/media_original_access_fact/application"
	originalaccessmodel "quwoquan_service/services/content-service/internal/media/media_original_access_fact/domain/model"
	originalaccessports "quwoquan_service/services/content-service/internal/media/media_original_access_fact/domain/ports"
)

func TestAppendOriginalAccessAuditRecordsTheDecisionWithoutOwningQuotaState(t *testing.T) {
	now := time.Date(2030, time.September, 10, 11, 12, 13, 0, time.UTC)
	store := &memoryOriginalAccessStore{facts: map[string]originalaccessmodel.Fact{}}
	service := originalaccessapp.NewService(store)
	decision := originalaccessapp.Decision{
		AssetID: "media-original-local", ViewerID: "persona-original-owner",
		Purpose: "save", Outcome: "granted", Reason: "authorized",
		IdempotencyKey: "original-access-local", CommandDigest: "digest",
		DecidedAt: now, GrantExpiresAt: now.Add(5 * time.Minute),
	}
	first, err := service.AppendAudit(context.Background(), decision)
	if err != nil {
		t.Fatalf("append original access audit: %v", err)
	}
	replayed, err := service.AppendAudit(context.Background(), decision)
	if err != nil {
		t.Fatalf("replay original access audit: %v", err)
	}
	if first.AuditID == "" || first.Outcome != "granted" || first.ExpiresAt != now.Add(5*time.Minute) {
		t.Fatalf("audit record drift: %+v", first)
	}
	if replayed.AuditID != first.AuditID || replayed.ExpiresAt != first.ExpiresAt || !replayed.Replayed {
		t.Fatalf("audit replay drift: first=%+v replay=%+v", first, replayed)
	}
	if len(store.facts) != 1 || store.appendCalls != 2 {
		t.Fatalf("audit append drift: facts=%d calls=%d", len(store.facts), store.appendCalls)
	}
}

func TestAppendOriginalAccessAuditKeepsDenialsWithoutGrantDeadline(t *testing.T) {
	now := time.Date(2030, time.September, 10, 11, 12, 13, 0, time.UTC)
	store := &memoryOriginalAccessStore{facts: map[string]originalaccessmodel.Fact{}}
	service := originalaccessapp.NewService(store)
	record, err := service.AppendAudit(context.Background(), originalaccessapp.Decision{
		AssetID: "media-original-local", ViewerID: "persona-original-owner",
		Purpose: "view", Outcome: "rate_limited", Reason: "rate_limit_exhausted",
		IdempotencyKey: "original-access-rate-limited", CommandDigest: "digest",
		DecidedAt: now, GrantExpiresAt: now.Add(5 * time.Minute),
	})
	if err != nil {
		t.Fatalf("append rate limited audit: %v", err)
	}
	if !record.ExpiresAt.IsZero() {
		t.Fatalf("non granted audit must not carry a grant deadline: %+v", record)
	}
}

type memoryOriginalAccessStore struct {
	facts       map[string]originalaccessmodel.Fact
	appendCalls int
}

func (store *memoryOriginalAccessStore) Append(
	_ context.Context,
	request originalaccessports.AppendRequest,
) (originalaccessports.AppendResult, error) {
	store.appendCalls++
	if err := request.Fact.Validate(); err != nil {
		return originalaccessports.AppendResult{}, err
	}
	key := request.Fact.IdempotencyKey
	if existing, found := store.facts[key]; found {
		return originalaccessports.AppendResult{Fact: existing, Replayed: true}, nil
	}
	store.facts[key] = request.Fact
	return originalaccessports.AppendResult{Fact: request.Fact}, nil
}
