// Package ports 定义 DeviceRegistration 对象专属 Store、named reader 与 token cipher。
package ports

import (
	"context"
	"errors"

	registrationmodel "quwoquan_service/services/user-service/internal/domain/account/device_registration/model"
)

var ErrActiveTokenConflict = errors.New(
	"push token fingerprint belongs to another active device push endpoint",
)

type CommitMutation struct {
	ExpectedAggregateVersion int64
	ExpectedEndpointVersions map[string]int64
	Registration             registrationmodel.DeviceRegistration
}

// AggregateStore 是 DeviceRegistration 唯一写端口。父与本次 changed child 的
// version CAS 必须在同一 PostgreSQL transaction 中成功或回滚。
type AggregateStore interface {
	Load(
		ctx context.Context,
		accountID string,
		deviceID string,
	) (registrationmodel.DeviceRegistration, bool, error)
	LoadByEndpointRef(
		ctx context.Context,
		endpointRef string,
	) (registrationmodel.DeviceRegistration, bool, error)
	Commit(ctx context.Context, mutation CommitMutation) error
}

type PushDestinationRef struct {
	EndpointRef string
	DeviceID    string
	Kind        registrationmodel.EndpointKind
}

// ResolveIncomingCallPushDestinationsReader 是 account-scoped named reader。
// 返回值刻意不含 token ciphertext/fingerprint。
type ResolveIncomingCallPushDestinationsReader interface {
	ListActivePushDestinations(
		ctx context.Context,
		accountID string,
	) ([]PushDestinationRef, error)
}

// ResolvePushEndpointSecretReader 只读取 active owned endpoint 的加密持久化状态。
type ResolvePushEndpointSecretReader interface {
	FindPushEndpointByRef(
		ctx context.Context,
		endpointRef string,
	) (registrationmodel.EndpointState, bool, error)
}

type TokenCipherScope struct {
	AccountID string
	DeviceID  string
	Kind      registrationmodel.EndpointKind
}

// TokenCipher 是 token 明文允许触达的唯一基础设施端口。
// 实现必须把 accountId/deviceId/endpointKind 作为 AES-GCM AAD。
type TokenCipher interface {
	ProtectPushToken(
		ctx context.Context,
		plaintext []byte,
		scope TokenCipherScope,
	) (ciphertext string, fingerprint string, err error)
	RevealPushToken(
		ctx context.Context,
		ciphertext string,
		scope TokenCipherScope,
	) ([]byte, error)
}
