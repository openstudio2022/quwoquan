package api_integration_test

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/internal/platform/testinfra"
	"quwoquan_service/runtime/commandmeta"
	moderationhttp "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/adapters/inbound/http"
	moderationapp "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/application"
	moderationpersistence "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/infrastructure/persistence"
)

func TestOpenHTTPCommitsCaseReceiptAuditAndOutboxInMongo(t *testing.T) {
	runtime, err := testinfra.StartRealMongo(context.Background(), "post_moderation_case_http")
	if err != nil {
		t.Fatalf("start real MongoDB: %v", err)
	}
	t.Cleanup(func() {
		if closeErr := runtime.Close(context.Background()); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})
	store := moderationpersistence.NewMongoPostModerationCaseStore(
		runtime.Database.Collection("post_moderation_cases"),
	)
	if err := store.EnsureIndexes(context.Background()); err != nil {
		t.Fatalf("ensure indexes: %v", err)
	}
	service := moderationapp.NewModerationService(
		moderationapp.BindDataPorts(store),
		moderationapp.WithClock(func() time.Time {
			return time.Date(2030, time.June, 7, 8, 9, 10, 0, time.UTC)
		}),
		moderationapp.WithIdentifierGenerator(func(string) (string, error) {
			return "pmc-object-owned", nil
		}),
	)
	handler := moderationhttp.NewHandler(moderationapp.BindFacades(service))
	request := httptest.NewRequest(
		http.MethodPost,
		"/internal/content/posts/post-moderated/moderation-cases",
		strings.NewReader(`{"postVersion":3,"contentDigest":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}`),
	)
	request.SetPathValue("postId", "post-moderated")
	request = request.WithContext(commandmeta.WithIdempotencyKey(request.Context(), "open-moderation-once"))
	recorder := httptest.NewRecorder()
	handler.Open(recorder, request)
	if recorder.Code != http.StatusOK || !strings.Contains(recorder.Body.String(), `"caseId":"pmc-object-owned"`) {
		t.Fatalf("status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	for _, collection := range []string{
		"post_moderation_cases",
		"post_moderation_case_command_receipts",
		"post_moderation_case_audit",
		"post_moderation_case_outbox",
	} {
		count, countErr := runtime.Database.Collection(collection).CountDocuments(context.Background(), bson.D{})
		if countErr != nil || count != 1 {
			t.Fatalf("%s count=%d err=%v", collection, count, countErr)
		}
	}
}
