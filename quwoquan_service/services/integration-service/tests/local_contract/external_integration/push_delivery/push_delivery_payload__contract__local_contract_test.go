package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	rerrors "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/reliabletask"
	externalgenerated "quwoquan_service/services/integration-service/generated/external_integration/external_interaction"
	externalapp "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/application"
	pushapp "quwoquan_service/services/integration-service/internal/external_integration/push_delivery/application"
	integrationsupport "quwoquan_service/services/integration-service/tests/support"
)

func TestPushDeliverySubmitRejectsInvalidTypedPayload(t *testing.T) {
	service, err := externalapp.NewExternalInteractionService(
		integrationsupport.NewMemoryExternalStore(reliabletask.NewMemoryStore()),
		map[string]reliabletask.ExternalProvider{
			"push_dispatch": pushapp.LocalRecorderPushProvider{},
		},
		map[string]reliabletask.ProviderPolicy{
			reliabletask.ExternalInteractionOperationPush: {
				Providers:   []string{"push_dispatch"},
				Timeout:     time.Second,
				RetryPolicy: reliabletask.DefaultRetryPolicy(),
			},
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	valid := pushRequest(time.Now().UTC().Add(2 * time.Minute).Truncate(time.Second))
	if _, err := service.Submit(context.Background(), valid); err != nil {
		t.Fatalf("valid push payload rejected: %v", err)
	}
	tests := []struct {
		name   string
		mutate func(*reliabletask.ExternalInteractionRequest)
	}{
		{
			name: "unknown_field",
			mutate: func(request *reliabletask.ExternalInteractionRequest) {
				request.Payload["deviceToken"] = "must-never-be-accepted"
			},
		},
		{
			name: "raw_token_as_endpoint_ref",
			mutate: func(request *reliabletask.ExternalInteractionRequest) {
				request.Payload["endpointRef"] = "raw-device-token-must-not-be-persisted"
			},
		},
		{
			name: "invalid_call_type",
			mutate: func(request *reliabletask.ExternalInteractionRequest) {
				request.Payload["callType"] = "screen"
			},
		},
		{
			name: "invalid_action",
			mutate: func(request *reliabletask.ExternalInteractionRequest) {
				request.Payload["action"] = "dismiss"
			},
		},
		{
			name: "invalid_occurred_at",
			mutate: func(request *reliabletask.ExternalInteractionRequest) {
				request.Payload["occurredAt"] = "not-a-timestamp"
			},
		},
		{
			name: "missing_target_persona",
			mutate: func(request *reliabletask.ExternalInteractionRequest) {
				delete(request.Payload, "targetPersonaId")
			},
		},
		{
			name: "invalid_trust_relation",
			mutate: func(request *reliabletask.ExternalInteractionRequest) {
				request.Payload["trustRelation"] = "trusted"
			},
		},
		{
			name: "mismatched_expiry",
			mutate: func(request *reliabletask.ExternalInteractionRequest) {
				request.Payload["expiresAt"] = request.ExpiresAt.Add(time.Second).Format(time.RFC3339)
			},
		},
	}
	for _, testCase := range tests {
		t.Run(testCase.name, func(t *testing.T) {
			request := valid
			request.RequestID = "push-request-" + testCase.name
			request.IdempotencyKey = "delivery-" + testCase.name
			request.Payload = reliabletask.CloneStringMap(valid.Payload)
			testCase.mutate(&request)
			_, submitErr := service.Submit(context.Background(), request)
			var appErr *rerrors.AppError
			if !errors.As(submitErr, &appErr) ||
				appErr.Code.String() != externalgenerated.ErrInvalidExternalRequest.Error() {
				t.Fatalf("expected object-local external interaction invalid error, got %T %v", submitErr, submitErr)
			}
		})
	}
}
