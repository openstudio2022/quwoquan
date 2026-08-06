// spec_ref: specs/feature-tree/runtime/runtime-external-integration/integration-service-foundation/spec.md#gwt-001
// readiness_case: invoke-push-delivery-provider-api
package api_integration

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/internal/platform/reliabletaskmongo"
	"quwoquan_service/runtime/reliabletask"
	externalapp "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/application"
	attemptadapter "quwoquan_service/services/integration-service/internal/external_integration/external_interaction_attempt_fact/adapters/inbound/runtime"
	deadletteradapter "quwoquan_service/services/integration-service/internal/external_integration/external_interaction_dead_letter_fact/adapters/inbound/runtime"
	deadletterpersistence "quwoquan_service/services/integration-service/internal/external_integration/external_interaction_dead_letter_fact/infrastructure/persistence"
	"quwoquan_service/services/integration-service/internal/external_integration/push_delivery/application"
	pushprovider "quwoquan_service/services/integration-service/internal/external_integration/push_delivery/infrastructure/provider"
	integrationsupport "quwoquan_service/services/integration-service/tests/support"
)

const apiIntegrationEndpointRef = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

func TestPushDeliveryWorkerDispatchesIdempotentlyExactlyOnce(t *testing.T) {
	integrationsupport.WithIntegrationMongo(t, func(runtime *integrationsupport.MongoRuntime) {
		runtime.ResetExternalInteraction(t)
		var providerCalls atomic.Int32
		providerServer := httptest.NewTLSServer(http.HandlerFunc(func(
			writer http.ResponseWriter,
			request *http.Request,
		) {
			providerCalls.Add(1)
			if request.Method != http.MethodPost {
				t.Errorf("provider method=%s, want POST", request.Method)
			}
			var payload map[string]string
			if err := json.NewDecoder(request.Body).Decode(&payload); err != nil {
				t.Errorf("decode provider request: %v", err)
			}
			if payload["requestId"] != "push-api-request-001" ||
				payload["operation"] != reliabletask.ExternalInteractionOperationPush ||
				payload["idempotencyKey"] != "delivery-api-001" ||
				payload["payloadDigest"] != integrationsupport.CanonicalTestSHA256("push:delivery-api-001") {
				t.Errorf("non-canonical provider request: %+v", payload)
			}
			writer.Header().Set("Content-Type", "application/json")
			writer.WriteHeader(http.StatusAccepted)
			_ = json.NewEncoder(writer).Encode(map[string]string{
				"providerRequestId": "push-substitute-api-001",
			})
		}))
		t.Cleanup(providerServer.Close)
		remoteProvider, err := pushprovider.NewProtocolSubstitutePushProvider(
			providerServer.URL,
			providerServer.Client(),
			2*time.Second,
		)
		if err != nil {
			t.Fatal(err)
		}
		policies := map[string]reliabletask.ProviderPolicy{
			reliabletask.ExternalInteractionOperationPush: {
				Providers:   []string{pushprovider.ProtocolSubstituteProviderName},
				Timeout:     2 * time.Second,
				RetryPolicy: reliabletask.DefaultRetryPolicy(),
			},
		}
		service, err := externalapp.NewExternalInteractionService(
			runtime.CanonicalExternalStore(t),
			map[string]reliabletask.ExternalProvider{
				pushprovider.ProtocolSubstituteProviderName: remoteProvider,
			},
			policies,
		)
		if err != nil {
			t.Fatal(err)
		}
		expiresAt := time.Now().UTC().Add(5 * time.Minute).Truncate(time.Second)
		request := reliabletask.ExternalInteractionRequest{
			RequestID:      "push-api-request-001",
			Operation:      reliabletask.ExternalInteractionOperationPush,
			Tenant:         "quwoquan",
			Env:            "gamma",
			IdempotencyKey: "delivery-api-001",
			PayloadRef:     "push:delivery-api-001",
			PayloadDigest:  integrationsupport.CanonicalTestSHA256("push:delivery-api-001"),
			Sensitivity:    "private",
			ExpiresAt:      expiresAt,
			Payload: map[string]string{
				"action":          application.PushDeliveryActionRing,
				"endpointRef":     apiIntegrationEndpointRef,
				"deliveryKey":     "delivery-api-001",
				"callId":          "call-api-001",
				"targetPersonaId": "persona-api-001",
				"callType":        "video",
				"callerName":      "接口集成来电",
				"sourceLabel":     "接口集成会话",
				"trustRelation":   "possibly_unknown",
				"expiresAt":       expiresAt.Format(time.RFC3339),
				"occurredAt":      time.Now().UTC().Add(-time.Second).Format(time.RFC3339),
			},
		}
		for index := 0; index < 2; index++ {
			accepted, submitErr := service.Submit(context.Background(), request)
			if submitErr != nil {
				t.Fatalf("submit duplicate %d: %v", index, submitErr)
			}
			if accepted.RequestID != request.RequestID {
				t.Fatalf("unexpected accepted response: %+v", accepted)
			}
		}
		outboxCount, err := runtime.Database.Collection("reliable_task_outbox").CountDocuments(
			context.Background(),
			bson.M{"idempotencyKey": request.IdempotencyKey},
		)
		if err != nil || outboxCount != 1 {
			t.Fatalf("idempotent outbox count=%d err=%v", outboxCount, err)
		}
		var outbox bson.M
		if err := runtime.Database.Collection("reliable_task_outbox").FindOne(
			context.Background(),
			bson.M{"idempotencyKey": request.IdempotencyKey},
		).Decode(&outbox); err != nil {
			t.Fatal(err)
		}
		if strings.Contains(fmt.Sprint(outbox), "api-integration-transient-token") ||
			strings.Contains(fmt.Sprint(outbox), "\"token\"") {
			t.Fatalf("outbox leaked endpoint token: %+v", outbox)
		}

		reopenedStore := reliabletaskmongo.NewExternalInteraction(runtime.Database)
		reopened, err := externalapp.NewExternalInteractionService(
			deadletteradapter.NewRuntimeStore(
				attemptadapter.NewRuntimeStore(reopenedStore),
				deadletterpersistence.NewMongoRepository(runtime.Database),
			),
			map[string]reliabletask.ExternalProvider{
				pushprovider.ProtocolSubstituteProviderName: remoteProvider,
			},
			policies,
		)
		if err != nil {
			t.Fatal(err)
		}
		if err := reopened.DispatchDue(context.Background(), 10); err != nil {
			t.Fatal(err)
		}
		processed, err := reopened.ProcessOne(context.Background())
		if err != nil || !processed {
			t.Fatalf("first worker process processed=%t err=%v", processed, err)
		}
		processed, err = reopened.ProcessOne(context.Background())
		if err != nil || processed {
			t.Fatalf("second worker process must be empty processed=%t err=%v", processed, err)
		}
		if providerCalls.Load() != 1 {
			t.Fatalf("HTTPS provider calls=%d, want exactly one", providerCalls.Load())
		}
		attempts, err := reopened.ListAttempts(context.Background(), request.RequestID)
		if err != nil || len(attempts) != 1 {
			t.Fatalf("attempt ledger=%+v err=%v", attempts, err)
		}
		if attempts[0].Provider != pushprovider.ProtocolSubstituteProviderName ||
			attempts[0].Status != reliabletask.ExternalInteractionStatusSentUnconfirmed {
			t.Fatalf("unexpected attempt: %+v", attempts[0])
		}
		var attemptDocument bson.M
		if err := runtime.Database.Collection("external_provider_attempt_ledger").FindOne(
			context.Background(),
			bson.M{"requestId": request.RequestID},
		).Decode(&attemptDocument); err != nil {
			t.Fatal(err)
		}
		if strings.Contains(fmt.Sprint(attemptDocument), "api-integration-transient-token") {
			t.Fatalf("attempt ledger leaked endpoint token: %+v", attemptDocument)
		}
		var resultOutbox bson.M
		if err := runtime.Database.Collection(
			"external_interaction_result_outbox",
		).FindOne(
			context.Background(),
			bson.M{"_id": attempts[0].AttemptID},
		).Decode(&resultOutbox); err != nil {
			t.Fatalf("provider attempt must commit a result outbox row: %v", err)
		}
		if resultOutbox["deliveryStatus"] !=
			reliabletask.ExternalInteractionResultOutboxPending ||
			resultOutbox["providerRequestDigest"] == "" {
			t.Fatalf("invalid provider result outbox: %+v", resultOutbox)
		}
		for _, forbidden := range []string{
			"providerRequestId",
			"api-integration-transient-token",
			"endpointRef",
		} {
			if strings.Contains(fmt.Sprint(resultOutbox), forbidden) {
				t.Fatalf(
					"provider result outbox leaked %s: %+v",
					forbidden,
					resultOutbox,
				)
			}
		}
		taskCount, err := runtime.Database.Collection("reliable_async_task").CountDocuments(
			context.Background(),
			bson.M{
				"aggregateId": request.RequestID,
				"status":      reliabletask.TaskStatusSucceeded,
			},
		)
		if err != nil || taskCount != 1 {
			t.Fatalf("completed task count=%d err=%v", taskCount, err)
		}
	})
}
