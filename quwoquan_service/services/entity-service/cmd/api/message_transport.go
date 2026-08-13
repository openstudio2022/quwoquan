package bootstrap

import (
	"context"
	"fmt"
	"strings"

	platformredis "quwoquan_service/internal/platform/redis"
	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	bindingdescriptor "quwoquan_service/services/entity-service/generated/entity_homepage/homepage"
)

const entityAPIMessageTransportRoot = "entity-service-api"

func buildEntityMessageTransportRouter(
	environment string,
	cfg config,
) (*rtredis.Router, map[string]string, error) {
	addr := getenvOrDefault("ENTITY_REDIS_ADDR", cfg.Redis.Addr)
	mode := "standalone"
	if strings.TrimSpace(addr) == "" {
		if strings.TrimSpace(environment) != "alpha" {
			return nil, nil, fmt.Errorf(
				"ENTITY_REDIS_ADDR is required for message transport when APP_ENV=%s",
				environment,
			)
		}
		mode = "memory"
	}
	router, err := platformredis.NewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general": {
				Mode:     mode,
				Addr:     addr,
				Password: getenvOrDefault("ENTITY_REDIS_PASSWORD", cfg.Redis.Password),
				DB:       cfg.Redis.DB,
			},
		},
		DefaultScene: "general",
	})
	if err != nil {
		return nil, nil, fmt.Errorf("entity message transport Redis router: %w", err)
	}
	return router, map[string]string{"general": mode}, nil
}

func requireEntityAPIMessageTransport(
	ctx context.Context,
	environment string,
	router *rtredis.Router,
	sceneModes map[string]string,
) (*runtimemessaging.RedisMessageTransport, error) {
	binding, found := bindingdescriptor.ExternalProviderBindingFor(
		environment,
		runtimemessaging.RuntimeMessageTransportCapability,
	)
	resolved, err := runtimemessaging.RequireConfiguredRedisMessageTransport(
		ctx, environment, found,
		runtimemessaging.MessageTransportBinding{
			State: binding.State, AdapterID: binding.AdapterID,
			TimeoutMilliseconds: binding.TimeoutMilliseconds,
		},
		runtimemessaging.MessageTransportRoot{
			RootID:              entityAPIMessageTransportRoot,
			RequiredRedisScenes: binding.RequiredRedisScenes,
		},
		router, sceneModes,
	)
	if err != nil {
		return nil, err
	}
	if len(binding.RequiredRedisScenes) != 1 {
		return nil, fmt.Errorf("generated message transport root %s must declare exactly one Redis scene", entityAPIMessageTransportRoot)
	}
	scene, ok := resolved.Scene(strings.TrimSpace(binding.RequiredRedisScenes[0]))
	if !ok {
		return nil, fmt.Errorf("preflighted message transport root %s is missing its declared Redis scene", entityAPIMessageTransportRoot)
	}
	return runtimemessaging.NewRedisMessageTransportForRoot(
		entityAPIMessageTransportRoot, binding.AdapterID, scene, scene,
	)
}
