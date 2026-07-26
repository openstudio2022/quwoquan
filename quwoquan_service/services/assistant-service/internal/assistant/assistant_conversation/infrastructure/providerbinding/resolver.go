package providerbinding

import (
	"fmt"
	"strings"
	"time"

	runtimeconfig "quwoquan_service/runtime/config"
	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_conversation"
)

// ResolvedBinding is the startup-only materialization of one compiler-selected
// external capability binding. It is never exposed through assistant results.
type ResolvedBinding struct {
	AdapterID string
	Endpoints map[string]string
	Secrets   map[string]string
	Timeout   time.Duration
}

// Resolve requires an enabled, complete generated binding and its referenced
// environment material. It never guesses an adapter or provider fallback.
func Resolve(
	appEnv string,
	capabilityID string,
	configProvider runtimeconfig.RuntimeConfigProvider,
) (ResolvedBinding, error) {
	if configProvider == nil {
		return ResolvedBinding{}, fmt.Errorf("provider binding %s has no runtime config provider", capabilityID)
	}
	binding, found := assistantgenerated.ExternalProviderBindingFor(appEnv, capabilityID)
	if !found {
		return ResolvedBinding{}, fmt.Errorf(
			"provider binding is missing for environment=%s capability=%s",
			appEnv,
			capabilityID,
		)
	}
	if binding.State != "enabled" {
		return ResolvedBinding{}, fmt.Errorf(
			"provider binding is not enabled for environment=%s capability=%s",
			appEnv,
			capabilityID,
		)
	}
	if strings.TrimSpace(binding.AdapterID) == "" || binding.TimeoutMilliseconds <= 0 {
		return ResolvedBinding{}, fmt.Errorf(
			"provider binding is incomplete for environment=%s capability=%s",
			appEnv,
			capabilityID,
		)
	}

	endpoints := make(map[string]string, len(binding.EndpointEnvironmentKeys))
	for role, environmentKey := range binding.EndpointEnvironmentKeys {
		value, ok := configProvider.GetString(environmentKey)
		if !ok {
			return ResolvedBinding{}, fmt.Errorf(
				"provider endpoint material is unavailable for environment=%s capability=%s role=%s",
				appEnv,
				capabilityID,
				role,
			)
		}
		endpoints[role] = value
	}
	if len(endpoints) == 0 {
		return ResolvedBinding{}, fmt.Errorf(
			"provider binding has no endpoint material for environment=%s capability=%s",
			appEnv,
			capabilityID,
		)
	}

	secrets := make(map[string]string, len(binding.SecretEnvironmentKeys))
	for _, environmentKey := range binding.SecretEnvironmentKeys {
		value, ok := configProvider.GetString(environmentKey)
		if !ok {
			return ResolvedBinding{}, fmt.Errorf(
				"provider secret material is unavailable for environment=%s capability=%s",
				appEnv,
				capabilityID,
			)
		}
		secrets[environmentKey] = value
	}
	return ResolvedBinding{
		AdapterID: binding.AdapterID,
		Endpoints: endpoints,
		Secrets:   secrets,
		Timeout:   time.Duration(binding.TimeoutMilliseconds) * time.Millisecond,
	}, nil
}

func (b ResolvedBinding) Endpoint(role string) (string, bool) {
	value, ok := b.Endpoints[role]
	return value, ok
}

func (b ResolvedBinding) Secret(environmentKey string) (string, bool) {
	value, ok := b.Secrets[environmentKey]
	return value, ok
}
