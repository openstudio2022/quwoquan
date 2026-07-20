package device_registration

import (
	"context"
	"strings"

	registrationmodel "quwoquan_service/services/user-service/internal/domain/account/device_registration/model"
	registrationports "quwoquan_service/services/user-service/internal/domain/account/device_registration/ports"
	userports "quwoquan_service/services/user-service/internal/domain/user/ports"
	"quwoquan_service/services/user-service/internal/generated"
)

type IncomingCallPushDestination struct {
	EndpointRef  string                         `json:"endpointRef"`
	DeviceID     string                         `json:"deviceId"`
	EndpointKind registrationmodel.EndpointKind `json:"endpointKind"`
}

type IncomingCallPushDestinationSlice struct {
	Destinations []IncomingCallPushDestination `json:"destinations"`
}

// PushEndpointSecret 只能用于一次内部 HTTP response；禁止缓存、日志或持久化。
type PushEndpointSecret struct {
	EndpointRef  string                         `json:"endpointRef"`
	EndpointKind registrationmodel.EndpointKind `json:"endpointKind"`
	Token        string                         `json:"token"`
}

type QueryFacet interface {
	ResolveIncomingCallPushDestinations(
		context.Context,
		string,
	) (IncomingCallPushDestinationSlice, error)
	ResolvePushEndpointSecret(context.Context, string) (PushEndpointSecret, error)
}

type QueryFacade struct {
	destinations registrationports.ResolveIncomingCallPushDestinationsReader
	secrets      registrationports.ResolvePushEndpointSecretReader
	personas     userports.PersonaOwnerAccountReader
	cipher       registrationports.TokenCipher
}

func NewQueryFacade(
	destinations registrationports.ResolveIncomingCallPushDestinationsReader,
	secrets registrationports.ResolvePushEndpointSecretReader,
	personas userports.PersonaOwnerAccountReader,
	cipher registrationports.TokenCipher,
) *QueryFacade {
	if destinations == nil || secrets == nil || personas == nil || cipher == nil {
		panic("DeviceRegistration query facade requires typed readers and TokenCipher")
	}
	return &QueryFacade{
		destinations: destinations,
		secrets:      secrets,
		personas:     personas,
		cipher:       cipher,
	}
}

var _ QueryFacet = (*QueryFacade)(nil)

func (facade *QueryFacade) ResolveIncomingCallPushDestinations(
	ctx context.Context,
	personaID string,
) (IncomingCallPushDestinationSlice, error) {
	if err := trustedServicePrincipal(ctx, PushDestinationReadScope); err != nil {
		return IncomingCallPushDestinationSlice{}, err
	}
	personaID = strings.TrimSpace(personaID)
	if personaID == "" {
		return IncomingCallPushDestinationSlice{},
			generated.AppErrorFromUserNotFound("personaId is required")
	}
	accountID, found, err := facade.personas.ResolveOwnerAccountID(ctx, personaID)
	if err != nil {
		return IncomingCallPushDestinationSlice{},
			generated.AppErrorFromInternalError(
				"resolve persona owner for incoming call push failed",
			)
	}
	if !found {
		return IncomingCallPushDestinationSlice{},
			generated.AppErrorFromUserNotFound(
				"incoming call target persona was not found",
			)
	}
	accountID = strings.TrimSpace(accountID)
	if accountID == "" {
		return IncomingCallPushDestinationSlice{},
			generated.AppErrorFromInternalError(
				"persona owner account is missing",
			)
	}
	refs, err := facade.destinations.ListActivePushDestinations(ctx, accountID)
	if err != nil {
		return IncomingCallPushDestinationSlice{},
			generated.AppErrorFromInternalError(
				"resolve active incoming call push destinations failed",
			)
	}
	destinations := make([]IncomingCallPushDestination, 0, len(refs))
	for _, ref := range refs {
		destinations = append(destinations, IncomingCallPushDestination{
			EndpointRef:  ref.EndpointRef,
			DeviceID:     ref.DeviceID,
			EndpointKind: ref.Kind,
		})
	}
	return IncomingCallPushDestinationSlice{Destinations: destinations}, nil
}

func (facade *QueryFacade) ResolvePushEndpointSecret(
	ctx context.Context,
	endpointRef string,
) (PushEndpointSecret, error) {
	if err := trustedServicePrincipal(
		ctx,
		PushEndpointSecretReadScope,
		IntegrationServicePrincipal,
	); err != nil {
		return PushEndpointSecret{}, err
	}
	endpointRef = strings.TrimSpace(endpointRef)
	if endpointRef == "" {
		return PushEndpointSecret{},
			generated.AppErrorFromDevicePushEndpointNotFound(
				"endpointRef is required",
			)
	}
	endpoint, found, err := facade.secrets.FindPushEndpointByRef(ctx, endpointRef)
	if err != nil {
		return PushEndpointSecret{}, generated.AppErrorFromInternalError(
			"resolve push endpoint secret state failed",
		)
	}
	if !found {
		return PushEndpointSecret{},
			generated.AppErrorFromDevicePushEndpointNotFound(
				"push endpoint was not found",
			)
	}
	if endpoint.Status != registrationmodel.StatusActive {
		return PushEndpointSecret{},
			generated.AppErrorFromDevicePushEndpointNotActive(
				"push endpoint is not active",
			)
	}
	plaintext, err := facade.cipher.RevealPushToken(
		ctx,
		endpoint.TokenCiphertext,
		registrationports.TokenCipherScope{
			AccountID: endpoint.AccountID,
			DeviceID:  endpoint.DeviceID,
			Kind:      endpoint.Kind,
		},
	)
	if err != nil || len(plaintext) == 0 {
		clearBytes(plaintext)
		return PushEndpointSecret{},
			generated.AppErrorFromDevicePushCryptoFailure(
				"push endpoint token decryption failed",
			)
	}
	token := string(plaintext)
	clearBytes(plaintext)
	return PushEndpointSecret{
		EndpointRef:  endpoint.EndpointRef,
		EndpointKind: endpoint.Kind,
		Token:        token,
	}, nil
}
