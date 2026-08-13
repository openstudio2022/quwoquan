// spec_ref: specs/feature-tree/chat-conversation/message-reliability-foundation/chat-offline-push-delivery/spec.md#gwt-002
//
// 通用投递 worker 经 integration 提交的组装契约：
//   - Deliver 把 push 投递记录组装为契约 push_delivery action=alert 十字段
//     payload（title/body/targetType/targetId 语义锚点），并按收件人真实
//     设备端点逐端点提交（requestID 掺入 endpointRef 幂等）；
//   - 无可推送端点的收件人按无操作完成，不制造无意义重试；
//   - 组装字段缺失与远端结构化失败原样保留，不吞不降级；
//   - 来电 ring/cancel 提交通道不回归。
package local_contract

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"quwoquan_service/runtime/failures"
	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/services/notification-service/internal/notification_delivery/notification/application"
	integrationclient "quwoquan_service/services/notification-service/internal/notification_delivery/notification/infrastructure/integration"
	notification "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/application"
)

type fixedServiceCredential string

func (c fixedServiceCredential) AuthorizationHeader(context.Context) (string, error) {
	return "Bearer " + string(c), nil
}

type staticDestinationLister struct {
	destinations []notification.PushDestinationRef
	err          error
	calls        atomic.Int32
}

func (s *staticDestinationLister) ListPushDestinations(
	context.Context,
	string,
) ([]notification.PushDestinationRef, error) {
	s.calls.Add(1)
	return s.destinations, s.err
}

func chatPushOutboxRecord() reliabletask.NotificationOutboxRecord {
	return reliabletask.NotificationOutboxRecord{
		NotificationID:        "notification-contract-001",
		SubjectNotificationID: "message-contract-001",
		EventType:             application.NotificationPushRequestedEvent,
		AggregateType:         "NotificationDeliveryJob",
		AggregateID:           "message-contract-001",
		DedupeKey:             "chat-message:evt-001:user-contract-001",
		Payload: map[string]string{
			"messageType":    "chat_message",
			"conversationId": "conv-001",
			"messageId":      "message-contract-001",
			"title":          "李明",
			"summary":        "周六的观星聚会记得带上三脚架",
			"targetType":     "conversation",
			"targetId":       "conv-001",
		},
	}
}

func TestIntegrationDeliveryAdapterAssemblesAlertPerEndpoint(t *testing.T) {
	var payloads []map[string]any
	var requestIDs []string
	upstream := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/integrations/external-requests" {
			http.Error(w, "unexpected integration path", http.StatusNotFound)
			return
		}
		var request map[string]any
		if err := json.NewDecoder(r.Body).Decode(&request); err != nil {
			http.Error(w, err.Error(), http.StatusBadRequest)
			return
		}
		requestID, _ := request["requestId"].(string)
		requestIDs = append(requestIDs, requestID)
		payload, _ := request["payload"].(map[string]any)
		payloads = append(payloads, payload)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusAccepted)
		_ = json.NewEncoder(w).Encode(map[string]any{
			"requestId":  requestID,
			"status":     reliabletask.ExternalInteractionStatusAccepted,
			"acceptedAt": time.Now().UTC().Format(time.RFC3339),
		})
	}))
	t.Cleanup(upstream.Close)
	lister := &staticDestinationLister{
		destinations: []notification.PushDestinationRef{
			{DeviceID: "device-1", EndpointRef: strings.Repeat("a", 64)},
			{DeviceID: "device-2", EndpointRef: strings.Repeat("b", 64)},
		},
	}
	adapter, err := integrationclient.NewExternalInteractionDeliveryAdapter(
		integrationclient.ExternalInteractionDeliveryConfig{
			BaseURL:     upstream.URL,
			Credentials: fixedServiceCredential("service-token"),
			Environment: "gamma",
			Timeout:     time.Second,
		},
		upstream.Client(),
		lister,
	)
	if err != nil {
		t.Fatalf("construct integration delivery adapter: %v", err)
	}
	sequence, err := adapter.Deliver(
		context.Background(),
		chatPushOutboxRecord(),
		"user-contract-001",
	)
	if err != nil {
		t.Fatalf("deliver notification through integration: %v", err)
	}
	if sequence <= 0 || lister.calls.Load() != 1 {
		t.Fatalf("delivery not traceable: sequence=%d listerCalls=%d", sequence, lister.calls.Load())
	}
	if len(payloads) != 2 {
		t.Fatalf("expected one alert submission per endpoint, got %d", len(payloads))
	}
	if requestIDs[0] == requestIDs[1] {
		t.Fatalf("per-endpoint requestId must differ for idempotency: %v", requestIDs)
	}
	seenEndpoints := map[string]bool{}
	for _, payload := range payloads {
		if len(payload) != 10 {
			t.Fatalf("alert payload must contain exactly ten fields: %v", payload)
		}
		if payload["action"] != "alert" ||
			payload["title"] != "李明" ||
			payload["body"] != "周六的观星聚会记得带上三脚架" ||
			payload["targetType"] != "conversation" ||
			payload["targetId"] != "conv-001" ||
			payload["targetPersonaId"] != "user-contract-001" ||
			payload["deliveryKey"] != "chat-message:evt-001:user-contract-001" {
			t.Fatalf("unexpected alert payload assembly: %v", payload)
		}
		endpointRef, _ := payload["endpointRef"].(string)
		seenEndpoints[endpointRef] = true
	}
	if !seenEndpoints[strings.Repeat("a", 64)] || !seenEndpoints[strings.Repeat("b", 64)] {
		t.Fatalf("alert submissions must cover both endpoints: %v", seenEndpoints)
	}
}

func TestIntegrationDeliveryAdapterCompletesWithoutEndpointsAsNoop(t *testing.T) {
	var submissions atomic.Int32
	upstream := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		submissions.Add(1)
		w.WriteHeader(http.StatusAccepted)
	}))
	t.Cleanup(upstream.Close)
	adapter, err := integrationclient.NewExternalInteractionDeliveryAdapter(
		integrationclient.ExternalInteractionDeliveryConfig{
			BaseURL:     upstream.URL,
			Credentials: fixedServiceCredential("service-token"),
			Environment: "gamma",
			Timeout:     time.Second,
		},
		upstream.Client(),
		&staticDestinationLister{},
	)
	if err != nil {
		t.Fatalf("construct integration delivery adapter: %v", err)
	}
	sequence, err := adapter.Deliver(
		context.Background(),
		chatPushOutboxRecord(),
		"user-contract-001",
	)
	if err != nil || sequence <= 0 {
		t.Fatalf("no-endpoint recipient must complete as noop: sequence=%d err=%v", sequence, err)
	}
	if submissions.Load() != 0 {
		t.Fatalf("no-endpoint recipient must not submit external requests, got %d", submissions.Load())
	}
}

func TestIntegrationDeliveryAdapterRejectsIncompleteAlertPayload(t *testing.T) {
	adapter, err := integrationclient.NewExternalInteractionDeliveryAdapter(
		integrationclient.ExternalInteractionDeliveryConfig{
			BaseURL:     "https://integration.example.invalid",
			Credentials: fixedServiceCredential("service-token"),
			Environment: "gamma",
			Timeout:     time.Second,
		},
		http.DefaultClient,
		&staticDestinationLister{},
	)
	if err != nil {
		t.Fatalf("construct integration delivery adapter: %v", err)
	}
	record := chatPushOutboxRecord()
	delete(record.Payload, "title")
	_, err = adapter.Deliver(context.Background(), record, "user-contract-001")
	var deliveryErr *integrationclient.DeliveryError
	if !errors.As(err, &deliveryErr) ||
		deliveryErr.RecoveryAction != failures.RecoveryActionSurface {
		t.Fatalf("incomplete alert record must surface structured failure, got %v", err)
	}
}

func TestIntegrationDeliveryAdapterPreservesStructuredRemoteFailure(t *testing.T) {
	upstream := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusServiceUnavailable)
		_ = json.NewEncoder(w).Encode(map[string]any{
			"code":      "INTEGRATION.MIDDLEWARE.provider_rejected",
			"requestId": "integration-503",
			"traceId":   "trace-503",
			"recovery": map[string]any{
				"action": "surface",
			},
		})
	}))
	t.Cleanup(upstream.Close)
	adapter, err := integrationclient.NewExternalInteractionDeliveryAdapter(
		integrationclient.ExternalInteractionDeliveryConfig{
			BaseURL:     upstream.URL,
			Credentials: fixedServiceCredential("service-token"),
			Environment: "gamma",
			Timeout:     time.Second,
		},
		upstream.Client(),
		&staticDestinationLister{
			destinations: []notification.PushDestinationRef{
				{DeviceID: "device-1", EndpointRef: strings.Repeat("a", 64)},
			},
		},
	)
	if err != nil {
		t.Fatalf("construct integration delivery adapter: %v", err)
	}
	record := chatPushOutboxRecord()
	record.NotificationID = "notification-contract-503"
	_, err = adapter.Deliver(context.Background(), record, "user-contract-503")
	if err == nil {
		t.Fatal("expected structured integration failure")
	}
	var deliveryErr *integrationclient.DeliveryError
	if !errors.As(err, &deliveryErr) {
		t.Fatalf("expected DeliveryError, got %T: %v", err, err)
	}
	if deliveryErr.Code != "INTEGRATION.MIDDLEWARE.provider_rejected" ||
		deliveryErr.RecoveryAction != failures.RecoveryActionSurface ||
		deliveryErr.RequestID != "integration-503" ||
		deliveryErr.TraceID != "trace-503" {
		t.Fatalf("unexpected delivery failure: %+v", deliveryErr)
	}
}

func TestIntegrationDeliveryAdapterFailsClosedWithoutServiceCredentials(t *testing.T) {
	_, err := integrationclient.NewExternalInteractionDeliveryAdapter(
		integrationclient.ExternalInteractionDeliveryConfig{
			BaseURL:     "https://integration.example.invalid",
			Environment: "prod",
			Timeout:     time.Second,
		},
		http.DefaultClient,
		&staticDestinationLister{},
	)
	if err == nil {
		t.Fatal("missing integration service credentials must fail closed")
	}
	_, err = integrationclient.NewExternalInteractionDeliveryAdapter(
		integrationclient.ExternalInteractionDeliveryConfig{
			BaseURL:     "https://integration.example.invalid",
			Credentials: fixedServiceCredential("service-token"),
			Environment: "prod",
			Timeout:     time.Second,
		},
		http.DefaultClient,
		nil,
	)
	if err == nil {
		t.Fatal("missing push destination lister must fail closed")
	}
}

func TestIncomingCallIntegrationPayloadAndAcceptedSemantics(t *testing.T) {
	var captured map[string]any
	upstream := httptest.NewServer(http.HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			if err := json.NewDecoder(r.Body).Decode(&captured); err != nil {
				http.Error(w, err.Error(), http.StatusBadRequest)
				return
			}
			w.WriteHeader(http.StatusAccepted)
			_ = json.NewEncoder(w).Encode(map[string]any{
				"requestId":  captured["requestId"],
				"status":     reliabletask.ExternalInteractionStatusAccepted,
				"acceptedAt": time.Now().UTC().Format(time.RFC3339),
			})
		},
	))
	t.Cleanup(upstream.Close)
	adapter, err := integrationclient.NewExternalInteractionDeliveryAdapter(
		integrationclient.ExternalInteractionDeliveryConfig{
			BaseURL:     upstream.URL,
			Credentials: fixedServiceCredential("service-token"),
			Environment: "gamma",
			Timeout:     time.Second,
		},
		http.DefaultClient,
		&staticDestinationLister{},
	)
	if err != nil {
		t.Fatal(err)
	}
	now := time.Now().UTC()
	deliveryKey := canonicalFixtureDigest("incoming-job-1", "persona-target-1")
	job := notification.IncomingCallDeliveryJob{
		ID:              "incoming-job-1",
		CallID:          "76c0ee4a-1540-44fd-a291-c5593ac3d95d",
		TargetPersonaID: "persona-target-1",
		DestinationRef:  strings.Repeat("c", 64),
		DeliveryKey:     deliveryKey,
		CallType:        "video",
		CallerName:      "caller",
		CallerAvatarURL: "https://cdn.example.invalid/avatar.png",
		SourceLabel:     "conversation:conversation-1",
		TrustRelation:   "known",
		ExpiresAt:       now.Add(30 * time.Second),
		CreatedAt:       now,
	}
	externalID, err := adapter.SubmitIncomingCall(
		context.Background(),
		job,
	)
	if err != nil || externalID == "" {
		t.Fatalf("submit incoming call externalID=%q err=%v", externalID, err)
	}
	payload, ok := captured["payload"].(map[string]any)
	if !ok {
		t.Fatalf("incoming call payload=%v", captured)
	}
	for _, field := range []string{
		"action",
		"endpointRef",
		"deliveryKey",
		"callId",
		"targetPersonaId",
		"callType",
		"callerName",
		"sourceLabel",
		"trustRelation",
		"expiresAt",
		"occurredAt",
	} {
		if _, exists := payload[field]; !exists {
			t.Fatalf("incoming call payload misses %s: %v", field, payload)
		}
	}
	if payload["action"] != "ring" {
		t.Fatalf("incoming call action=%v", payload["action"])
	}
	ringRequestID, _ := captured["requestId"].(string)
	cancelledAt := now.Add(time.Second)
	job.CancellationEventID = "rtc-answer-1"
	job.CancellationOccurredAt = &cancelledAt
	cancellationID, err := adapter.SubmitIncomingCallCancellation(
		context.Background(),
		job,
	)
	if err != nil || cancellationID == "" || cancellationID == ringRequestID {
		t.Fatalf(
			"submit cancellation externalID=%q ringID=%q err=%v",
			cancellationID,
			ringRequestID,
			err,
		)
	}
	cancelPayload, _ := captured["payload"].(map[string]any)
	if cancelPayload["action"] != "cancel" ||
		cancelPayload["deliveryKey"] != job.DeliveryKey ||
		cancelPayload["occurredAt"] != cancelledAt.Format(time.RFC3339) {
		t.Fatalf("incoming cancellation payload=%v", cancelPayload)
	}
}
