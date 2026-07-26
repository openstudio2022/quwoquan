package local_contract

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	. "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/infrastructure/provider"
	"strings"
	"testing"

	rerrors "quwoquan_service/runtime/errors"
	"quwoquan_service/services/integration-service/generated/external_integration/location"
	"quwoquan_service/services/integration-service/internal/external_integration/location/domain/model"
)

func TestBaiduClientMapsVendorFailureToStructuredRecovery(t *testing.T) {
	upstream := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		http.Error(w, "vendor diagnostic must not escape", http.StatusBadGateway)
	}))
	t.Cleanup(upstream.Close)

	client := NewBaiduClient(upstream.URL, "test-ak", upstream.Client())
	_, err := client.Search(context.Background(), model.SearchQuery{Query: "cafe"})
	if err == nil {
		t.Fatal("provider failure must not succeed")
	}
	var appError *rerrors.AppError
	if !errors.As(err, &appError) {
		t.Fatalf("error type = %T, want *runtimeerrors.AppError", err)
	}
	if appError.Code.String() != generated.ErrLocationProviderUnavailable.Error() {
		t.Fatalf("error code = %s", appError.Code.String())
	}
	if appError.Recovery.Action != "retry" || appError.Recovery.AfterSeconds != 5 {
		t.Fatalf("recovery = %+v, want retry after five seconds", appError.Recovery)
	}
	if strings.Contains(err.Error(), "vendor diagnostic") {
		t.Fatalf("provider diagnostic leaked through adapter: %v", err)
	}
}

func TestUnavailableLocationProviderMapsBlockedCapabilityToStructuredRecovery(t *testing.T) {
	locationProvider := NewUnavailableLocationProvider(
		"integration location lookup capability is blocked for environment=gamma",
	)

	_, err := locationProvider.Nearby(context.Background(), model.NearbyQuery{})
	if err == nil {
		t.Fatal("blocked capability must not return synthetic POIs")
	}
	var appError *rerrors.AppError
	if !errors.As(err, &appError) {
		t.Fatalf("error type = %T, want *runtimeerrors.AppError", err)
	}
	if appError.Code.String() != generated.ErrLocationProviderUnavailable.Error() {
		t.Fatalf("error code = %s", appError.Code.String())
	}
	if appError.Recovery.Action != "retry" || appError.Recovery.AfterSeconds != 5 {
		t.Fatalf("recovery = %+v, want retry after five seconds", appError.Recovery)
	}
}
