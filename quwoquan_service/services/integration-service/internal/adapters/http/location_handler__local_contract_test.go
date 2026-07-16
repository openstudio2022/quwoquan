package httpadapter

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"quwoquan_service/runtime/otpseal"
	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/services/integration-service/internal/application"
	"quwoquan_service/services/integration-service/internal/domain/location/model"
	"quwoquan_service/services/integration-service/internal/generated"
)

type fakeProviderClient struct {
	name     model.Provider
	nearbyFn func(model.NearbyQuery) ([]model.POI, error)
	searchFn func(model.SearchQuery) ([]model.POI, error)
}

func (f *fakeProviderClient) Name() model.Provider { return f.name }

func (f *fakeProviderClient) Nearby(_ context.Context, q model.NearbyQuery) ([]model.POI, error) {
	return f.nearbyFn(q)
}

func (f *fakeProviderClient) Search(_ context.Context, q model.SearchQuery) ([]model.POI, error) {
	return f.searchFn(q)
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
		Status:            reliabletask.ExternalInteractionStatusDelivered,
		Provider:          "test_sms",
		ProviderRequestID: "test-provider-" + request.RequestID,
		OccurredAt:        time.Now().UTC(),
	}, nil
}

type testCallbackSender struct{}

type testOTPReferenceStore struct{}

func (testOTPReferenceStore) Put(context.Context, otpseal.StoredReference) error { return nil }
func (testOTPReferenceStore) Get(context.Context, string, string) (otpseal.StoredReference, error) {
	return otpseal.StoredReference{}, otpseal.ErrReferenceNotFound
}
func (testOTPReferenceStore) Delete(context.Context, string, string) error { return nil }

func (testCallbackSender) SendExternalInteractionResult(
	context.Context,
	reliabletask.ExternalInteractionResult,
) error {
	return nil
}

func TestSubmitExternalInteractionReturnsAcceptedAndRecordsAttempt(t *testing.T) {
	store := reliabletask.NewMemoryStore()
	external, err := application.NewExternalInteractionService(
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
		testCallbackSender{},
		testOTPReferenceStore{},
	)
	if err != nil {
		t.Fatalf("construct external interaction service: %v", err)
	}
	svc := application.NewService(
		model.ProviderBaidu,
		model.ProviderAMap,
		map[model.Provider]model.ProviderClient{},
		nil,
	)
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
	req := httptest.NewRequest(http.MethodPost, externalRequestsPath, bytes.NewReader(body))
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
	svc := application.NewService(
		model.ProviderBaidu,
		model.ProviderAMap,
		map[model.Provider]model.ProviderClient{
			model.ProviderBaidu: &fakeProviderClient{
				name: model.ProviderBaidu,
				nearbyFn: func(q model.NearbyQuery) ([]model.POI, error) {
					got = q
					return []model.POI{{Name: "x", Latitude: q.Lat, Longitude: q.Lng}}, nil
				},
				searchFn: func(model.SearchQuery) ([]model.POI, error) {
					return nil, nil
				},
			},
		},
		nil,
	)

	handler := NewHandler(svc, 3000, 20, 20, 30.1, 104.2).Routes()
	req := httptest.NewRequest(http.MethodGet, generated.NearbyPath+"?"+generated.QueryParamLimit+"=1", nil)
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
	svc := application.NewService(
		model.ProviderBaidu,
		model.ProviderAMap,
		map[model.Provider]model.ProviderClient{},
		nil,
	)
	handler := NewHandler(svc, 3000, 20, 20, 30.1, 104.2).Routes()
	req := httptest.NewRequest(http.MethodGet, generated.SearchPath, nil)
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("status=%d, want=400 body=%s", rr.Code, rr.Body.String())
	}
	var body map[string]any
	_ = json.Unmarshal(rr.Body.Bytes(), &body)
	if body["code"] != generated.ErrInvalidArgument.Error() {
		t.Fatalf("code=%v, want %s", body["code"], generated.ErrInvalidArgument.Error())
	}
}

func TestNearbyBothProvidersFailReturns500WithIntegrationErrorCode(t *testing.T) {
	fail := &fakeProviderClient{
		name: model.ProviderBaidu,
		nearbyFn: func(model.NearbyQuery) ([]model.POI, error) {
			return nil, errors.New("down")
		},
		searchFn: func(model.SearchQuery) ([]model.POI, error) {
			return nil, nil
		},
	}
	backup := &fakeProviderClient{
		name: model.ProviderAMap,
		nearbyFn: func(model.NearbyQuery) ([]model.POI, error) {
			return nil, errors.New("down2")
		},
		searchFn: func(model.SearchQuery) ([]model.POI, error) {
			return nil, nil
		},
	}
	svc := application.NewService(
		model.ProviderBaidu,
		model.ProviderAMap,
		map[model.Provider]model.ProviderClient{
			model.ProviderBaidu: fail,
			model.ProviderAMap:  backup,
		},
		nil,
	)
	handler := NewHandler(svc, 3000, 20, 20, 30.1, 104.2).Routes()
	req := httptest.NewRequest(http.MethodGet, generated.NearbyPath, nil)
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)
	if rr.Code != http.StatusInternalServerError {
		t.Fatalf("status=%d, want=500 body=%s", rr.Code, rr.Body.String())
	}
	var body map[string]any
	_ = json.Unmarshal(rr.Body.Bytes(), &body)
	if body["code"] != generated.ErrInternalError.Error() {
		t.Fatalf("code=%v, want %s", body["code"], generated.ErrInternalError.Error())
	}
}

func TestNearbyNoProvidersReturns400WithLocationUnavailableCode(t *testing.T) {
	svc := application.NewService(
		model.ProviderBaidu,
		model.ProviderAMap,
		map[model.Provider]model.ProviderClient{},
		nil,
	)
	handler := NewHandler(svc, 3000, 20, 20, 30.1, 104.2).Routes()
	req := httptest.NewRequest(http.MethodGet, generated.NearbyPath, nil)
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)
	if rr.Code != http.StatusBadRequest {
		t.Fatalf("status=%d, want=400 body=%s", rr.Code, rr.Body.String())
	}
	var body map[string]any
	_ = json.Unmarshal(rr.Body.Bytes(), &body)
	if body["code"] != generated.ErrLocationUnavailable.Error() {
		t.Fatalf("code=%v, want %s", body["code"], generated.ErrLocationUnavailable.Error())
	}
}

func TestNearbyTimeoutReturns504WithUpstreamTimeoutCode(t *testing.T) {
	timeoutClient := &fakeProviderClient{
		name: model.ProviderBaidu,
		nearbyFn: func(model.NearbyQuery) ([]model.POI, error) {
			return nil, context.DeadlineExceeded
		},
		searchFn: func(model.SearchQuery) ([]model.POI, error) { return nil, nil },
	}
	svc := application.NewService(
		model.ProviderBaidu,
		model.ProviderAMap,
		map[model.Provider]model.ProviderClient{model.ProviderBaidu: timeoutClient},
		nil,
	)
	handler := NewHandler(svc, 3000, 20, 20, 30.1, 104.2).Routes()
	req := httptest.NewRequest(http.MethodGet, generated.NearbyPath, nil)
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)
	if rr.Code != http.StatusGatewayTimeout {
		t.Fatalf("status=%d, want=504 body=%s", rr.Code, rr.Body.String())
	}
	var body map[string]any
	_ = json.Unmarshal(rr.Body.Bytes(), &body)
	if body["code"] != generated.ErrUpstreamTimeout.Error() {
		t.Fatalf("code=%v, want %s", body["code"], generated.ErrUpstreamTimeout.Error())
	}
}
