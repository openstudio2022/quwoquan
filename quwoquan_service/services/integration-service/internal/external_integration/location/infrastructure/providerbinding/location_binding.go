package providerbinding

import (
	"errors"
	"fmt"
	"strings"
	"time"

	runtimeconfig "quwoquan_service/runtime/config"
	integrationgenerated "quwoquan_service/services/integration-service/generated/external_integration/location"
)

const LocationLookupCapabilityID = "integration.location.lookup"

// ErrLocationLookupCapabilityBlocked 表示 metadata 已明确禁用位置查找能力。
// 这是可预期的部署能力状态；composition root 应装配结构化不可用 provider，
// 而非令整个 integration-service 无法启动。
var ErrLocationLookupCapabilityBlocked = errors.New(
	"integration location lookup capability is blocked",
)

// ResolvedLocationBinding 是启动期物化的单个位置能力绑定，绝不进入 API 响应。
type ResolvedLocationBinding struct {
	AdapterID string
	Endpoints map[string]string
	Secrets   map[string]string
	Timeout   time.Duration
}

// ResolveLocationLookup 只消费构建期生成的 Binding；缺失和材料不完整必须失败。
// 被 metadata 显式 blocked 的能力返回可辨识错误，交由 composition root 装配
// structured-unavailable provider，使未依赖位置能力的服务路径保持可用。
func ResolveLocationLookup(
	appEnv string,
	configProvider runtimeconfig.RuntimeConfigProvider,
) (ResolvedLocationBinding, error) {
	if configProvider == nil {
		return ResolvedLocationBinding{}, fmt.Errorf(
			"location provider binding has no runtime config provider",
		)
	}
	binding, found := integrationgenerated.ExternalProviderBindingFor(
		appEnv,
		LocationLookupCapabilityID,
	)
	if !found {
		return ResolvedLocationBinding{}, fmt.Errorf(
			"location provider binding is missing for environment=%s",
			appEnv,
		)
	}
	if binding.State != "enabled" {
		return ResolvedLocationBinding{}, fmt.Errorf(
			"%w for environment=%s",
			ErrLocationLookupCapabilityBlocked,
			appEnv,
		)
	}
	if strings.TrimSpace(binding.AdapterID) == "" || binding.TimeoutMilliseconds <= 0 {
		return ResolvedLocationBinding{}, fmt.Errorf(
			"location provider binding is incomplete for environment=%s",
			appEnv,
		)
	}

	endpoints := make(map[string]string, len(binding.EndpointEnvironmentKeys))
	for role, environmentKey := range binding.EndpointEnvironmentKeys {
		value, ok := configProvider.GetString(environmentKey)
		if !ok {
			return ResolvedLocationBinding{}, fmt.Errorf(
				"location provider endpoint material is unavailable for environment=%s role=%s",
				appEnv,
				role,
			)
		}
		endpoints[role] = value
	}
	if len(endpoints) == 0 {
		return ResolvedLocationBinding{}, fmt.Errorf(
			"location provider binding has no endpoint material for environment=%s",
			appEnv,
		)
	}

	secrets := make(map[string]string, len(binding.SecretEnvironmentKeys))
	for _, environmentKey := range binding.SecretEnvironmentKeys {
		value, ok := configProvider.GetString(environmentKey)
		if !ok {
			return ResolvedLocationBinding{}, fmt.Errorf(
				"location provider secret material is unavailable for environment=%s",
				appEnv,
			)
		}
		secrets[environmentKey] = value
	}
	return ResolvedLocationBinding{
		AdapterID: binding.AdapterID,
		Endpoints: endpoints,
		Secrets:   secrets,
		Timeout:   time.Duration(binding.TimeoutMilliseconds) * time.Millisecond,
	}, nil
}

func (b ResolvedLocationBinding) Endpoint(role string) (string, bool) {
	value, ok := b.Endpoints[role]
	return value, ok
}

func (b ResolvedLocationBinding) Secret(environmentKey string) (string, bool) {
	value, ok := b.Secrets[environmentKey]
	return value, ok
}
