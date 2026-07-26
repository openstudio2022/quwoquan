package local_contract

import (
	"context"
	"testing"
	"time"

	"quwoquan_service/runtime/otpseal"
	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/services/integration-service/internal/external_integration/external_interaction/application"
)

type contractProvider struct {
	name string
}

func (p contractProvider) Send(
	_ context.Context,
	request reliabletask.ExternalInteractionRequest,
	_ reliabletask.ReliableAsyncTask,
) (reliabletask.ExternalInteractionResult, error) {
	return reliabletask.ExternalInteractionResult{
		RequestID:         request.RequestID,
		Operation:         request.Operation,
		Status:            reliabletask.ExternalInteractionStatusDelivered,
		Provider:          p.name,
		ProviderRequestID: "contract-request",
		OccurredAt:        time.Now().UTC(),
	}, nil
}

type contractCallback struct{}

type contractOTPReferenceStore struct{}

func (contractOTPReferenceStore) Put(context.Context, otpseal.StoredReference) error { return nil }
func (contractOTPReferenceStore) Get(context.Context, string, string) (otpseal.StoredReference, error) {
	return otpseal.StoredReference{}, otpseal.ErrReferenceNotFound
}
func (contractOTPReferenceStore) Delete(context.Context, string, string) error { return nil }

func (contractCallback) SendExternalInteractionResult(
	context.Context,
	reliabletask.ExternalInteractionResult,
) error {
	return nil
}

func TestExternalInteractionConstructorRequiresExplicitDependencies(t *testing.T) {
	policies := map[string]reliabletask.ProviderPolicy{
		reliabletask.ExternalInteractionOperationSmsOTP: {
			Providers:   []string{"test_sms"},
			Timeout:     time.Second,
			RetryPolicy: reliabletask.DefaultRetryPolicy(),
		},
	}
	providers := map[string]reliabletask.ExternalProvider{
		"test_sms": contractProvider{name: "test_sms"},
	}
	if _, err := application.NewExternalInteractionService(
		nil,
		providers,
		policies,
		contractCallback{},
	); err == nil {
		t.Fatal("nil store must be rejected")
	}
	var typedNilStore *reliabletask.MemoryStore
	if _, err := application.NewExternalInteractionService(
		typedNilStore,
		providers,
		policies,
		contractCallback{},
	); err == nil {
		t.Fatal("typed nil store must be rejected")
	}
	store := reliabletask.NewMemoryStore()
	if _, err := application.NewExternalInteractionService(
		store,
		providers,
		policies,
		nil,
	); err == nil {
		t.Fatal("nil callback sender must be rejected")
	}
	service, err := application.NewExternalInteractionService(
		store,
		providers,
		policies,
		contractCallback{},
		contractOTPReferenceStore{},
	)
	if err != nil {
		t.Fatalf("explicit test dependencies must be accepted: %v", err)
	}
	if service == nil {
		t.Fatal("constructor returned nil service")
	}
}

func TestExternalInteractionConstructorRejectsMockProviderPolicy(t *testing.T) {
	store := reliabletask.NewMemoryStore()
	_, err := application.NewExternalInteractionService(
		store,
		map[string]reliabletask.ExternalProvider{
			"mock_sms": contractProvider{name: "mock_sms"},
		},
		map[string]reliabletask.ProviderPolicy{
			reliabletask.ExternalInteractionOperationSmsOTP: {
				Providers:   []string{"mock_sms"},
				Timeout:     time.Second,
				RetryPolicy: reliabletask.DefaultRetryPolicy(),
			},
		},
		contractCallback{},
	)
	if err == nil {
		t.Fatal("mock provider policy must be rejected")
	}
}
