package bootstrap

import (
	"context"
	"fmt"
	"strings"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	bindingdescriptor "quwoquan_service/services/search-service/generated/search/search_request_fact"
)

const searchAPIMessageTransportRoot = "search-service-api"

func requireSearchAPIMessageTransport(
	ctx context.Context,
	environment string,
	router *rtredis.Router,
	sceneModes map[string]string,
) (*runtimemessaging.RedisMessageTransport, error) {
	binding, found := bindingdescriptor.CompiledBindingFor(runtimemessaging.RuntimeMessageTransportCapability)
	resolved, err := runtimemessaging.RequireConfiguredRedisMessageTransport(
		ctx, environment, found,
		runtimemessaging.MessageTransportBinding{
			State: binding.State, AdapterID: binding.AdapterID,
			TimeoutMilliseconds: binding.TimeoutMilliseconds,
		},
		runtimemessaging.MessageTransportRoot{
			RootID:              searchAPIMessageTransportRoot,
			RequiredRedisScenes: binding.RequiredRedisScenes,
		},
		router, sceneModes,
	)
	if err != nil {
		return nil, err
	}
	if len(binding.RequiredRedisScenes) != 1 {
		return nil, fmt.Errorf("generated message transport root %s must declare exactly one Redis scene", searchAPIMessageTransportRoot)
	}
	scene, ok := resolved.Scene(strings.TrimSpace(binding.RequiredRedisScenes[0]))
	if !ok {
		return nil, fmt.Errorf("preflighted message transport root %s is missing its declared Redis scene", searchAPIMessageTransportRoot)
	}
	return runtimemessaging.NewRedisMessageTransportForRoot(
		searchAPIMessageTransportRoot, binding.AdapterID, scene, scene,
	)
}
