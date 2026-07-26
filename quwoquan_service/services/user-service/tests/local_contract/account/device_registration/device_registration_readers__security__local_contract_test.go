package local_contract

import (
	"context"
	"testing"

	registrationapp "quwoquan_service/services/user-service/internal/account/device_registration/application"
	registrationmodel "quwoquan_service/services/user-service/internal/account/device_registration/domain/model"
	userports "quwoquan_service/services/user-service/internal/account/user_account/domain/user/ports"
)

func TestDevicePushEndpointNamedReadersSplitReferencesFromSecret(t *testing.T) {
	t.Parallel()

	store := newFakeDeviceRegistrationStore()
	cipher := newSpyDeviceTokenCipher()
	commands := registrationapp.NewCommandFacade(store, cipher)
	created, err := commands.UpsertDevicePushEndpoint(
		trustedAccountContext("account-1"),
		registrationapp.UpsertDevicePushEndpointCommand{
			DeviceID: "device-1",
			Kind:     registrationmodel.EndpointKindAPNSVoIP,
			Token:    []byte("reader-secret-token"),
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	queries := registrationapp.NewQueryFacade(
		store,
		store,
		&fakePersonaOwnerReader{
			personaID: "persona-1",
			accountID: "account-1",
		},
		cipher,
	)
	destinations, err := queries.ResolveIncomingCallPushDestinations(
		trustedServiceContext(registrationapp.PushDestinationReadScope),
		"persona-1",
	)
	if err != nil || len(destinations.Destinations) != 1 {
		t.Fatalf("resolve destinations: %+v err=%v", destinations, err)
	}
	destination := destinations.Destinations[0]
	if destination.EndpointRef != created.EndpointRef ||
		destination.DeviceID != "device-1" ||
		destination.EndpointKind != registrationmodel.EndpointKindAPNSVoIP {
		t.Fatalf("destination ref 错误: %+v", destination)
	}
	secret, err := queries.ResolvePushEndpointSecret(
		trustedServiceContext(registrationapp.PushEndpointSecretReadScope),
		created.EndpointRef,
	)
	if err != nil ||
		secret.EndpointKind != registrationmodel.EndpointKindAPNSVoIP ||
		secret.Token != "reader-secret-token" {
		t.Fatalf("resolve secret: %+v err=%v", secret, err)
	}
	_, err = queries.ResolvePushEndpointSecret(
		trustedServiceContext(registrationapp.PushDestinationReadScope),
		created.EndpointRef,
	)
	assertDeviceRegistrationAppErrorCode(t, err, "USER.USER.forbidden")
	_, err = queries.ResolvePushEndpointSecret(
		trustedNamedServiceContext(
			"service:notification-service",
			registrationapp.PushEndpointSecretReadScope,
		),
		created.EndpointRef,
	)
	assertDeviceRegistrationAppErrorCode(t, err, "USER.USER.forbidden")
}

type fakePersonaOwnerReader struct {
	personaID string
	accountID string
}

func (reader *fakePersonaOwnerReader) ResolveOwnerAccountID(
	_ context.Context,
	subAccountID string,
) (string, bool, error) {
	if reader.personaID != subAccountID {
		return "", false, nil
	}
	return reader.accountID, true, nil
}

var _ userports.PersonaOwnerAccountReader = (*fakePersonaOwnerReader)(nil)
