package local_contract

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"quwoquan_service/runtime/reliabletask"
	pushprovider "quwoquan_service/services/integration-service/internal/external_integration/push_delivery/infrastructure/provider"
	integrationsupport "quwoquan_service/services/integration-service/tests/support"
)

func TestProtocolSubstitutePushProviderUsesRemoteProtocol(t *testing.T) {
	server := httptest.NewTLSServer(http.HandlerFunc(
		func(writer http.ResponseWriter, _ *http.Request) {
			writer.Header().Set("Content-Type", "application/json")
			writer.WriteHeader(http.StatusAccepted)
			_, _ = writer.Write([]byte(`{"providerRequestId":"remote-request-1"}`))
		},
	))
	defer server.Close()

	provider, err := pushprovider.NewProtocolSubstitutePushProvider(
		server.URL,
		server.Client(),
		time.Second,
	)
	if err != nil {
		t.Fatal(err)
	}
	result, err := provider.Send(
		context.Background(),
		reliabletask.ExternalInteractionRequest{
			RequestID:      "request-1",
			Operation:      reliabletask.ExternalInteractionOperationPush,
			IdempotencyKey: "delivery-1",
			PayloadDigest: integrationsupport.CanonicalTestSHA256(
				"push:delivery-1",
			),
		},
		reliabletask.ReliableAsyncTask{},
	)
	if err != nil ||
		result.ProviderRequestID != "remote-request-1" ||
		result.Provider != pushprovider.ProtocolSubstituteProviderName {
		t.Fatalf("result=%+v err=%v", result, err)
	}
}

func TestProtocolSubstitutePushProviderRejectsUnisolatedHTTP(t *testing.T) {
	if _, err := pushprovider.NewProtocolSubstitutePushProvider(
		"http://example.test/push",
		http.DefaultClient,
		time.Second,
	); err == nil {
		t.Fatal("plain HTTP outside the isolated network must fail closed")
	}
}
