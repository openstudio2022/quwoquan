package bootstrap

import (
	"errors"
	"fmt"

	runtimeconfig "quwoquan_service/runtime/config"
	integrationconfig "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/infrastructure/runtimeconfig"
	locationproviderbinding "quwoquan_service/services/integration-service/internal/external_integration/location/infrastructure/providerbinding"
)

type config = integrationconfig.Config
type externalProviderConfig = integrationconfig.ExternalProviderConfig
type pushDeliveryProviderConfig = integrationconfig.PushDeliveryProviderConfig

func retiredEnvKeys() []string {
	return integrationconfig.RetiredEnvKeys()
}

func snapshotGuard(raw []byte) error {
	return integrationconfig.SnapshotGuard(raw)
}

// resolveIntegrationConfig 补齐领域下界、物化 release external provider binding
// 并做 integration 领域校验。它在骨架的 required 校验之后、任何观测栈与基础
// 设施连接之前执行，所以非法配置不会产生外部副作用。
func resolveIntegrationConfig(cfg *config) error {
	integrationconfig.NormalizeDefaults(cfg)
	materialized, err := integrationconfig.MaterializeReleaseExternalInteractionBindings(
		*cfg,
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
	if err != nil {
		return fmt.Errorf("external provider binding invalid: %w", err)
	}
	*cfg = materialized
	if err := integrationconfig.Validate(*cfg); err != nil {
		return err
	}
	return integrationconfig.ValidateResultRelayRedis(cfg.Environment, cfg.Redis.General)
}

// locationBindings 汇集三个 location capability 的绑定解析结果。capability
// 被环境判定为未启用时不是失败：对应 provider 装配成显式 unavailable，
// 由领域按 capability 语义回答，而不是让进程起不来。
type locationBindings struct {
	lookup        locationproviderbinding.ResolvedLocationBinding
	lookupErr     error
	lookupBlocked bool

	poi            locationproviderbinding.ResolvedLocationBinding
	poiErr         error
	poiUnavailable bool

	route            locationproviderbinding.ResolvedLocationBinding
	routeErr         error
	routeUnavailable bool
}

func resolveLocationBindings(cfg *config) (locationBindings, error) {
	provider := runtimeconfig.EnvRuntimeConfigProvider{}
	resolved := locationBindings{}

	resolved.lookup, resolved.lookupErr = locationproviderbinding.ResolveLocationLookup(
		cfg.Environment,
		provider,
	)
	resolved.lookupBlocked = errors.Is(
		resolved.lookupErr,
		locationproviderbinding.ErrLocationLookupCapabilityBlocked,
	)
	if resolved.lookupErr != nil && !resolved.lookupBlocked {
		return locationBindings{}, fmt.Errorf(
			"location provider binding invalid: %w", resolved.lookupErr,
		)
	}

	poiPolicy := cfg.Integration.PublicProvider.POI
	resolved.poi, resolved.poiErr = locationproviderbinding.ResolvePublicLocationCapability(
		cfg.Environment,
		locationproviderbinding.LocationPOISearchCapabilityID,
		provider,
		locationproviderbinding.PublicProviderRuntimePolicy{
			ConfigRef:          "config:integration.public_provider.poi",
			RatePolicyRef:      "config:integration.public_provider.poi",
			ProbePassed:        poiPolicy.ProbePassed,
			RateLimitPerSecond: poiPolicy.RateLimitPerSecond,
		},
	)
	resolved.poiUnavailable = publicLocationCapabilityUnavailable(resolved.poiErr)
	if resolved.poiErr != nil && !resolved.poiUnavailable {
		return locationBindings{}, fmt.Errorf("POI provider binding invalid: %w", resolved.poiErr)
	}

	routePolicy := cfg.Integration.PublicProvider.Route
	resolved.route, resolved.routeErr = locationproviderbinding.ResolvePublicLocationCapability(
		cfg.Environment,
		locationproviderbinding.LocationRouteReadCapabilityID,
		provider,
		locationproviderbinding.PublicProviderRuntimePolicy{
			ConfigRef:          "config:integration.public_provider.route",
			RatePolicyRef:      "config:integration.public_provider.route",
			ProbePassed:        routePolicy.ProbePassed,
			RateLimitPerSecond: routePolicy.RateLimitPerSecond,
		},
	)
	resolved.routeUnavailable = publicLocationCapabilityUnavailable(resolved.routeErr)
	if resolved.routeErr != nil && !resolved.routeUnavailable {
		return locationBindings{}, fmt.Errorf("route provider binding invalid: %w", resolved.routeErr)
	}
	return resolved, nil
}

func publicLocationCapabilityUnavailable(err error) bool {
	return errors.Is(err, locationproviderbinding.ErrPublicLocationCapabilityBlocked) ||
		errors.Is(err, locationproviderbinding.ErrPublicLocationProbeNotPassed)
}
