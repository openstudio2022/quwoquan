// spec_ref: specs/feature-tree/runtime/runtime-external-integration/integration-service-foundation/spec.md#gwt-001
package api_integration

import (
	"context"
	"fmt"
	"log/slog"
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
	integrationsupport "quwoquan_service/services/integration-service/tests/support"
)

const apiIntegrationEndpointRef = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

type pushEndpointAccessSpy struct {
	resolutions   atomic.Int32
	invalidations atomic.Int32
}

func (s *pushEndpointAccessSpy) ResolvePushEndpointSecret(
	_ context.Context,
	endpointRef string,
) (application.PushEndpointSecret, error) {
	s.resolutions.Add(1)
	return application.PushEndpointSecret{
		EndpointRef:  endpointRef,
		EndpointKind: application.PushEndpointKindFCM,
		Token:        "api-integration-transient-token",
	}, nil
}

func (s *pushEndpointAccessSpy) InvalidatePushEndpoint(
	context.Context,
	string,
	string,
	string,
) error {
	s.invalidations.Add(1)
	return nil
}

type pushSenderSpy struct {
	calls atomic.Int32
}

func (s *pushSenderSpy) SendPush(
	_ context.Context,
	token string,
	message application.PushDeliveryMessage,
) (application.PushSendReceipt, error) {
	if token != "api-integration-transient-token" {
		return application.PushSendReceipt{}, fmt.Errorf("unexpected transient token")
	}
	if message.DeliveryKey != "delivery-api-001" || message.CallID != "call-api-001" {
		return application.PushSendReceipt{}, fmt.Errorf("unexpected push payload")
	}
	s.calls.Add(1)
	return application.PushSendReceipt{ProviderRequestID: "fcm-message-api-001"}, nil
}

func TestPushDeliveryWorkerDispatchesIdempotentlyExactlyOnce(t *testing.T) {
	integrationsupport.WithIntegrationMongo(t, func(runtime *integrationsupport.MongoRuntime) {
		runtime.ResetExternalInteraction(t)
		endpointAccess := &pushEndpointAccessSpy{}
		apns := &pushSenderSpy{}
		fcm := &pushSenderSpy{}
		dispatchProvider, err := application.NewPushDispatchProvider(
			endpointAccess,
			endpointAccess,
			apns,
			fcm,
			slog.Default(),
		)
		if err != nil {
			t.Fatal(err)
		}
		policies := map[string]reliabletask.ProviderPolicy{
			reliabletask.ExternalInteractionOperationPush: {
				Providers:   []string{"push_dispatch"},
				Timeout:     2 * time.Second,
				RetryPolicy: reliabletask.DefaultRetryPolicy(),
			},
		}
		service, err := externalapp.NewExternalInteractionService(
			runtime.CanonicalExternalStore(t),
			map[string]reliabletask.ExternalProvider{"push_dispatch": dispatchProvider},
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
			map[string]reliabletask.ExternalProvider{"push_dispatch": dispatchProvider},
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
		if fcm.calls.Load() != 1 ||
			apns.calls.Load() != 0 ||
			endpointAccess.resolutions.Load() != 1 ||
			endpointAccess.invalidations.Load() != 0 {
			t.Fatalf(
				"exactly-once calls fcm=%d apns=%d resolutions=%d invalidations=%d",
				fcm.calls.Load(),
				apns.calls.Load(),
				endpointAccess.resolutions.Load(),
				endpointAccess.invalidations.Load(),
			)
		}
		attempts, err := reopened.ListAttempts(context.Background(), request.RequestID)
		if err != nil || len(attempts) != 1 {
			t.Fatalf("attempt ledger=%+v err=%v", attempts, err)
		}
		if attempts[0].Provider != application.PushEndpointKindFCM ||
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
