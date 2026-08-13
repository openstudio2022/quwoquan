package local_contract

import (
	"context"
	"testing"

	registrationapp "quwoquan_service/services/user-service/internal/account/device_registration/application"
	registrationmodel "quwoquan_service/services/user-service/internal/account/device_registration/domain/model"
	registrationports "quwoquan_service/services/user-service/internal/account/device_registration/domain/ports"
)

type failingDeviceTokenCipher struct{}

func (failingDeviceTokenCipher) ProtectPushToken(
	context.Context,
	[]byte,
	registrationports.TokenCipherScope,
) (string, string, error) {
	return "", "", context.DeadlineExceeded
}

func (failingDeviceTokenCipher) RevealPushToken(
	context.Context,
	string,
	registrationports.TokenCipherScope,
) ([]byte, error) {
	return nil, context.DeadlineExceeded
}

// conflictingDeviceRegistrationStore 让每次 CAS 提交都撞上并发版本冲突。
type conflictingDeviceRegistrationStore struct {
	*fakeDeviceRegistrationStore
}

func (conflictingDeviceRegistrationStore) Commit(
	context.Context,
	registrationports.CommitMutation,
) error {
	return registrationmodel.ErrVersionConflict
}

func TestDevicePushEndpointUpsertRejectsUnknownEndpointKind(t *testing.T) {
	t.Parallel()
	facade := registrationapp.NewCommandFacade(
		newFakeDeviceRegistrationStore(),
		newSpyDeviceTokenCipher(),
	)

	_, err := facade.UpsertDevicePushEndpoint(
		trustedAccountContext("account-kind"),
		registrationapp.UpsertDevicePushEndpointCommand{
			DeviceID: "device-1",
			Kind:     registrationmodel.EndpointKind("email"),
			Token:    []byte("token"),
		},
	)
	assertDeviceRegistrationAppErrorCode(
		t, err, "USER.DEVICE_PUSH.invalid_endpoint_kind",
	)
}

func TestDevicePushEndpointUpsertRejectsBlankToken(t *testing.T) {
	t.Parallel()
	facade := registrationapp.NewCommandFacade(
		newFakeDeviceRegistrationStore(),
		newSpyDeviceTokenCipher(),
	)

	_, err := facade.UpsertDevicePushEndpoint(
		trustedAccountContext("account-token"),
		registrationapp.UpsertDevicePushEndpointCommand{
			DeviceID: "device-1",
			Kind:     registrationmodel.EndpointKindFCM,
			Token:    []byte("   "),
		},
	)
	assertDeviceRegistrationAppErrorCode(t, err, "USER.DEVICE_PUSH.invalid_token")
}

func TestDevicePushEndpointUpsertSurfacesCryptoFailure(t *testing.T) {
	t.Parallel()
	facade := registrationapp.NewCommandFacade(
		newFakeDeviceRegistrationStore(),
		failingDeviceTokenCipher{},
	)

	_, err := facade.UpsertDevicePushEndpoint(
		trustedAccountContext("account-crypto"),
		registrationapp.UpsertDevicePushEndpointCommand{
			DeviceID: "device-1",
			Kind:     registrationmodel.EndpointKindFCM,
			Token:    []byte("valid-token"),
		},
	)
	assertDeviceRegistrationAppErrorCode(t, err, "USER.DEVICE_PUSH.crypto_failure")
}

func TestDevicePushEndpointRemoveSurfacesEndpointNotFound(t *testing.T) {
	t.Parallel()
	facade := registrationapp.NewCommandFacade(
		newFakeDeviceRegistrationStore(),
		newSpyDeviceTokenCipher(),
	)

	_, err := facade.RemoveDevicePushEndpoint(
		trustedAccountContext("account-missing"),
		registrationapp.RemoveDevicePushEndpointCommand{
			DeviceID: "device-unregistered",
			Kind:     registrationmodel.EndpointKindFCM,
		},
	)
	assertDeviceRegistrationAppErrorCode(
		t, err, "USER.DEVICE_PUSH.endpoint_not_found",
	)
}

func TestDevicePushEndpointInvalidateRejectsBlankReason(t *testing.T) {
	t.Parallel()
	facade := registrationapp.NewCommandFacade(
		newFakeDeviceRegistrationStore(),
		newSpyDeviceTokenCipher(),
	)

	_, err := facade.InvalidateDevicePushEndpoint(
		trustedServiceContext(registrationapp.PushEndpointInvalidateScope),
		registrationapp.InvalidateDevicePushEndpointCommand{
			EndpointRef: "endpoint-ref-1",
			Reason:      "   ",
		},
	)
	assertDeviceRegistrationAppErrorCode(
		t, err, "USER.DEVICE_PUSH.invalid_invalidation_reason",
	)
}

func TestDevicePushEndpointUpsertSurfacesVersionConflictAfterCASRetries(
	t *testing.T,
) {
	t.Parallel()
	facade := registrationapp.NewCommandFacade(
		conflictingDeviceRegistrationStore{newFakeDeviceRegistrationStore()},
		newSpyDeviceTokenCipher(),
	)

	_, err := facade.UpsertDevicePushEndpoint(
		trustedAccountContext("account-cas"),
		registrationapp.UpsertDevicePushEndpointCommand{
			DeviceID: "device-1",
			Kind:     registrationmodel.EndpointKindFCM,
			Token:    []byte("conflicted-token"),
		},
	)
	assertDeviceRegistrationAppErrorCode(
		t, err, "USER.DEVICE_PUSH.version_conflict",
	)
}
