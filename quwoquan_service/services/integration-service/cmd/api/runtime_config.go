package bootstrap

import integrationconfig "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/infrastructure/runtimeconfig"

type config = integrationconfig.Config
type externalProviderConfig = integrationconfig.ExternalProviderConfig
type pushDeliveryProviderConfig = integrationconfig.PushDeliveryProviderConfig

func loadRuntimeConfig() (config, error) {
	return integrationconfig.Load()
}

func normalizeDefaults(cfg *config) {
	integrationconfig.NormalizeDefaults(cfg)
}

func validateRuntimeConfig(cfg config) error {
	return integrationconfig.Validate(cfg)
}

func applyEnvOverrides(cfg *config) error {
	return integrationconfig.ApplyEnvOverrides(cfg)
}
