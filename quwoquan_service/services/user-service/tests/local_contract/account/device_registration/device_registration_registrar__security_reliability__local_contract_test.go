package local_contract

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"sync"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	runtimeerrors "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/operation"
	registrationapp "quwoquan_service/services/user-service/internal/account/device_registration/application"
	registrationmodel "quwoquan_service/services/user-service/internal/account/device_registration/domain/model"
	registrationports "quwoquan_service/services/user-service/internal/account/device_registration/domain/ports"
)

func TestDevicePushEndpointCommandsEncryptReplayRotateAndSupportDualKinds(
	t *testing.T,
) {
	t.Parallel()

	now := time.Date(2026, 7, 20, 10, 0, 0, 0, time.UTC)
	store := newFakeDeviceRegistrationStore()
	tokenCipher := newSpyDeviceTokenCipher()
	facade := registrationapp.NewCommandFacade(
		store,
		tokenCipher,
		registrationapp.WithClock(func() time.Time {
			now = now.Add(time.Second)
			return now
		}),
	)
	ctx := trustedAccountContext("account-1")

	first, err := facade.UpsertDevicePushEndpoint(
		ctx,
		registrationapp.UpsertDevicePushEndpointCommand{
			DeviceID:   "device-1",
			Kind:       registrationmodel.EndpointKindAPNSVoIP,
			Token:      []byte("plaintext-apns-token"),
			AppVersion: "1.0.0",
		},
	)
	if err != nil {
		t.Fatalf("首次 upsert: %v", err)
	}
	replay, err := facade.UpsertDevicePushEndpoint(
		ctx,
		registrationapp.UpsertDevicePushEndpointCommand{
			DeviceID:   "device-1",
			Kind:       registrationmodel.EndpointKindAPNSVoIP,
			Token:      []byte("plaintext-apns-token"),
			AppVersion: "1.0.0",
		},
	)
	if err != nil {
		t.Fatalf("自然幂等 replay: %v", err)
	}
	if replay.IdempotentReplay != true ||
		replay.Version != first.Version ||
		replay.AggregateVersion != first.AggregateVersion ||
		store.commitCount() != 1 {
		t.Fatalf("重复 upsert 不得推进版本或提交: first=%+v replay=%+v", first, replay)
	}

	rotated, err := facade.UpsertDevicePushEndpoint(
		ctx,
		registrationapp.UpsertDevicePushEndpointCommand{
			DeviceID:   "device-1",
			Kind:       registrationmodel.EndpointKindAPNSVoIP,
			Token:      []byte("rotated-apns-token"),
			AppVersion: "1.1.0",
		},
	)
	if err != nil {
		t.Fatalf("token 轮换: %v", err)
	}
	if rotated.Version != first.Version+1 ||
		rotated.AggregateVersion != first.AggregateVersion+1 {
		t.Fatalf("轮换必须同时推进 child/parent version: %+v", rotated)
	}

	fcm, err := facade.UpsertDevicePushEndpoint(
		ctx,
		registrationapp.UpsertDevicePushEndpointCommand{
			DeviceID:   "device-1",
			Kind:       registrationmodel.EndpointKindFCM,
			Token:      []byte("plaintext-fcm-token"),
			AppVersion: "1.1.0",
		},
	)
	if err != nil {
		t.Fatalf("同设备增加 fcm: %v", err)
	}
	if fcm.EndpointKind != registrationmodel.EndpointKindFCM {
		t.Fatalf("fcm 回执错误: %+v", fcm)
	}
	state := store.mustState(t, "account-1", "device-1")
	if len(state.PushEndpoints) != 2 {
		t.Fatalf("同设备应有双 endpoint: %+v", state.PushEndpoints)
	}
	for _, endpoint := range state.PushEndpoints {
		if endpoint.TokenCiphertext == "" ||
			endpoint.TokenFingerprint == "" ||
			strings.Contains(endpoint.TokenCiphertext, "plaintext") {
			t.Fatalf("Store 只能接收密文和 fingerprint: %+v", endpoint)
		}
	}

	loggable := fmt.Sprintf("%+v %+v", first, state)
	for _, plaintext := range []string{
		"plaintext-apns-token",
		"rotated-apns-token",
		"plaintext-fcm-token",
	} {
		if strings.Contains(loggable, plaintext) {
			t.Fatalf("响应/领域状态的可记录表示泄露 token: %q", plaintext)
		}
	}
	if tokenCipher.protectCallCount() != 4 {
		t.Fatalf("每次 upsert 都必须先走 cipher，得到 %d", tokenCipher.protectCallCount())
	}
}

func TestDevicePushEndpointRemoveAndInvalidateClearTokenMaterial(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, 7, 20, 11, 0, 0, 0, time.UTC)
	store := newFakeDeviceRegistrationStore()
	facade := registrationapp.NewCommandFacade(
		store,
		newSpyDeviceTokenCipher(),
		registrationapp.WithClock(func() time.Time {
			now = now.Add(time.Second)
			return now
		}),
	)
	accountCtx := trustedAccountContext("account-1")
	apns, err := facade.UpsertDevicePushEndpoint(
		accountCtx,
		registrationapp.UpsertDevicePushEndpointCommand{
			DeviceID: "device-1", Kind: registrationmodel.EndpointKindAPNSVoIP,
			Token: []byte("apns-token"),
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	fcm, err := facade.UpsertDevicePushEndpoint(
		accountCtx,
		registrationapp.UpsertDevicePushEndpointCommand{
			DeviceID: "device-1", Kind: registrationmodel.EndpointKindFCM,
			Token: []byte("fcm-token"),
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	removed, err := facade.RemoveDevicePushEndpoint(
		accountCtx,
		registrationapp.RemoveDevicePushEndpointCommand{
			DeviceID: "device-1", Kind: registrationmodel.EndpointKindAPNSVoIP,
		},
	)
	if err != nil || removed.Status != registrationmodel.StatusRevoked {
		t.Fatalf("remove endpoint: result=%+v err=%v", removed, err)
	}
	invalidated, err := facade.InvalidateDevicePushEndpoint(
		trustedServiceContext(registrationapp.PushEndpointInvalidateScope),
		registrationapp.InvalidateDevicePushEndpointCommand{
			EndpointRef: fcm.EndpointRef,
			Reason:      "provider_unregistered",
		},
	)
	if err != nil || invalidated.Status != registrationmodel.StatusStale {
		t.Fatalf("invalidate endpoint: result=%+v err=%v", invalidated, err)
	}
	state := store.mustState(t, "account-1", "device-1")
	if state.Status != registrationmodel.StatusStale {
		t.Fatalf("父生命周期未与 children 对齐: %s", state.Status)
	}
	for _, endpoint := range state.PushEndpoints {
		if endpoint.TokenCiphertext != "" || endpoint.TokenFingerprint != "" {
			t.Fatalf("inactive endpoint 仍保留 token material: %+v", endpoint)
		}
	}
	replayed, err := facade.InvalidateDevicePushEndpoint(
		trustedServiceContext(registrationapp.PushEndpointInvalidateScope),
		registrationapp.InvalidateDevicePushEndpointCommand{
			EndpointRef: fcm.EndpointRef,
			Reason:      "provider_unregistered",
		},
	)
	if err != nil || !replayed.IdempotentReplay {
		t.Fatalf("重复 invalidate 必须幂等: result=%+v err=%v", replayed, err)
	}
	if apns.EndpointRef == fcm.EndpointRef {
		t.Fatal("不同 endpointKind 必须产生不同 endpointRef")
	}
}

func TestDevicePushEndpointCommandsRejectUntrustedAccountAndTokenConflict(
	t *testing.T,
) {
	t.Parallel()

	store := newFakeDeviceRegistrationStore()
	facade := registrationapp.NewCommandFacade(store, newSpyDeviceTokenCipher())
	command := registrationapp.UpsertDevicePushEndpointCommand{
		DeviceID: "device-1",
		Kind:     registrationmodel.EndpointKindFCM,
		Token:    []byte("shared-token"),
	}
	_, err := facade.UpsertDevicePushEndpoint(context.Background(), command)
	assertDeviceRegistrationAppErrorCode(t, err, "USER.USER.unauthorized")
	_, err = facade.UpsertDevicePushEndpoint(
		trustedServiceContext(registrationapp.PushEndpointInvalidateScope),
		command,
	)
	assertDeviceRegistrationAppErrorCode(t, err, "USER.USER.unauthorized")

	if _, err := facade.UpsertDevicePushEndpoint(
		trustedAccountContext("account-1"),
		command,
	); err != nil {
		t.Fatal(err)
	}
	command.DeviceID = "device-2"
	_, err = facade.UpsertDevicePushEndpoint(
		trustedAccountContext("account-2"),
		command,
	)
	assertDeviceRegistrationAppErrorCode(t, err, "USER.DEVICE_PUSH.token_conflict")
	if strings.Contains(fmt.Sprint(err), "shared-token") {
		t.Fatal("RuntimeError 不得包含 token 明文")
	}
}

func trustedAccountContext(accountID string) context.Context {
	ctx := rtauth.WithPrincipal(context.Background(), rtauth.Principal{
		Claims: rtauth.Claims{
			TokenType: rtauth.TokenTypeAccess,
		},
		Actor: operation.ActorContext{
			AccountID: accountID,
		},
	})
	return operation.WithContext(ctx, operation.Context{
		OperationID: "user.device_registration.UpsertDevicePushEndpoint",
		Actor: operation.ActorContext{
			AccountID: accountID,
		},
	})
}

func trustedServiceContext(scope string) context.Context {
	return trustedNamedServiceContext(
		registrationapp.IntegrationServicePrincipal,
		scope,
	)
}

func trustedNamedServiceContext(accountID string, scope string) context.Context {
	return rtauth.WithPrincipal(context.Background(), rtauth.Principal{
		Claims: rtauth.Claims{
			TokenType: rtauth.TokenTypeAccess,
			Scope:     scope,
			Roles:     []string{"service"},
		},
		Actor: operation.ActorContext{
			AccountID: accountID,
		},
	})
}

func assertDeviceRegistrationAppErrorCode(
	t *testing.T,
	err error,
	want string,
) {
	t.Helper()
	if err == nil {
		t.Fatalf("期望 runtime app error %s，实际 nil", want)
	}
	var appErr *runtimeerrors.AppError
	if !errors.As(err, &appErr) {
		t.Fatalf("期望 *runtimeerrors.AppError，实际 %T: %v", err, err)
	}
	if got := appErr.Code.String(); got != want {
		t.Fatalf("runtime error code=%s，期望 %s", got, want)
	}
}

type spyDeviceTokenCipher struct {
	mu       sync.Mutex
	protects int
	byCipher map[string][]byte
}

func newSpyDeviceTokenCipher() *spyDeviceTokenCipher {
	return &spyDeviceTokenCipher{byCipher: map[string][]byte{}}
}

func (cipher *spyDeviceTokenCipher) ProtectPushToken(
	_ context.Context,
	plaintext []byte,
	scope registrationports.TokenCipherScope,
) (string, string, error) {
	cipher.mu.Lock()
	defer cipher.mu.Unlock()
	cipher.protects++
	sum := sha256.Sum256(plaintext)
	fingerprint := hex.EncodeToString(sum[:])
	ciphertext := fmt.Sprintf(
		"cipher-%s-%s-%d",
		scope.Kind,
		fingerprint,
		cipher.protects,
	)
	cipher.byCipher[ciphertext] = append([]byte(nil), plaintext...)
	return ciphertext, fingerprint, nil
}

func (cipher *spyDeviceTokenCipher) RevealPushToken(
	_ context.Context,
	ciphertext string,
	_ registrationports.TokenCipherScope,
) ([]byte, error) {
	cipher.mu.Lock()
	defer cipher.mu.Unlock()
	plaintext, ok := cipher.byCipher[ciphertext]
	if !ok {
		return nil, errors.New("ciphertext not found")
	}
	return append([]byte(nil), plaintext...), nil
}

func (cipher *spyDeviceTokenCipher) protectCallCount() int {
	cipher.mu.Lock()
	defer cipher.mu.Unlock()
	return cipher.protects
}

type fakeDeviceRegistrationStore struct {
	mu                sync.Mutex
	byIdentity        map[string]registrationmodel.DeviceRegistration
	activeFingerprint map[string]string
	commits           int
}

func newFakeDeviceRegistrationStore() *fakeDeviceRegistrationStore {
	return &fakeDeviceRegistrationStore{
		byIdentity:        map[string]registrationmodel.DeviceRegistration{},
		activeFingerprint: map[string]string{},
	}
}

func (store *fakeDeviceRegistrationStore) Load(
	_ context.Context,
	accountID string,
	deviceID string,
) (registrationmodel.DeviceRegistration, bool, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	value, ok := store.byIdentity[deviceIdentityKey(accountID, deviceID)]
	return value, ok, nil
}

func (store *fakeDeviceRegistrationStore) LoadByEndpointRef(
	_ context.Context,
	endpointRef string,
) (registrationmodel.DeviceRegistration, bool, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	for _, registration := range store.byIdentity {
		if _, found := registration.EndpointByRef(endpointRef); found {
			return registration, true, nil
		}
	}
	return registrationmodel.DeviceRegistration{}, false, nil
}

func (store *fakeDeviceRegistrationStore) Commit(
	_ context.Context,
	mutation registrationports.CommitMutation,
) error {
	store.mu.Lock()
	defer store.mu.Unlock()
	if err := mutation.Registration.Validate(); err != nil {
		return err
	}
	next := mutation.Registration.State()
	key := deviceIdentityKey(next.AccountID, next.DeviceID)
	current, found := store.byIdentity[key]
	if mutation.ExpectedAggregateVersion == 0 {
		if found {
			return registrationmodel.ErrVersionConflict
		}
	} else {
		if !found ||
			current.State().Version != mutation.ExpectedAggregateVersion ||
			next.Version != mutation.ExpectedAggregateVersion+1 {
			return registrationmodel.ErrVersionConflict
		}
	}
	for _, endpoint := range next.PushEndpoints {
		if endpoint.Status != registrationmodel.StatusActive {
			continue
		}
		if owner, exists := store.activeFingerprint[endpoint.TokenFingerprint]; exists && owner != endpoint.EndpointRef {
			return registrationports.ErrActiveTokenConflict
		}
	}
	if found {
		for _, endpoint := range current.State().PushEndpoints {
			delete(store.activeFingerprint, endpoint.TokenFingerprint)
		}
	}
	store.byIdentity[key] = mutation.Registration
	for _, endpoint := range next.PushEndpoints {
		if endpoint.Status == registrationmodel.StatusActive {
			store.activeFingerprint[endpoint.TokenFingerprint] = endpoint.EndpointRef
		}
	}
	store.commits++
	return nil
}

func (store *fakeDeviceRegistrationStore) ListActivePushDestinations(
	_ context.Context,
	accountID string,
) ([]registrationports.PushDestinationRef, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	result := make([]registrationports.PushDestinationRef, 0)
	for _, registration := range store.byIdentity {
		state := registration.State()
		if state.AccountID != accountID {
			continue
		}
		for _, endpoint := range state.PushEndpoints {
			if endpoint.Status == registrationmodel.StatusActive {
				result = append(result, registrationports.PushDestinationRef{
					EndpointRef: endpoint.EndpointRef,
					DeviceID:    endpoint.DeviceID,
					Kind:        endpoint.Kind,
				})
			}
		}
	}
	return result, nil
}

func (store *fakeDeviceRegistrationStore) FindPushEndpointByRef(
	_ context.Context,
	endpointRef string,
) (registrationmodel.EndpointState, bool, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	for _, registration := range store.byIdentity {
		if endpoint, found := registration.EndpointByRef(endpointRef); found {
			return endpoint, true, nil
		}
	}
	return registrationmodel.EndpointState{}, false, nil
}

func (store *fakeDeviceRegistrationStore) mustState(
	t *testing.T,
	accountID string,
	deviceID string,
) registrationmodel.State {
	t.Helper()
	registration, found, err := store.Load(
		context.Background(),
		accountID,
		deviceID,
	)
	if err != nil || !found {
		t.Fatalf("读取设备登记: found=%v err=%v", found, err)
	}
	return registration.State()
}

func (store *fakeDeviceRegistrationStore) commitCount() int {
	store.mu.Lock()
	defer store.mu.Unlock()
	return store.commits
}

func deviceIdentityKey(accountID, deviceID string) string {
	return strings.TrimSpace(accountID) + "\x00" + strings.TrimSpace(deviceID)
}

var (
	_ registrationports.TokenCipher                               = (*spyDeviceTokenCipher)(nil)
	_ registrationports.AggregateStore                            = (*fakeDeviceRegistrationStore)(nil)
	_ registrationports.ResolveIncomingCallPushDestinationsReader = (*fakeDeviceRegistrationStore)(nil)
	_ registrationports.ResolvePushEndpointSecretReader           = (*fakeDeviceRegistrationStore)(nil)
)
