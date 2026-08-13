// spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-003
// spec_ref: specs/feature-tree/discovery-content/media-processing-helper-read/image-delivery-variants/spec.md#gwt-003.t1
// readiness_case: append-original-access-audit-api
package api_integration_test

import (
	"context"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/internal/platform/testinfra"
	auditapp "quwoquan_service/services/content-service/internal/media/media_original_access_fact/application"
	auditpersistence "quwoquan_service/services/content-service/internal/media/media_original_access_fact/infrastructure/persistence"
)

func TestAppendingAuditFactsCommitsOneImmutableFactPerIdempotencyKey(t *testing.T) {
	runtime, err := testinfra.StartRealMongo(context.Background(), "content_media_original_access_fact")
	if err != nil {
		t.Fatalf("start real MongoDB: %v", err)
	}
	t.Cleanup(func() {
		if closeErr := runtime.Close(context.Background()); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})
	database := runtime.Database
	store := auditpersistence.NewMongoStore(database)
	if err := store.EnsureIndexes(context.Background()); err != nil {
		t.Fatalf("ensure indexes: %v", err)
	}
	service := auditapp.NewService(store)
	now := time.Date(2030, time.March, 4, 5, 6, 7, 0, time.UTC)
	decision := auditapp.Decision{
		AssetID: "media_image", ViewerID: "persona_owner", Purpose: "save",
		Outcome: "granted", Reason: "authorized",
		IdempotencyKey: "original-access-once", CommandDigest: "digest",
		DecidedAt: now, GrantExpiresAt: now.Add(5 * time.Minute),
	}
	first, err := service.AppendAudit(context.Background(), decision)
	if err != nil {
		t.Fatalf("append audit: %v", err)
	}
	replayed, err := service.AppendAudit(context.Background(), decision)
	if err != nil {
		t.Fatalf("replay audit: %v", err)
	}
	if replayed.AuditID != first.AuditID || !replayed.ExpiresAt.Equal(first.ExpiresAt) {
		t.Fatalf("replay must reuse the original audit identity and deadline: first=%+v replay=%+v", first, replayed)
	}
	count, err := database.Collection("media_original_access_facts").CountDocuments(context.Background(), bson.D{})
	if err != nil {
		t.Fatalf("count facts: %v", err)
	}
	if count != 1 {
		t.Fatalf("expected one immutable fact after replay, got %d", count)
	}
	quotas, err := database.Collection("media_original_access_rate_limits").CountDocuments(context.Background(), bson.D{})
	if err != nil {
		t.Fatalf("count quota rows: %v", err)
	}
	if quotas != 0 {
		t.Fatalf("the audit fact must not write quota state, got %d rows", quotas)
	}
}
