// spec_ref: specs/feature-tree/assistant-run-learning/run-stream-policy/policy-template-routing/spec.md#gwt-001
package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/internal/platform/testinfra"
	releasehttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/adapters/inbound/http"
	releaseapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/application"
	releasemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/domain/model"
	releasepersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/infrastructure/persistence"
)

func TestAssistantPolicyReleaseStagesStateReceiptAndOutboxAtomically(t *testing.T) {
	testinfra.ConfigureLocalContainerRuntime()
	startupCtx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(startupCtx, "assistant_policy_release_api_integration")
	if err != nil {
		t.Fatalf("start real MongoDB replica set: %v", err)
	}
	t.Cleanup(func() {
		closeCtx, closeCancel := context.WithTimeout(context.Background(), 30*time.Second)
		defer closeCancel()
		if closeErr := runtime.Close(closeCtx); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})

	store := releasepersistence.NewMongoStore(runtime.Database)
	if err := store.EnsureIndexes(startupCtx); err != nil {
		t.Fatalf("ensure AssistantPolicyRelease indexes: %v", err)
	}
	mux := http.NewServeMux()
	releasehttp.NewHandler(releaseapplication.NewService(store, nil)).RegisterRoutes(mux)

	release := policyRelease(t, "baseline")
	first := stageReleaseRequest(t, mux, "stage-policy-baseline", release)
	if first.Code != http.StatusOK {
		t.Fatalf("stage status=%d body=%s", first.Code, first.Body.String())
	}
	var staged releasemodel.Release
	if err := json.Unmarshal(first.Body.Bytes(), &staged); err != nil {
		t.Fatalf("decode staged release: %v", err)
	}
	if staged.PolicyID != release.PolicyID || staged.ReleaseDigest != release.ReleaseDigest || staged.AggregateVersion != 1 || staged.StagedAt.IsZero() {
		t.Fatalf("unexpected staged release: %+v", staged)
	}
	replay := stageReleaseRequest(t, mux, "stage-policy-baseline", release)
	if replay.Code != http.StatusOK || replay.Body.String() != first.Body.String() {
		t.Fatalf("stage replay drifted: status=%d body=%s first=%s", replay.Code, replay.Body.String(), first.Body.String())
	}
	assertPolicyReleaseCount(t, runtime, "assistant_policy_releases", 1)
	assertPolicyReleaseCount(t, runtime, "assistant_policy_release_receipts", 1)
	assertPolicyReleaseCount(t, runtime, "assistant_policy_release_outbox", 1)

	conflict := stageReleaseRequest(t, mux, "stage-policy-baseline", policyRelease(t, "candidate"))
	if conflict.Code != http.StatusConflict || !strings.Contains(conflict.Body.String(), "policy_release_idempotency_conflict") {
		t.Fatalf("idempotency conflict status=%d body=%s", conflict.Code, conflict.Body.String())
	}
	assertPolicyReleaseCount(t, runtime, "assistant_policy_releases", 1)
	assertPolicyReleaseCount(t, runtime, "assistant_policy_release_receipts", 1)
	assertPolicyReleaseCount(t, runtime, "assistant_policy_release_outbox", 1)
}

func policyRelease(t *testing.T, variant string) releasemodel.Release {
	t.Helper()
	release := releasemodel.Release{
		PolicyID: "assistant-default", DefaultTemplateID: "default",
		Templates: []releasemodel.Template{{
			TemplateID: "default", SkillID: "fallback_general_search", DomainID: "assistant",
			PromptPolicy: "grounded answer " + variant, AllowedTools: []string{"app_search"}, SearchIntensity: "medium",
		}},
		LearningContextPolicy: releasemodel.LearningContextPolicy{
			Enabled: true, AllowedSignals: []string{"feedback_counts"},
			MinimumFeedbackSamples: 3, WindowDays: 30,
		},
	}
	digest, err := releasemodel.Digest(release)
	if err != nil {
		t.Fatalf("digest release: %v", err)
	}
	release.ReleaseDigest = digest
	return release
}

func stageReleaseRequest(t *testing.T, handler http.Handler, commandID string, release releasemodel.Release) *httptest.ResponseRecorder {
	t.Helper()
	payload, err := json.Marshal(release)
	if err != nil {
		t.Fatalf("marshal policy release: %v", err)
	}
	request := httptest.NewRequest(http.MethodPost, "/internal/assistant/policy-releases", bytes.NewReader(payload))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", commandID)
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}

func assertPolicyReleaseCount(t *testing.T, runtime *testinfra.RealMongo, collection string, want int64) {
	t.Helper()
	count, err := runtime.Database.Collection(collection).CountDocuments(t.Context(), bson.M{})
	if err != nil || count != want {
		t.Fatalf("%s count=%d err=%v want=%d", collection, count, err, want)
	}
}
