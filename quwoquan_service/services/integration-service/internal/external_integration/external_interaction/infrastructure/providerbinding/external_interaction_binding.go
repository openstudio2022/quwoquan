package providerbinding

import (
	"errors"
	"fmt"
	"strings"
	"time"

	runtimeconfig "quwoquan_service/runtime/config"
	integrationgenerated "quwoquan_service/services/integration-service/generated/external_integration/external_interaction"
)

const (
	smsCapabilityID  = "identity.sms.otp"
	pushCapabilityID = "integration.push.delivery"
)

// ErrExternalInteractionCapabilityBlocked 表示 metadata 显式禁用某项外部交互能力。
// 这不是缺失的运行时材料：composition root 应禁用相应 operation，同时继续提供
// 其余 integration-service 能力。
var ErrExternalInteractionCapabilityBlocked = errors.New(
	"integration external interaction capability is blocked",
)

// ExternalInteractionBinding is startup-only provider material for a single
// compiler-selected external interaction capability.
type ExternalInteractionBinding struct {
	AdapterID string
	Endpoints map[string]string
	Secrets   map[string]string
	Timeout   time.Duration
}

// ResolveSMSBinding materializes the compiler-selected SMS adapter.
func ResolveSMSBinding(
	appEnv string,
	configProvider runtimeconfig.RuntimeConfigProvider,
) (ExternalInteractionBinding, error) {
	return resolveExternalInteractionBinding(
		appEnv,
		smsCapabilityID,
		map[string]struct{}{
			SMSAdapterAliyun:       {},
			SMSAdapterLocalCapture: {},
		},
		configProvider,
	)
}

// ResolvePushBinding materializes the compiler-selected Push adapter.
func ResolvePushBinding(
	appEnv string,
	configProvider runtimeconfig.RuntimeConfigProvider,
) (ExternalInteractionBinding, error) {
	return resolveExternalInteractionBinding(
		appEnv,
		pushCapabilityID,
		map[string]struct{}{
			PushAdapterDispatch:      {},
			PushAdapterLocalRecorder: {},
		},
		configProvider,
	)
}

func resolveExternalInteractionBinding(
	appEnv string,
	capabilityID string,
	allowedAdapters map[string]struct{},
	configProvider runtimeconfig.RuntimeConfigProvider,
) (ExternalInteractionBinding, error) {
	if configProvider == nil {
		return ExternalInteractionBinding{}, fmt.Errorf(
			"%s has no runtime config provider",
			capabilityID,
		)
	}
	binding, found := integrationgenerated.ExternalProviderBindingFor(appEnv, capabilityID)
	if !found {
		return ExternalInteractionBinding{}, fmt.Errorf(
			"%s binding is missing for environment=%s",
			capabilityID,
			appEnv,
		)
	}
	if binding.State != "enabled" {
		return ExternalInteractionBinding{}, fmt.Errorf(
			"%w: %s for environment=%s",
			ErrExternalInteractionCapabilityBlocked,
			capabilityID,
			appEnv,
		)
	}
	if _, ok := allowedAdapters[binding.AdapterID]; !ok || binding.TimeoutMilliseconds <= 0 {
		return ExternalInteractionBinding{}, fmt.Errorf(
			"%s binding is incomplete or selects an unexpected adapter",
			capabilityID,
		)
	}

	endpoints := make(map[string]string, len(binding.EndpointEnvironmentKeys))
	for role, environmentKey := range binding.EndpointEnvironmentKeys {
		value, ok := configProvider.GetString(environmentKey)
		if !ok {
			return ExternalInteractionBinding{}, fmt.Errorf(
				"%s endpoint material is unavailable for environment=%s role=%s",
				capabilityID,
				appEnv,
				role,
			)
		}
		endpoints[role] = value
	}
	secrets := make(map[string]string, len(binding.SecretEnvironmentKeys))
	for _, environmentKey := range binding.SecretEnvironmentKeys {
		value, ok := configProvider.GetString(environmentKey)
		if !ok {
			return ExternalInteractionBinding{}, fmt.Errorf(
				"%s secret material is unavailable for environment=%s",
				capabilityID,
				appEnv,
			)
		}
		secrets[environmentKey] = value
	}
	return ExternalInteractionBinding{
		AdapterID: binding.AdapterID,
		Endpoints: endpoints,
		Secrets:   secrets,
		Timeout:   time.Duration(binding.TimeoutMilliseconds) * time.Millisecond,
	}, nil
}

func (binding ExternalInteractionBinding) Endpoint(role string) (string, bool) {
	value, ok := binding.Endpoints[role]
	return value, ok && strings.TrimSpace(value) != ""
}

func (binding ExternalInteractionBinding) Secret(environmentKey string) (string, bool) {
	value, ok := binding.Secrets[environmentKey]
	return value, ok && strings.TrimSpace(value) != ""
}
