package bootstrap

import (
	"context"
	"fmt"
	"strings"

	platformredis "quwoquan_service/internal/platform/redis"
	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	bindingdescriptor "quwoquan_service/services/integration-service/generated/external_integration/external_interaction"
	integrationconfig "quwoquan_service/services/integration-service/internal/external_integration/external_interaction/infrastructure/runtimeconfig"
)

const integrationMessageTransportRoot = "integration-service-api"

func buildIntegrationRedisRouter(
	cfg config,
) (*rtredis.Router, map[string]string, error) {
	if err := integrationconfig.ValidateResultRelayRedis(
		cfg.Environment,
		cfg.Redis.General,
	); err != nil {
		return nil, nil, err
	}
	base := rtredis.DefaultRouterConfig()
	generalScene := rtredis.SceneConfig{
		Mode:           cfg.Redis.General.Mode,
		Addr:           cfg.Redis.General.Addr,
		Addrs:          cfg.Redis.General.Addrs,
		Password:       cfg.Redis.General.Password,
		DB:             cfg.Redis.General.DB,
		TLS:            cfg.Redis.General.TLS,
		PoolSize:       cfg.Redis.General.Pool.Size,
		MinIdleConns:   cfg.Redis.General.Pool.MinIdle,
		ReadTimeoutMs:  cfg.Redis.General.Pool.ReadTimeoutMs,
		WriteTimeoutMs: cfg.Redis.General.Pool.WriteTimeoutMs,
		DialTimeoutMs:  cfg.Redis.General.Pool.DialTimeoutMs,
	}
	base.Scenes["general"] = generalScene
	return platformredis.MustNewRouter(base), map[string]string{
		"general": generalScene.Mode,
	}, nil
}

func requireIntegrationMessageTransport(
	ctx context.Context,
	environment string,
	router *rtredis.Router,
	sceneModes map[string]string,
) (*runtimemessaging.RedisMessageTransport, error) {
	binding, found := bindingdescriptor.CompiledBindingFor(runtimemessaging.RuntimeMessageTransportCapability)
	resolved, err := runtimemessaging.RequireConfiguredRedisMessageTransport(
		ctx,
		environment,
		found,
		runtimemessaging.MessageTransportBinding{
			State:               binding.State,
			AdapterID:           binding.AdapterID,
			TimeoutMilliseconds: binding.TimeoutMilliseconds,
		},
		runtimemessaging.MessageTransportRoot{
			RootID:              integrationMessageTransportRoot,
			RequiredRedisScenes: binding.RequiredRedisScenes,
		},
		router,
		sceneModes,
	)
	if err != nil {
		return nil, err
	}
	if len(binding.RequiredRedisScenes) != 1 {
		return nil, fmt.Errorf(
			"generated message transport root %s must declare exactly one Redis scene",
			integrationMessageTransportRoot,
		)
	}
	scene, ok := resolved.Scene(strings.TrimSpace(binding.RequiredRedisScenes[0]))
	if !ok {
		return nil, fmt.Errorf(
			"preflighted message transport root %s is missing its declared Redis scene",
			integrationMessageTransportRoot,
		)
	}
	return runtimemessaging.NewRedisMessageTransportForRoot(
		integrationMessageTransportRoot,
		binding.AdapterID,
		scene,
		scene,
	)
}
