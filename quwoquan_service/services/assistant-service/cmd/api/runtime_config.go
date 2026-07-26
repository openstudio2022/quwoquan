package main

import "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/infrastructure/runtimeconfig"

type redisPoolCfg = runtimeconfig.RedisPoolConfig
type redisSceneCfg = runtimeconfig.RedisSceneConfig
type config = runtimeconfig.Config
type userProfileCfg = runtimeconfig.UserProfileConfig
type serviceEgressCfg = runtimeconfig.ServiceEgressConfig

func resolveRuntimeIdentity() (serviceName, appEnv, configRoot, configVersion, imageVersion string, err error) {
	return runtimeconfig.ResolveRuntimeIdentity()
}

func loadRuntimeConfig(serviceName, appEnv, configRoot, configVersion string) (config, error) {
	return runtimeconfig.LoadRuntimeConfig(serviceName, appEnv, configRoot, configVersion)
}

func mergeConfigFile(cfg *config, path string) error {
	return runtimeconfig.MergeConfigFile(cfg, path)
}

func applyEnvOverrides(cfg *config) error {
	return runtimeconfig.ApplyEnvOverrides(cfg)
}
