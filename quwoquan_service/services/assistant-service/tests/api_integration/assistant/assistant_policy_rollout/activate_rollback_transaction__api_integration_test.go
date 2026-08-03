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
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	releaseapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/application"
	releasemodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/domain/model"
	releasepersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/infrastructure/persistence"
	rollouthttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/adapters/inbound/http"
	rolloutapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/application"
	rolloutmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/domain/model"
	rolloutpersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/infrastructure/persistence"
)

func TestAssistantPolicyRolloutActivatesAndRollsBackWithCASReceiptsAndOutbox(t *testing.T) {
	testinfra.ConfigureLocalContainerRuntime()
	startupCtx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
	defer cancel()
	runtime, err := testinfra.StartRealMongo(startupCtx, "assistant_policy_rollout_api_integration")
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

	releaseStore := releasepersistence.NewMongoStore(runtime.Database)
	rolloutStore := rolloutpersistence.NewMongoStore(runtime.Database)
	if err := releaseStore.EnsureIndexes(startupCtx); err != nil {
		t.Fatalf("ensure release indexes: %v", err)
	}
	if err := rolloutStore.EnsureIndexes(startupCtx); err != nil {
		t.Fatalf("ensure rollout indexes: %v", err)
	}
	releases := releaseapplication.NewService(releaseStore, nil)
	baseline := rolloutPolicyRelease(t, "baseline")
	candidate := rolloutPolicyRelease(t, "candidate")
	for _, release := range []releasemodel.Release{baseline, candidate} {
		if _, err := releases.Stage(startupCtx, "stage-"+release.ReleaseDigest, release); err != nil {
			t.Fatalf("stage release %s: %v", release.ReleaseDigest, err)
		}
	}
	mux := http.NewServeMux()
	rollouthttp.NewHandler(rolloutapplication.NewService(rolloutStore, releases, nil)).RegisterRoutes(mux)

	buckets := []map[string]any{{"cohort": "all", "weightBasisPoints": 10000}}
	activateBaseline := map[string]any{
		"revision": 0, "bucketDefinitions": buckets,
		"assignments": []map[string]any{{"cohort": "all", "releaseDigest": baseline.ReleaseDigest}},
	}
	first := rolloutRequest(t, mux, "/internal/assistant/policy-rollouts/assistant-default/activate", "activate-baseline", activateBaseline)
	if first.Code != http.StatusOK {
		t.Fatalf("activate baseline status=%d body=%s", first.Code, first.Body.String())
	}
	var firstRollout rolloutmodel.Rollout
	if err := json.Unmarshal(first.Body.Bytes(), &firstRollout); err != nil {
		t.Fatalf("decode baseline rollout: %v", err)
	}
	if firstRollout.Revision != 1 || firstRollout.Assignments[0].ReleaseDigest != baseline.ReleaseDigest {
		t.Fatalf("unexpected baseline rollout: %+v", firstRollout)
	}
	replay := rolloutRequest(t, mux, "/internal/assistant/policy-rollouts/assistant-default/activate", "activate-baseline", activateBaseline)
	if replay.Code != http.StatusOK || replay.Body.String() != first.Body.String() {
		t.Fatalf("activation replay drifted: status=%d body=%s first=%s", replay.Code, replay.Body.String(), first.Body.String())
	}

	activateCandidate := map[string]any{
		"revision": 1, "bucketDefinitions": buckets,
		"assignments": []map[string]any{{"cohort": "all", "releaseDigest": candidate.ReleaseDigest}},
	}
	second := rolloutRequest(t, mux, "/internal/assistant/policy-rollouts/assistant-default/activate", "activate-candidate", activateCandidate)
	if second.Code != http.StatusOK {
		t.Fatalf("activate candidate status=%d body=%s", second.Code, second.Body.String())
	}
	var secondRollout rolloutmodel.Rollout
	if err := json.Unmarshal(second.Body.Bytes(), &secondRollout); err != nil {
		t.Fatalf("decode candidate rollout: %v", err)
	}
	if secondRollout.Revision != 2 || secondRollout.Assignments[0].ReleaseDigest != candidate.ReleaseDigest {
		t.Fatalf("unexpected candidate rollout: %+v", secondRollout)
	}

	rollback := rolloutRequest(t, mux, "/internal/assistant/policy-rollouts/assistant-default/rollback", "rollback-candidate", map[string]any{"revision": 2})
	if rollback.Code != http.StatusOK {
		t.Fatalf("rollback status=%d body=%s", rollback.Code, rollback.Body.String())
	}
	var rolledBack rolloutmodel.Rollout
	if err := json.Unmarshal(rollback.Body.Bytes(), &rolledBack); err != nil {
		t.Fatalf("decode rollback: %v", err)
	}
	if rolledBack.Revision != 3 || rolledBack.Assignments[0].ReleaseDigest != baseline.ReleaseDigest {
		t.Fatalf("unexpected rollback: %+v", rolledBack)
	}
	assertPolicyRolloutCount(t, runtime, "assistant_policy_rollouts", 1)
	assertPolicyRolloutCount(t, runtime, "assistant_policy_rollout_receipts", 3)
	assertPolicyRolloutCount(t, runtime, "assistant_policy_rollout_outbox", 3)

	stale := rolloutRequest(t, mux, "/internal/assistant/policy-rollouts/assistant-default/activate", "activate-stale", activateCandidate)
	if stale.Code != http.StatusConflict || !strings.Contains(stale.Body.String(), "policy_rollout_revision_conflict") {
		t.Fatalf("stale revision status=%d body=%s", stale.Code, stale.Body.String())
	}
	assertPolicyRolloutCount(t, runtime, "assistant_policy_rollout_receipts", 3)
	assertPolicyRolloutCount(t, runtime, "assistant_policy_rollout_outbox", 3)
}

func rolloutPolicyRelease(t *testing.T, variant string) releasemodel.Release {
	t.Helper()
	release := releasemodel.Release{
		PolicyID: "assistant-default", DefaultTemplateID: "default",
		Templates: []releasemodel.Template{{
			TemplateID: "default", SkillID: "fallback_general_search", DomainID: "assistant",
			PromptPolicy: "grounded answer " + variant, AllowedTools: []string{"app_search"}, SearchIntensity: "medium",
		}},
		LearningContextPolicy: releasemodel.LearningContextPolicy{
			Enabled: true, AllowedSignals: []string{"feedback_counts"}, MinimumFeedbackSamples: 3, WindowDays: 30,
		},
	}
	digest, err := releasemodel.Digest(release)
	if err != nil {
		t.Fatalf("digest rollout release: %v", err)
	}
	release.ReleaseDigest = digest
	return release
}

func rolloutRequest(t *testing.T, handler http.Handler, path, commandID string, body any) *httptest.ResponseRecorder {
	t.Helper()
	payload, err := json.Marshal(body)
	if err != nil {
		t.Fatalf("marshal rollout request: %v", err)
	}
	request := httptest.NewRequest(http.MethodPost, path, bytes.NewReader(payload))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", commandID)
	request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
		Actor: operation.ActorContext{AccountID: "policy-operator", PersonaID: "policy-operator:persona"},
	}))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}

func assertPolicyRolloutCount(t *testing.T, runtime *testinfra.RealMongo, collection string, want int64) {
	t.Helper()
	count, err := runtime.Database.Collection(collection).CountDocuments(t.Context(), bson.M{})
	if err != nil || count != want {
		t.Fatalf("%s count=%d err=%v want=%d", collection, count, err, want)
	}
}
