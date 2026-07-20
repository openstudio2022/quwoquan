package local_contract

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"quwoquan_service/runtime/failures"
	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/services/notification-service/internal/application"
	notification "quwoquan_service/services/notification-service/internal/domain/notification"
	integrationclient "quwoquan_service/services/notification-service/internal/infrastructure/integration"
)

type fixedServiceCredential string

func (c fixedServiceCredential) AuthorizationHeader(context.Context) (string, error) {
	return "Bearer " + string(c), nil
}

func TestIntegrationDeliveryAdapterReturnsTraceableAcceptedSequence(t *testing.T) {
	var acceptedRequestID string
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
		acceptedRequestID, _ = request["requestId"].(string)
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusAccepted)
		_ = json.NewEncoder(w).Encode(map[string]any{
			"requestId":  acceptedRequestID,
			"status":     reliabletask.ExternalInteractionStatusAccepted,
			"acceptedAt": time.Now().UTC().Format(time.RFC3339),
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
	)
	if err != nil {
		t.Fatalf("construct integration delivery adapter: %v", err)
	}
	sequence, err := adapter.Deliver(
		context.Background(),
		reliabletask.NotificationOutboxRecord{
			NotificationID: "notification-contract-001",
			EventType:      application.NotificationPushRequestedEvent,
			AggregateType:  "message",
			AggregateID:    "message-contract-001",
			Payload: map[string]string{
				"providerHint": "vendor_push",
				"deeplink":     "quwoquan://chat/message-contract-001",
			},
		},
		"user-contract-001",
	)
	if err != nil {
		t.Fatalf("deliver notification through integration: %v", err)
	}
	if acceptedRequestID == "" || sequence <= 0 {
		t.Fatalf("delivery receipt is not traceable: requestId=%q sequence=%d", acceptedRequestID, sequence)
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
	)
	if err != nil {
		t.Fatalf("construct integration delivery adapter: %v", err)
	}
	_, err = adapter.Deliver(
		context.Background(),
		reliabletask.NotificationOutboxRecord{
			NotificationID: "notification-contract-503",
			EventType:      application.NotificationPushRequestedEvent,
		},
		"user-contract-503",
	)
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
	)
	if err == nil {
		t.Fatal("missing integration service credentials must fail closed")
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
	)
	if err != nil {
		t.Fatal(err)
	}
	now := time.Now().UTC()
	job := notification.IncomingCallDeliveryJob{
		ID:              "incoming-job-1",
		CallID:          "76c0ee4a-1540-44fd-a291-c5593ac3d95d",
		TargetPersonaID: "persona-target-1",
		DestinationRef:  strings.Repeat("c", 64),
		DeliveryKey:     "sha256:delivery-1",
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
