package bootstrap

import (
	"context"
	"fmt"
	"strings"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	bindingdescriptor "quwoquan_service/services/circle-service/generated/circle_management/circle"
)

const circleAPIMessageTransportRoot = "circle-service-api"

func requireCircleAPIMessageTransport(
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
			RootID:              circleAPIMessageTransportRoot,
			RequiredRedisScenes: binding.RequiredRedisScenes,
		},
		router, sceneModes,
	)
	if err != nil {
		return nil, err
	}
	if len(binding.RequiredRedisScenes) != 1 {
		return nil, fmt.Errorf("generated message transport root %s must declare exactly one Redis scene", circleAPIMessageTransportRoot)
	}
	scene, ok := resolved.Scene(strings.TrimSpace(binding.RequiredRedisScenes[0]))
	if !ok {
		return nil, fmt.Errorf("preflighted message transport root %s is missing its declared Redis scene", circleAPIMessageTransportRoot)
	}
	return runtimemessaging.NewRedisMessageTransportForRoot(
		circleAPIMessageTransportRoot, binding.AdapterID, scene, scene,
	)
}
