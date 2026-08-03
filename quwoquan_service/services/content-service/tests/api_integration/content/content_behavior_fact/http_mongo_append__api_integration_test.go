package content_behavior_fact_test

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	rtrec "quwoquan_service/runtime/recommendation"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	behaviorhttp "quwoquan_service/services/content-service/internal/content/content_behavior_fact/adapters/inbound/http"
	behaviorapp "quwoquan_service/services/content-service/internal/content/content_behavior_fact/application"
	behaviorpersistence "quwoquan_service/services/content-service/internal/content/content_behavior_fact/infrastructure/persistence"
	postpersistence "quwoquan_service/services/content-service/internal/content/post/infrastructure/persistence"
)

type acceptingSignalProcessor struct{}

func (acceptingSignalProcessor) ProcessSignal(context.Context, rtrec.BehaviorSignal) error {
	return nil
}

func (acceptingSignalProcessor) ProcessSignalBatch(context.Context, []rtrec.BehaviorSignal) error {
	return nil
}

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

	store := behaviorpersistence.NewMongoBehaviorEventStore(runtime.Database, nil)
	service := behaviorapp.NewBehaviorService(
		acceptingSignalProcessor{},
		postpersistence.NewPostStore([]postmodel.Post{}),
		behaviorapp.WithBehaviorEventStore(store),
	)
	handler := behaviorhttp.NewHandler(service)
	occurredAt := time.Now().UTC().Add(-time.Second).Format(time.RFC3339Nano)
	body := fmt.Sprintf(`{"userId":"spoofed-user","sessionId":"spoofed-session","events":[{"clientEventId":"behavior-once","occurredAt":%q,"userId":"spoofed-user","deviceActorId":"spoofed-device","sessionId":"","action":"assistant_interest","tagRefs":["Topic/travel"]}]}`, occurredAt)

	perform := func() int {
		request := httptest.NewRequest(http.MethodPost, "/content/behaviors", strings.NewReader(body))
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
		return recorder.Code
	}
	if status := perform(); status != http.StatusNoContent {
		t.Fatalf("ReportBehaviors status=%d", status)
	}
	if status := perform(); status != http.StatusNoContent {
		t.Fatalf("ReportBehaviors replay status=%d", status)
	}

	count, err := runtime.Database.Collection("rm_behavior_events").CountDocuments(
		context.Background(),
		bson.M{"userId": "trusted-persona", "clientEventId": "behavior-once"},
	)
	if err != nil || count != 1 {
		t.Fatalf("trusted fact count=%d err=%v", count, err)
	}
	var fact bson.M
	if err := runtime.Database.Collection("rm_behavior_events").FindOne(
		context.Background(),
		bson.M{"clientEventId": "behavior-once"},
	).Decode(&fact); err != nil {
		t.Fatalf("read ContentBehaviorFact: %v", err)
	}
	if fact["sessionId"] != "trusted-session" || fact["deviceActorId"] == "spoofed-device" {
		t.Fatalf("untrusted actor/session leaked into fact: %#v", fact)
	}
}
