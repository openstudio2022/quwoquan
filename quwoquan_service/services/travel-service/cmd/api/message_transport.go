package main

import (
	"context"
	"fmt"
	"strings"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	bindingdescriptor "quwoquan_service/services/travel-service/generated/travel/trip_plan"
)

const travelAPIMessageTransportRoot = "travel-service-api"

func requireTravelAPIMessageTransport(
	ctx context.Context,
	environment string,
	router *rtredis.Router,
	sceneModes map[string]string,
) (*runtimemessaging.RedisMessageTransport, error) {
	binding, found := bindingdescriptor.ExternalProviderBindingFor(
		environment, runtimemessaging.RuntimeMessageTransportCapability,
	)
	resolved, err := runtimemessaging.RequireConfiguredRedisMessageTransport(
		ctx, environment, found,
		runtimemessaging.MessageTransportBinding{
			State: binding.State, AdapterID: binding.AdapterID,
			TimeoutMilliseconds: binding.TimeoutMilliseconds,
		},
		runtimemessaging.MessageTransportRoot{
			RootID:              travelAPIMessageTransportRoot,
			RequiredRedisScenes: binding.RequiredRedisScenes,
		},
		router, sceneModes,
	)
	if err != nil {
		return nil, err
	}
	if len(binding.RequiredRedisScenes) != 1 {
		return nil, fmt.Errorf(
			"generated message transport root %s must declare exactly one Redis scene",
			travelAPIMessageTransportRoot,
		)
	}
	sceneName := strings.TrimSpace(binding.RequiredRedisScenes[0])
	scene, found := resolved.Scene(sceneName)
	if !found {
		return nil, fmt.Errorf(
			"preflighted message transport root %s is missing scene %s",
			travelAPIMessageTransportRoot,
			sceneName,
		)
	}
	return runtimemessaging.NewRedisMessageTransportForRoot(
		travelAPIMessageTransportRoot, binding.AdapterID, scene, scene,
	)
}
