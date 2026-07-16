package local_contract

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"quwoquan_service/runtime/failures"
	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/services/notification-service/internal/application"
	integrationclient "quwoquan_service/services/notification-service/internal/infrastructure/integration"
)

type fixedServiceCredential string

func (c fixedServiceCredential) AuthorizationHeader(context.Context) (string, error) {
	return "Bearer " + string(c), nil
}

func TestIntegrationDeliveryAdapterReturnsTraceableAcceptedSequence(t *testing.T) {
	var acceptedRequestID string
	upstream := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/v1/integrations/external-requests" {
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
