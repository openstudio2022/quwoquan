// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/feedback-ingestion-sampling/spec.md#gwt-001
// readiness_case: report-behaviors-local
package http_test

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	rtrec "quwoquan_service/runtime/recommendation"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	behaviorhttp "quwoquan_service/services/content-service/internal/content/content_behavior_fact/adapters/inbound/http"
	behaviorapp "quwoquan_service/services/content-service/internal/content/content_behavior_fact/application"
	postpersistence "quwoquan_service/services/content-service/internal/content/post/infrastructure/persistence"
)

type recordingBatchProcessor struct {
	events []behaviorapp.BehaviorEventInput
}

type acceptingSignalProcessor struct{}

func (acceptingSignalProcessor) ProcessSignal(context.Context, rtrec.BehaviorSignal) error {
	return nil
}

func (acceptingSignalProcessor) ProcessSignalBatch(context.Context, []rtrec.BehaviorSignal) error {
	return nil
}

func (processor *recordingBatchProcessor) ProcessBatch(
	_ context.Context,
	events []behaviorapp.BehaviorEventInput,
) (behaviorapp.BatchReceipt, error) {
	processor.events = append([]behaviorapp.BehaviorEventInput(nil), events...)
	return behaviorapp.BatchReceipt{AcceptedCount: len(events)}, nil
}

func TestReportBehaviorsAcceptsOnlyTypedWireAndInjectsTrustedCoordinates(t *testing.T) {
	processor := &recordingBatchProcessor{}
	handler := behaviorhttp.NewHandler(processor)
	occurredAt := time.Now().UTC().Add(-time.Second).Format(time.RFC3339Nano)
	payload := fmt.Sprintf(`{"events":[{"clientEventId":"motion-1","occurredAt":%q,"contentId":"post-1","action":"content_depth","state":"works_image_pageflip_motion","playbackSessionId":"playback-1","pageVisitId":"visit-1","direction":"back","motionProfile":"reduced_motion","settleMs":0,"reducedMotion":true,"committed":false}]}`, occurredAt)

	recorder := httptest.NewRecorder()
	handler.Report(recorder, trustedBehaviorRequest(payload))
	if recorder.Code != http.StatusOK {
		t.Fatalf("typed behavior wire status=%d body=%s", recorder.Code, recorder.Body.String())
	}
	var receipt behaviorapp.BatchReceipt
	if err := json.Unmarshal(recorder.Body.Bytes(), &receipt); err != nil {
		t.Fatalf("decode typed behavior receipt: %v", err)
	}
	if receipt.AcceptedCount != 1 || receipt.ReplayedCount != 0 {
		t.Fatalf("typed behavior receipt=%+v", receipt)
	}
	if len(processor.events) != 1 {
		t.Fatalf("processor received %d events", len(processor.events))
	}
	event := processor.events[0]
	if event.UserID != "persona-1" || event.PersonaID != "persona-1" || event.SessionID != "runtime-session-1" {
		t.Fatalf("trusted coordinates were not injected: %+v", event)
	}
	if event.PlaybackSessionID != "playback-1" || event.PageVisitID != "visit-1" || event.SettleMS == nil || *event.SettleMS != 0 || event.Committed == nil || *event.Committed {
		t.Fatalf("typed motion evidence drifted: %+v", event)
	}
}

func TestReportBehaviorsRejectsClientOwnedActorAndRuntimeSession(t *testing.T) {
	handler := behaviorhttp.NewHandler(&recordingBatchProcessor{})
	occurredAt := time.Now().UTC().Add(-time.Second).Format(time.RFC3339Nano)
	for _, forbidden := range []string{
		fmt.Sprintf(`{"userId":"spoofed","events":[{"clientEventId":"event-1","occurredAt":%q,"action":"assistant_interest","tagRefs":["Topic/travel"]}]}`, occurredAt),
		fmt.Sprintf(`{"events":[{"clientEventId":"event-2","occurredAt":%q,"action":"assistant_interest","sessionId":"spoofed","tagRefs":["Topic/travel"]}]}`, occurredAt),
	} {
		recorder := httptest.NewRecorder()
		handler.Report(recorder, trustedBehaviorRequest(forbidden))
		if recorder.Code != http.StatusBadRequest {
			t.Fatalf("forbidden actor/session wire status=%d body=%s", recorder.Code, recorder.Body.String())
		}
	}
}

func TestReportBehaviorsFailsClosedOnIncompletePageflipEvidence(t *testing.T) {
	service := behaviorapp.NewBehaviorService(
		acceptingSignalProcessor{},
		postpersistence.NewPostStore([]postmodel.Post{}),
	)
	handler := behaviorhttp.NewHandler(service)
	occurredAt := time.Now().UTC().Add(-time.Second).Format(time.RFC3339Nano)
	payload := fmt.Sprintf(`{"events":[{"clientEventId":"motion-incomplete","occurredAt":%q,"contentId":"post-1","action":"content_depth","state":"works_image_pageflip_motion","direction":"forward","motionProfile":"comfort_curl","settleMs":120,"committed":true}]}`, occurredAt)
	recorder := httptest.NewRecorder()
	handler.Report(recorder, trustedBehaviorRequest(payload))
	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("incomplete pageflip evidence status=%d body=%s", recorder.Code, recorder.Body.String())
	}
}

func trustedBehaviorRequest(payload string) *http.Request {
	request := httptest.NewRequest(http.MethodPost, "/content/behaviors", strings.NewReader(payload))
	actor := operation.ActorContext{AccountID: "account-1", PersonaID: "persona-1"}
	request = request.WithContext(operation.WithContext(request.Context(), operation.Context{
		OperationID: "content.content_behavior_fact.ReportBehaviors",
		RequestID:   "request-1",
		TraceID:     "trace-1",
		SessionID:   "runtime-session-1",
		Actor:       actor,
	}))
	return request.WithContext(rtauth.WithPrincipal(request.Context(), rtauth.Principal{Actor: actor}))
}
