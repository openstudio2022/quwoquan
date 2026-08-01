package local_contract

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	. "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/adapters/inbound/http"
	"testing"
	"time"

	"quwoquan_service/runtime/otpseal"
	"quwoquan_service/runtime/reliabletask"
	externalgenerated "quwoquan_service/services/integration-service/generated/external_integration/external_interaction"
	locationgenerated "quwoquan_service/services/integration-service/generated/external_integration/location"
	externalapplication "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/application"
	locationapplication "quwoquan_service/services/integration-service/internal/external_integration/location/application"
	"quwoquan_service/services/integration-service/internal/external_integration/location/domain/model"
)

type fakeProviderClient struct {
	nearbyFn func(model.NearbyQuery) ([]model.POI, error)
	searchFn func(model.SearchRequestFact) ([]model.POI, error)
}

func (f *fakeProviderClient) Nearby(_ context.Context, q model.NearbyQuery) ([]model.POI, error) {
	return f.nearbyFn(q)
}

func (f *fakeProviderClient) Search(_ context.Context, q model.SearchRequestFact) ([]model.POI, error) {
	return f.searchFn(q)
}

func newLocationService(t *testing.T, provider *fakeProviderClient) *locationapplication.Service {
	t.Helper()
	service, err := locationapplication.NewService(provider)
	if err != nil {
		t.Fatalf("construct location service: %v", err)
	}
	return service
}

type testExternalProvider struct{}

func (testExternalProvider) Send(
	_ context.Context,
	request reliabletask.ExternalInteractionRequest,
	_ reliabletask.ReliableAsyncTask,
) (reliabletask.ExternalInteractionResult, error) {
	return reliabletask.ExternalInteractionResult{
		RequestID:         request.RequestID,
		Operation:         request.Operation,
		Status:            reliabletask.ExternalInteractionStatusSentUnconfirmed,
		Provider:          "test_sms",
		ProviderRequestID: "test-provider-" + request.RequestID,
		OccurredAt:        time.Now().UTC(),
	}, nil
}

type testOTPReferenceStore struct{}

func (testOTPReferenceStore) Put(context.Context, otpseal.StoredReference) error { return nil }
func (testOTPReferenceStore) Get(context.Context, string, string) (otpseal.StoredReference, error) {
	return otpseal.StoredReference{}, otpseal.ErrReferenceNotFound
}
func (testOTPReferenceStore) Delete(context.Context, string, string) error { return nil }

func TestSubmitExternalInteractionReturnsAcceptedAndRecordsAttempt(t *testing.T) {
	store := reliabletask.NewMemoryStore()
	external, err := externalapplication.NewExternalInteractionService(
		store,
		map[string]reliabletask.ExternalProvider{
			"test_sms": testExternalProvider{},
		},
		map[string]reliabletask.ProviderPolicy{
			reliabletask.ExternalInteractionOperationSmsOTP: {
				Providers:   []string{"test_sms"},
				Timeout:     time.Second,
				RetryPolicy: reliabletask.DefaultRetryPolicy(),
			},
		},
		testOTPReferenceStore{},
	)
	if err != nil {
		t.Fatalf("construct external interaction service: %v", err)
	}
	svc := newLocationService(t, &fakeProviderClient{
		nearbyFn: func(model.NearbyQuery) ([]model.POI, error) { return nil, nil },
		searchFn: func(model.SearchRequestFact) ([]model.POI, error) { return nil, nil },
	})
	handler := NewHandler(svc, 3000, 20, 20, 30.1, 104.2, external).Routes()
	body := []byte(`{
		"requestId":"req-sms-1",
		"operation":"sms_otp.send",
		"tenant":"quwoquan",
		"env":"gamma",
		"idempotencyKey":"otp:fixture",
		"payloadRef":"otp_challenge:ch-1",
		"payloadDigest":"digest",
		"sensitivity":"secret",
		"expiresAt":"2030-01-01T00:00:00Z",
		"payload":{"challengeId":"ch-1","codeRef":"otpref.test","phoneHash":"hash","maskedRecipient":"180****3909"}
	}`)
	req := httptest.NewRequest(http.MethodPost, externalgenerated.ExternalRequestsPath, bytes.NewReader(body))
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)
	if rr.Code != http.StatusAccepted {
		t.Fatalf("status=%d, want=202 body=%s", rr.Code, rr.Body.String())
	}
	if err := external.DispatchDue(context.Background(), 10); err != nil {
		t.Fatalf("dispatch due: %v", err)
	}
	processed, err := external.ProcessOne(context.Background())
	if err != nil {
		t.Fatalf("process one: %v", err)
	}
	if !processed {
		t.Fatal("expected external worker to process one task")
	}
	attempts, err := store.ListProviderAttempts(context.Background(), "req-sms-1")
	if err != nil {
		t.Fatalf("list attempts: %v", err)
	}
	if len(attempts) != 1 || attempts[0].Provider != "test_sms" {
		t.Fatalf("unexpected attempts: %#v", attempts)
	}
}

func TestNearbyUsesDefaultCenterWhenLatLngMissing(t *testing.T) {
	var got model.NearbyQuery
	svc := newLocationService(t, &fakeProviderClient{
		nearbyFn: func(q model.NearbyQuery) ([]model.POI, error) {
			got = q
			return []model.POI{{Name: "x", Latitude: q.Lat, Longitude: q.Lng}}, nil
		},
		searchFn: func(model.SearchRequestFact) ([]model.POI, error) {
			return nil, nil
		},
	})

	handler := NewHandler(svc, 3000, 20, 20, 30.1, 104.2).Routes()
	req := httptest.NewRequest(http.MethodGet, locationgenerated.NearbyPath+"?"+locationgenerated.QueryParamLimit+"=1", nil)
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)

	if rr.Code != http.StatusOK {
		t.Fatalf("status=%d, want=200 body=%s", rr.Code, rr.Body.String())
	}
	if got.Lat != 30.1 || got.Lng != 104.2 {
		t.Fatalf("lat/lng not fallback, got=(%f,%f)", got.Lat, got.Lng)
	}
}

func TestSearchEmptyQueryReturnsBadRequest(t *testing.T) {
	svc := newLocationService(t, &fakeProviderClient{
		nearbyFn: func(model.NearbyQuery) ([]model.POI, error) { return nil, nil },
		searchFn: func(model.SearchRequestFact) ([]model.POI, error) { return nil, nil },
	})
	handler := NewHandler(svc, 3000, 20, 20, 30.1, 104.2).Routes()
	req := httptest.NewRequest(http.MethodGet, locationgenerated.SearchPath, nil)
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("status=%d, want=400 body=%s", rr.Code, rr.Body.String())
	}
	var body map[string]any
	_ = json.Unmarshal(rr.Body.Bytes(), &body)
	if body["code"] != locationgenerated.ErrInvalidArgument.Error() {
		t.Fatalf("code=%v, want %s", body["code"], locationgenerated.ErrInvalidArgument.Error())
	}
}

func TestNearbyProviderFailureReturnsStructuredUnavailableError(t *testing.T) {
	fail := &fakeProviderClient{
		nearbyFn: func(model.NearbyQuery) ([]model.POI, error) {
			return nil, locationgenerated.AppErrorFromLocationProviderUnavailable(
				"location provider request failed",
			)
		},
		searchFn: func(model.SearchRequestFact) ([]model.POI, error) {
			return nil, nil
		},
	}
	svc := newLocationService(t, fail)
	handler := NewHandler(svc, 3000, 20, 20, 30.1, 104.2).Routes()
	req := httptest.NewRequest(http.MethodGet, locationgenerated.NearbyPath, nil)
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)
	if rr.Code != http.StatusServiceUnavailable {
		t.Fatalf("status=%d, want=503 body=%s", rr.Code, rr.Body.String())
	}
	var body map[string]any
	_ = json.Unmarshal(rr.Body.Bytes(), &body)
	if body["code"] != locationgenerated.ErrLocationProviderUnavailable.Error() {
		t.Fatalf("code=%v, want %s", body["code"], locationgenerated.ErrLocationProviderUnavailable.Error())
	}
}

func TestNearbyTimeoutReturns504WithUpstreamTimeoutCode(t *testing.T) {
	timeoutClient := &fakeProviderClient{
		nearbyFn: func(model.NearbyQuery) ([]model.POI, error) {
			return nil, locationgenerated.AppErrorFromUpstreamTimeout(
				"location provider request timed out",
			)
		},
		searchFn: func(model.SearchRequestFact) ([]model.POI, error) { return nil, nil },
	}
	svc := newLocationService(t, timeoutClient)
	handler := NewHandler(svc, 3000, 20, 20, 30.1, 104.2).Routes()
	req := httptest.NewRequest(http.MethodGet, locationgenerated.NearbyPath, nil)
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)
	if rr.Code != http.StatusGatewayTimeout {
		t.Fatalf("status=%d, want=504 body=%s", rr.Code, rr.Body.String())
	}
	var body map[string]any
	_ = json.Unmarshal(rr.Body.Bytes(), &body)
	if body["code"] != locationgenerated.ErrUpstreamTimeout.Error() {
		t.Fatalf("code=%v, want %s", body["code"], locationgenerated.ErrUpstreamTimeout.Error())
	}
}
