// Package device_registration 提供 DeviceRegistration 对象专属 command Facade。
package device_registration

import (
	"bytes"
	"context"
	"errors"
	"strings"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	registrationmodel "quwoquan_service/services/user-service/internal/domain/account/device_registration/model"
	registrationports "quwoquan_service/services/user-service/internal/domain/account/device_registration/ports"
	"quwoquan_service/services/user-service/internal/generated"
)

const (
	deviceRegistrationCommitAttempts = 3
	maxPushTokenBytes                = 4096
	maxInvalidationReasonBytes       = 256
)

type InternalRegisterer interface {
	Register(context.Context, RegisterCommand) (RegisterResult, error)
}

type CommandFacet interface {
	UpsertDevicePushEndpoint(
		context.Context,
		UpsertDevicePushEndpointCommand,
	) (DevicePushEndpointCommandResult, error)
	RemoveDevicePushEndpoint(
		context.Context,
		RemoveDevicePushEndpointCommand,
	) (DevicePushEndpointCommandResult, error)
	InvalidateDevicePushEndpoint(
		context.Context,
		InvalidateDevicePushEndpointCommand,
	) (DevicePushEndpointCommandResult, error)
}

type CommandFacade struct {
	store  registrationports.AggregateStore
	cipher registrationports.TokenCipher
	now    func() time.Time
}

type Option func(*CommandFacade)

func WithClock(now func() time.Time) Option {
	return func(facade *CommandFacade) {
		if now != nil {
			facade.now = now
		}
	}
}

func NewCommandFacade(
	store registrationports.AggregateStore,
	cipher registrationports.TokenCipher,
	options ...Option,
) *CommandFacade {
	if store == nil {
		panic("DeviceRegistration command facade requires an object-specific AggregateStore")
	}
	if cipher == nil {
		panic("DeviceRegistration command facade requires a TokenCipher")
	}
	facade := &CommandFacade{store: store, cipher: cipher, now: time.Now}
	for _, option := range options {
		if option != nil {
			option(facade)
		}
	}
	return facade
}

var (
	_ InternalRegisterer = (*CommandFacade)(nil)
	_ CommandFacet       = (*CommandFacade)(nil)
)

func (facade *CommandFacade) Register(
	ctx context.Context,
	command RegisterCommand,
) (RegisterResult, error) {
	accountID := strings.TrimSpace(command.AccountID)
	deviceID := strings.TrimSpace(command.DeviceID)
	appVersion := strings.TrimSpace(command.AppVersion)
	if accountID == "" || deviceID == "" {
		return RegisterResult{}, generated.AppErrorFromInvalidArgument(
			"internal device registration requires accountId and deviceId",
		)
	}
	for attempt := 0; attempt < deviceRegistrationCommitAttempts; attempt++ {
		now := facade.now().UTC()
		current, found, err := facade.store.Load(ctx, accountID, deviceID)
		if err != nil {
			return RegisterResult{}, mapRegistrationError(err)
		}
		params := registrationmodel.RegisterParams{
			AccountID: accountID, DeviceID: deviceID,
			AppVersion: appVersion, RegisteredAt: now,
		}
		var (
			mutation registrationmodel.Mutation
			expected int64
		)
		if found {
			expected = current.State().Version
			mutation, err = current.Register(params)
		} else {
			var created registrationmodel.DeviceRegistration
			created, err = registrationmodel.New(params)
			mutation = registrationmodel.Mutation{
				Aggregate: created,
				Changed:   err == nil,
			}
		}
		if err != nil {
			return RegisterResult{}, mapRegistrationError(err)
		}
		if !mutation.Changed {
			return RegisterResult{
				Registration:     mutation.Aggregate.Snapshot(),
				IdempotentReplay: true,
			}, nil
		}
		err = facade.store.Commit(ctx, registrationports.CommitMutation{
			ExpectedAggregateVersion: expected,
			Registration:             mutation.Aggregate,
		})
		if err == nil {
			return RegisterResult{Registration: mutation.Aggregate.Snapshot()}, nil
		}
		if errors.Is(err, registrationmodel.ErrVersionConflict) &&
			attempt+1 < deviceRegistrationCommitAttempts {
			continue
		}
		return RegisterResult{}, mapRegistrationError(err)
	}
	panic("unreachable DeviceRegistration Register CAS retry")
}

func (facade *CommandFacade) UpsertDevicePushEndpoint(
	ctx context.Context,
	command UpsertDevicePushEndpointCommand,
) (DevicePushEndpointCommandResult, error) {
	accountID, err := trustedAccountID(ctx)
	if err != nil {
		return DevicePushEndpointCommandResult{}, err
	}
	deviceID := strings.TrimSpace(command.DeviceID)
	kind := registrationmodel.EndpointKind(strings.TrimSpace(string(command.Kind)))
	appVersion := strings.TrimSpace(command.AppVersion)
	if !kind.Valid() {
		return DevicePushEndpointCommandResult{},
			generated.AppErrorFromDevicePushInvalidEndpointKind(
				"endpointKind must be apns_voip or fcm",
			)
	}
	if deviceID == "" {
		return DevicePushEndpointCommandResult{},
			generated.AppErrorFromDevicePushInvalidToken(
				"deviceId is required for push endpoint upsert",
			)
	}
	secret := append([]byte(nil), command.Token...)
	defer clearBytes(secret)
	token := bytes.TrimSpace(secret)
	if len(token) == 0 || len(token) > maxPushTokenBytes {
		return DevicePushEndpointCommandResult{},
			generated.AppErrorFromDevicePushInvalidToken(
				"push endpoint token is blank or exceeds the size limit",
			)
	}
	ciphertext, fingerprint, err := facade.protectPushToken(
		ctx,
		token,
		registrationports.TokenCipherScope{
			AccountID: accountID,
			DeviceID:  deviceID,
			Kind:      kind,
		},
	)
	if err != nil {
		return DevicePushEndpointCommandResult{}, err
	}

	for attempt := 0; attempt < deviceRegistrationCommitAttempts; attempt++ {
		now := facade.now().UTC()
		current, found, loadErr := facade.store.Load(ctx, accountID, deviceID)
		if loadErr != nil {
			return DevicePushEndpointCommandResult{}, mapRegistrationError(loadErr)
		}
		expected := int64(0)
		if !found {
			current, err = registrationmodel.New(registrationmodel.RegisterParams{
				AccountID: accountID, DeviceID: deviceID,
				AppVersion: appVersion, RegisteredAt: now,
			})
			if err != nil {
				return DevicePushEndpointCommandResult{}, mapRegistrationError(err)
			}
		} else {
			expected = current.State().Version
		}
		mutation, mutationErr := current.UpsertEndpoint(
			registrationmodel.UpsertEndpointParams{
				AccountID: accountID, DeviceID: deviceID, Kind: kind,
				TokenCiphertext: ciphertext, TokenFingerprint: fingerprint,
				AppVersion: appVersion, UpdatedAt: now,
			},
		)
		if mutationErr != nil {
			return DevicePushEndpointCommandResult{}, mapRegistrationError(mutationErr)
		}
		if !mutation.Changed {
			return commandResult(mutation, true)
		}
		commitErr := facade.store.Commit(ctx, registrationports.CommitMutation{
			ExpectedAggregateVersion: expected,
			ExpectedEndpointVersions: mutation.ExpectedEndpointVersions,
			Registration:             mutation.Aggregate,
		})
		if commitErr == nil {
			return commandResult(mutation, false)
		}
		if errors.Is(commitErr, registrationmodel.ErrVersionConflict) &&
			attempt+1 < deviceRegistrationCommitAttempts {
			continue
		}
		return DevicePushEndpointCommandResult{}, mapRegistrationError(commitErr)
	}
	panic("unreachable UpsertDevicePushEndpoint CAS retry")
}

func (facade *CommandFacade) RemoveDevicePushEndpoint(
	ctx context.Context,
	command RemoveDevicePushEndpointCommand,
) (DevicePushEndpointCommandResult, error) {
	accountID, err := trustedAccountID(ctx)
	if err != nil {
		return DevicePushEndpointCommandResult{}, err
	}
	deviceID := strings.TrimSpace(command.DeviceID)
	kind := registrationmodel.EndpointKind(strings.TrimSpace(string(command.Kind)))
	if !kind.Valid() {
		return DevicePushEndpointCommandResult{},
			generated.AppErrorFromDevicePushInvalidEndpointKind(
				"endpointKind must be apns_voip or fcm",
			)
	}
	for attempt := 0; attempt < deviceRegistrationCommitAttempts; attempt++ {
		current, found, loadErr := facade.store.Load(ctx, accountID, deviceID)
		if loadErr != nil {
			return DevicePushEndpointCommandResult{}, mapRegistrationError(loadErr)
		}
		if !found {
			return DevicePushEndpointCommandResult{},
				generated.AppErrorFromDevicePushEndpointNotFound(
					"device registration was not found",
				)
		}
		expected := current.State().Version
		mutation, mutationErr := current.RemoveEndpoint(kind, facade.now().UTC())
		if mutationErr != nil {
			return DevicePushEndpointCommandResult{}, mapRegistrationError(mutationErr)
		}
		if !mutation.Changed {
			return commandResult(mutation, true)
		}
		commitErr := facade.store.Commit(ctx, registrationports.CommitMutation{
			ExpectedAggregateVersion: expected,
			ExpectedEndpointVersions: mutation.ExpectedEndpointVersions,
			Registration:             mutation.Aggregate,
		})
		if commitErr == nil {
			return commandResult(mutation, false)
		}
		if errors.Is(commitErr, registrationmodel.ErrVersionConflict) &&
			attempt+1 < deviceRegistrationCommitAttempts {
			continue
		}
		return DevicePushEndpointCommandResult{}, mapRegistrationError(commitErr)
	}
	panic("unreachable RemoveDevicePushEndpoint CAS retry")
}

func (facade *CommandFacade) InvalidateDevicePushEndpoint(
	ctx context.Context,
	command InvalidateDevicePushEndpointCommand,
) (DevicePushEndpointCommandResult, error) {
	if err := trustedServicePrincipal(
		ctx,
		PushEndpointInvalidateScope,
		IntegrationServicePrincipal,
	); err != nil {
		return DevicePushEndpointCommandResult{}, err
	}
	endpointRef := strings.TrimSpace(command.EndpointRef)
	reason := strings.TrimSpace(command.Reason)
	if endpointRef == "" {
		return DevicePushEndpointCommandResult{},
			generated.AppErrorFromDevicePushEndpointNotFound(
				"endpointRef is required",
			)
	}
	if reason == "" || len(reason) > maxInvalidationReasonBytes {
		return DevicePushEndpointCommandResult{},
			generated.AppErrorFromDevicePushInvalidInvalidationReason(
				"invalidation reason is blank or exceeds 256 bytes",
			)
	}
	for attempt := 0; attempt < deviceRegistrationCommitAttempts; attempt++ {
		current, found, loadErr := facade.store.LoadByEndpointRef(ctx, endpointRef)
		if loadErr != nil {
			return DevicePushEndpointCommandResult{}, mapRegistrationError(loadErr)
		}
		if !found {
			return DevicePushEndpointCommandResult{},
				generated.AppErrorFromDevicePushEndpointNotFound(
					"push endpoint was not found",
				)
		}
		expected := current.State().Version
		mutation, mutationErr := current.InvalidateEndpoint(
			endpointRef,
			reason,
			facade.now().UTC(),
		)
		if mutationErr != nil {
			return DevicePushEndpointCommandResult{}, mapRegistrationError(mutationErr)
		}
		if !mutation.Changed {
			return commandResult(mutation, true)
		}
		commitErr := facade.store.Commit(ctx, registrationports.CommitMutation{
			ExpectedAggregateVersion: expected,
			ExpectedEndpointVersions: mutation.ExpectedEndpointVersions,
			Registration:             mutation.Aggregate,
		})
		if commitErr == nil {
			return commandResult(mutation, false)
		}
		if errors.Is(commitErr, registrationmodel.ErrVersionConflict) &&
			attempt+1 < deviceRegistrationCommitAttempts {
			continue
		}
		return DevicePushEndpointCommandResult{}, mapRegistrationError(commitErr)
	}
	panic("unreachable InvalidateDevicePushEndpoint CAS retry")
}

func (facade *CommandFacade) protectPushToken(
	ctx context.Context,
	token []byte,
	scope registrationports.TokenCipherScope,
) (string, string, error) {
	ciphertext, fingerprint, err := facade.cipher.ProtectPushToken(ctx, token, scope)
	ciphertext = strings.TrimSpace(ciphertext)
	fingerprint = strings.TrimSpace(fingerprint)
	if err != nil || ciphertext == "" || fingerprint == "" ||
		bytes.Equal([]byte(ciphertext), token) ||
		strings.Contains(ciphertext, string(token)) {
		return "", "", generated.AppErrorFromDevicePushCryptoFailure(
			"push token encryption failed",
		)
	}
	return ciphertext, fingerprint, nil
}

func trustedAccountID(ctx context.Context) (string, error) {
	principal, ok := rtauth.PrincipalFromContext(ctx)
	if !ok ||
		principal.TokenType != rtauth.TokenTypeAccess ||
		containsString(principal.Roles, "service") {
		return "", generated.AppErrorFromUnauthorized(
			"trusted account principal is required",
		)
	}
	accountID := strings.TrimSpace(principal.Actor.AccountID)
	if accountID == "" {
		return "", generated.AppErrorFromUnauthorized(
			"trusted account principal is required",
		)
	}
	return accountID, nil
}

func trustedServicePrincipal(
	ctx context.Context,
	requiredScope string,
	requiredAccountIDs ...string,
) error {
	principal, ok := rtauth.PrincipalFromContext(ctx)
	if !ok {
		return generated.AppErrorFromUnauthorized(
			"trusted service principal is required",
		)
	}
	if !containsString(principal.Roles, "service") ||
		!containsString(strings.Fields(principal.Scope), requiredScope) {
		return generated.AppErrorFromForbidden(
			"service principal lacks the required DeviceRegistration scope",
		)
	}
	if len(requiredAccountIDs) > 0 &&
		!containsString(requiredAccountIDs, principal.Actor.AccountID) {
		return generated.AppErrorFromForbidden(
			"service principal is not allowed to resolve DeviceRegistration secrets",
		)
	}
	return nil
}

func containsString(values []string, expected string) bool {
	for _, value := range values {
		if strings.TrimSpace(value) == expected {
			return true
		}
	}
	return false
}

func commandResult(
	mutation registrationmodel.Mutation,
	replayed bool,
) (DevicePushEndpointCommandResult, error) {
	endpoint, found := mutation.Aggregate.EndpointByRef(mutation.EndpointRef)
	if !found {
		return DevicePushEndpointCommandResult{}, generated.AppErrorFromInternalError(
			"device push endpoint command result is missing its owned endpoint",
		)
	}
	parent := mutation.Aggregate.Snapshot()
	return DevicePushEndpointCommandResult{
		EndpointRef:      endpoint.EndpointRef,
		DeviceID:         endpoint.DeviceID,
		EndpointKind:     endpoint.Kind,
		Status:           endpoint.Status,
		Version:          endpoint.Version,
		AggregateVersion: parent.Version,
		IdempotentReplay: replayed,
		UpdatedAt:        endpoint.UpdatedAt,
	}, nil
}

func mapRegistrationError(err error) error {
	switch {
	case errors.Is(err, registrationports.ErrActiveTokenConflict):
		return generated.AppErrorFromDevicePushTokenConflict(
			"active token fingerprint belongs to another endpoint",
		)
	case errors.Is(err, registrationmodel.ErrEndpointNotFound):
		return generated.AppErrorFromDevicePushEndpointNotFound(
			"device push endpoint was not found",
		)
	case errors.Is(err, registrationmodel.ErrInvalidEndpoint):
		return generated.AppErrorFromDevicePushInvalidToken(
			"device push endpoint input or state is invalid",
		)
	case errors.Is(err, registrationmodel.ErrInvalidRegistration):
		return generated.AppErrorFromInvalidArgument(
			"device registration input or state is invalid",
		)
	case errors.Is(err, registrationmodel.ErrInvalidTransition):
		return generated.AppErrorFromDevicePushEndpointNotActive(
			"device push endpoint lifecycle transition is invalid",
		)
	case errors.Is(err, registrationmodel.ErrVersionConflict):
		return generated.AppErrorFromDevicePushVersionConflict(
			"device registration changed during CAS commit",
		)
	default:
		return generated.AppErrorFromInternalError(
			"device registration persistence failed",
		)
	}
}

func clearBytes(value []byte) {
	for index := range value {
		value[index] = 0
	}
}
