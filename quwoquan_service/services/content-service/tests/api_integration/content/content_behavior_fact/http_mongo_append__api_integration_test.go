// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/feedback-ingestion-sampling/spec.md#gwt-001
// readiness_case: report-behaviors-api
package content_behavior_fact_test

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	rtrec "quwoquan_service/runtime/recommendation"
	rtredis "quwoquan_service/runtime/redis"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	behaviorhttp "quwoquan_service/services/content-service/internal/content/content_behavior_fact/adapters/inbound/http"
	behaviorapp "quwoquan_service/services/content-service/internal/content/content_behavior_fact/application"
	behaviorpersistence "quwoquan_service/services/content-service/internal/content/content_behavior_fact/infrastructure/persistence"
	postpersistence "quwoquan_service/services/content-service/internal/content/post/infrastructure/persistence"
)

func TestReportBehaviorsUsesTrustedActorAndIdempotentlyAppendsRealMongoFact(t *testing.T) {
	runtime, err := testinfra.StartRealMongo(context.Background(), "content_behavior_fact_http")
	if err != nil {
		t.Fatalf("start real MongoDB: %v", err)
	}
	t.Cleanup(func() {
		if closeErr := runtime.Close(context.Background()); closeErr != nil {
			t.Errorf("close real MongoDB: %v", closeErr)
		}
	})
	redisRuntime, err := testinfra.StartRealRedis(context.Background())
	if err != nil {
		t.Fatalf("start real Redis: %v", err)
	}
	t.Cleanup(func() {
		if closeErr := redisRuntime.Close(context.Background()); closeErr != nil {
			t.Errorf("close real Redis: %v", closeErr)
		}
	})
	if err := redisRuntime.FlushDBs(context.Background(), 0); err != nil {
		t.Fatalf("flush real Redis: %v", err)
	}
	router := platformredis.MustNewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"rec": {
				Mode: "standalone", Addr: redisRuntime.Addr,
				Password: redisRuntime.Password, DB: 0, TLS: redisRuntime.TLS,
			},
		},
		DefaultScene: "rec",
	})
	t.Cleanup(func() { _ = router.Close() })

	store := behaviorpersistence.NewMongoBehaviorEventStore(runtime.Database, nil)
	service := behaviorapp.NewBehaviorService(
		rtrec.NewHotPath(rtredis.NewRecAdapter(router.Scene("rec"))),
		postpersistence.NewPostStore([]postmodel.Post{{
			ID: "content-motion", AuthorId: "author-motion", ContentType: "photo",
		}}),
		behaviorapp.WithBehaviorEventStore(store),
	)
	handler := behaviorhttp.NewHandler(service)
	occurredAt := time.Now().UTC().Add(-time.Second).Format(time.RFC3339Nano)
	body := fmt.Sprintf(`{"events":[{"clientEventId":"behavior-once","occurredAt":%q,"contentId":"content-motion","action":"content_depth","state":"works_image_pageflip_motion","direction":"forward","motionProfile":"comfort_curl","settleMs":384,"reducedMotion":false,"committed":true}]}`, occurredAt)

	perform := func(payload string) *httptest.ResponseRecorder {
		request := httptest.NewRequest(http.MethodPost, "/content/behaviors", strings.NewReader(payload))
		request.Header.Set("Content-Type", "application/json")
		request = request.WithContext(operation.WithContext(request.Context(), operation.Context{
			OperationID:  "content.content_behavior_fact.ReportBehaviors",
			RequestID:    "request-behavior",
			TraceID:      "trace-behavior",
			SessionID:    "trusted-session",
			ClientPageID: "assistant-entry",
			Actor: operation.ActorContext{
				AccountID: "trusted-account",
				PersonaID: "trusted-persona",
			},
		}))
		request = request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{
			Actor: operation.ActorContext{
				AccountID: "trusted-account",
				PersonaID: "trusted-persona",
			},
		}))
		recorder := httptest.NewRecorder()
		handler.Report(recorder, request)
		return recorder
	}
	if response := perform(fmt.Sprintf(`{"userId":"spoofed-user","events":[{"clientEventId":"spoofed","occurredAt":%q,"action":"assistant_interest","tagRefs":["Topic/travel"]}]}`, occurredAt)); response.Code != http.StatusBadRequest {
		t.Fatalf("ReportBehaviors must reject client actor coordinates, status=%d", response.Code)
	}
	first := perform(body)
	if first.Code != http.StatusOK {
		t.Fatalf("ReportBehaviors status=%d body=%s", first.Code, first.Body.String())
	}
	assertBehaviorReceipt(t, first, 1, 0)
	mixed := perform(fmt.Sprintf(`{"events":[{"clientEventId":"behavior-once","occurredAt":%q,"contentId":"content-motion","action":"content_depth","state":"works_image_pageflip_motion","direction":"forward","motionProfile":"comfort_curl","settleMs":384,"reducedMotion":false,"committed":true},{"clientEventId":"behavior-two","occurredAt":%q,"contentId":"content-motion","action":"content_depth","state":"works_image_pageflip_motion","direction":"back","motionProfile":"reduced_motion","settleMs":120,"reducedMotion":true,"committed":true}]}`, occurredAt, occurredAt))
	if mixed.Code != http.StatusOK {
		t.Fatalf("ReportBehaviors mixed replay status=%d body=%s", mixed.Code, mixed.Body.String())
	}
	assertBehaviorReceipt(t, mixed, 1, 1)
	fullReplay := perform(fmt.Sprintf(`{"events":[{"clientEventId":"behavior-once","occurredAt":%q,"contentId":"content-motion","action":"content_depth","state":"works_image_pageflip_motion","direction":"forward","motionProfile":"comfort_curl","settleMs":384,"reducedMotion":false,"committed":true},{"clientEventId":"behavior-two","occurredAt":%q,"contentId":"content-motion","action":"content_depth","state":"works_image_pageflip_motion","direction":"back","motionProfile":"reduced_motion","settleMs":120,"reducedMotion":true,"committed":true}]}`, occurredAt, occurredAt))
	if fullReplay.Code != http.StatusOK {
		t.Fatalf("ReportBehaviors full replay status=%d body=%s", fullReplay.Code, fullReplay.Body.String())
	}
	assertBehaviorReceipt(t, fullReplay, 0, 2)

	count, err := runtime.Database.Collection("rm_behavior_events").CountDocuments(
		context.Background(),
		bson.M{"userId": "trusted-persona", "clientEventId": "behavior-once"},
	)
	if err != nil || count != 1 {
		t.Fatalf("trusted fact count=%d err=%v", count, err)
	}
	total, err := runtime.Database.Collection("rm_behavior_events").CountDocuments(
		context.Background(),
		bson.M{"userId": "trusted-persona"},
	)
	if err != nil || total != 2 {
		t.Fatalf("trusted batch fact total=%d err=%v", total, err)
	}
	var fact bson.M
	if err := runtime.Database.Collection("rm_behavior_events").FindOne(
		context.Background(),
		bson.M{"clientEventId": "behavior-once"},
	).Decode(&fact); err != nil {
		t.Fatalf("read ContentBehaviorFact: %v", err)
	}
	if fact["sessionId"] != "trusted-session" || fact["personaId"] != "trusted-persona" || fact["userId"] != "trusted-persona" {
		t.Fatalf("untrusted actor/session leaked into fact: %#v", fact)
	}
	if fact["direction"] != "forward" || fact["motionProfile"] != "comfort_curl" || fmt.Sprint(fact["settleMs"]) != "384" || fact["reducedMotion"] != false || fact["committed"] != true {
		t.Fatalf("pageflip motion fact drifted: %#v", fact)
	}
}

func assertBehaviorReceipt(
	t *testing.T,
	response *httptest.ResponseRecorder,
	acceptedCount int,
	replayedCount int,
) {
	t.Helper()
	var receipt behaviorapp.BatchReceipt
	if err := json.Unmarshal(response.Body.Bytes(), &receipt); err != nil {
		t.Fatalf("decode behavior receipt: %v body=%s", err, response.Body.String())
	}
	if receipt.AcceptedCount != acceptedCount || receipt.ReplayedCount != replayedCount {
		t.Fatalf(
			"behavior receipt=%+v want accepted=%d replayed=%d",
			receipt,
			acceptedCount,
			replayedCount,
		)
	}
}
