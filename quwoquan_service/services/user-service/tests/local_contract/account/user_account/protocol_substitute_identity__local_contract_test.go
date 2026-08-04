package local_contract

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	credentialmodel "quwoquan_service/services/user-service/internal/account/credential_binding/domain/model"
	userintegration "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/integration"
)

func TestProtocolSubstituteIdentityAdaptersUseRemoteProtocol(t *testing.T) {
	server := httptest.NewTLSServer(http.HandlerFunc(
		func(writer http.ResponseWriter, request *http.Request) {
			switch request.URL.Path {
			case "/carrier":
				_ = json.NewEncoder(writer).Encode(map[string]string{
					"phone": "+8613800000000", "displayLabel": "138****0000",
				})
			case "/federated":
				_ = json.NewEncoder(writer).Encode(map[string]string{
					"credentialKey": "remote-credential",
					"displayName":   "Remote Nonprod User",
					"avatarUrl":     "",
				})
			default:
				http.NotFound(writer, request)
			}
		},
	))
	defer server.Close()

	carrier, err := userintegration.NewProtocolSubstituteCarrierPhoneResolver(
		server.URL+"/carrier",
		server.Client(),
	)
	if err != nil {
		t.Fatal(err)
	}
	phone, err := carrier.ResolvePhone(context.Background(), "one-time-token")
	if err != nil || phone.Phone != "+8613800000000" {
		t.Fatalf("carrier response=%+v err=%v", phone, err)
	}

	federated, err :=
		userintegration.NewProtocolSubstituteFederatedIdentityVerifier(
			credentialmodel.CredentialTypeFederatedSlotA,
			"wechat",
			server.URL+"/federated",
			server.Client(),
		)
	if err != nil {
		t.Fatal(err)
	}
	identity, err := federated.Verify(context.Background(), "authorization-code")
	if err != nil || identity.CredentialKey != "remote-credential" {
		t.Fatalf("federated response=%+v err=%v", identity, err)
	}
}

func TestProtocolSubstituteIdentityRejectsUnisolatedPlainHTTP(t *testing.T) {
	if _, err := userintegration.NewProtocolSubstituteCarrierPhoneResolver(
		"http://example.test/carrier",
		http.DefaultClient,
	); err == nil {
		t.Fatal("plain HTTP outside the isolated service network must fail closed")
	}
}
