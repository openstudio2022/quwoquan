package reliabletask

import (
	"context"
	"testing"
	"time"
)

type testExternalProvider struct{}

func (testExternalProvider) Send(ctx context.Context, req ExternalInteractionRequest, task ReliableAsyncTask) (ExternalInteractionResult, error) {
	_ = ctx
	_ = task
	return ExternalInteractionResult{
		RequestID:         req.RequestID,
		Operation:         req.Operation,
		Status:            ExternalInteractionStatusDelivered,
		Provider:          "mock_sms",
		ProviderRequestID: "provider-req-1",
	}, nil
}

func TestExternalInteractionDispatcherWorkerRecordsProviderAttempt(t *testing.T) {
	ctx := context.Background()
	store := NewMemoryStore()
	dispatcher := ExternalInteractionDispatcher{
		Writer: NewTaskOutboxWriter(store),
	}
	accepted, err := dispatcher.Submit(ctx, ExternalInteractionRequest{
		RequestID:      "req-1",
		Operation:      ExternalInteractionOperationSmsOTP,
		Tenant:         "quwoquan",
		Env:            "gamma",
		IdempotencyKey: "otp:user:1",
		PayloadRef:     "otp_challenge:ch-1",
		PayloadDigest:  "digest",
		Sensitivity:    "secret",
		ExpiresAt:      time.Now().UTC().Add(time.Minute),
		Payload: map[string]string{
			"challengeId":     "ch-1",
			"phoneHash":       "phone-hash",
			"maskedRecipient": "180****3909",
		},
	})
	if err != nil {
		t.Fatalf("submit external interaction: %v", err)
	}
	if accepted.Status != ExternalInteractionStatusAccepted {
		t.Fatalf("accepted status = %s", accepted.Status)
	}
	if _, err := (Dispatcher{Store: store}).DispatchDue(ctx, 10); err != nil {
		t.Fatalf("dispatch due: %v", err)
	}
	worker := ExternalInteractionWorker{
		Worker: Worker{
			Store:     store,
			TaskTypes: []string{TaskTypeForExternalInteraction(ExternalInteractionOperationSmsOTP)},
			WorkerID:  "test-worker",
		},
		Providers: map[string]ExternalProvider{"mock_sms": testExternalProvider{}},
		Policies: map[string]ProviderPolicy{
			ExternalInteractionOperationSmsOTP: {Providers: []string{"mock_sms"}},
		},
		Ledger: store,
	}
	processed, err := worker.ProcessOne(ctx)
	if err != nil {
		t.Fatalf("process one: %v", err)
	}
	if !processed {
		t.Fatal("expected one external interaction task to be processed")
	}
	attempts, err := store.ListProviderAttempts(ctx, "req-1")
	if err != nil {
		t.Fatalf("list attempts: %v", err)
	}
	if len(attempts) != 1 {
		t.Fatalf("attempts len = %d", len(attempts))
	}
	if attempts[0].Provider != "mock_sms" || attempts[0].Status != ExternalInteractionStatusDelivered {
		t.Fatalf("unexpected attempt: %#v", attempts[0])
	}
}
