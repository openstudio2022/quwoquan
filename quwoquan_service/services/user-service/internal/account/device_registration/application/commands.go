package device_registration

import (
	"time"

	registrationmodel "quwoquan_service/services/user-service/internal/account/device_registration/domain/model"
)

const (
	PushDestinationReadScope    = "user.push_destination.read"
	PushEndpointSecretReadScope = "user.push_endpoint.secret.read"
	PushEndpointInvalidateScope = "user.push_endpoint.invalidate"
	IntegrationServicePrincipal = "service:integration-service"
)

// RegisterCommand 只供可信登录 coordinator 建立/刷新父设备登记，不携带 push token。
type RegisterCommand struct {
	AccountID  string
	DeviceID   string
	AppVersion string
}

type RegisterResult struct {
	Registration     registrationmodel.Snapshot
	IdempotentReplay bool
}

// UpsertDevicePushEndpointCommand 的 AccountID 不由 transport 输入，必须从
// operation.Context 的 trusted account actor 解析。
type UpsertDevicePushEndpointCommand struct {
	DeviceID   string
	Kind       registrationmodel.EndpointKind
	Token      []byte
	AppVersion string
}

type RemoveDevicePushEndpointCommand struct {
	DeviceID string
	Kind     registrationmodel.EndpointKind
}

type InvalidateDevicePushEndpointCommand struct {
	EndpointRef string
	Reason      string
}

// DevicePushEndpointCommandResult 是不含任何 token material 的强类型回执。
type DevicePushEndpointCommandResult struct {
	EndpointRef      string                         `json:"endpointRef"`
	DeviceID         string                         `json:"deviceId"`
	EndpointKind     registrationmodel.EndpointKind `json:"endpointKind"`
	Status           registrationmodel.Status       `json:"status"`
	Version          int64                          `json:"version"`
	AggregateVersion int64                          `json:"aggregateVersion"`
	IdempotentReplay bool                           `json:"idempotentReplay"`
	UpdatedAt        time.Time                      `json:"updatedAt"`
}
