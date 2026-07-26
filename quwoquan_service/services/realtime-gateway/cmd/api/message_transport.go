package main

import (
	"context"
	"fmt"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	bindingdescriptor "quwoquan_service/services/realtime-gateway/generated/realtime/connection"
)

const realtimeGatewayAPIMessageTransportRoot = "realtime-gateway-api"

func requireMessageTransport(
	ctx context.Context,
	environment string,
	router *rtredis.Router,
	sceneModes map[string]string,
) (runtimemessaging.MessageTransport, error) {
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
			RootID:              realtimeGatewayAPIMessageTransportRoot,
			RequiredRedisScenes: binding.RequiredRedisScenes,
		},
		router, sceneModes,
	)
	if err != nil {
		return nil, err
	}
	realtime, ok := resolved.Scene("realtime")
	if !ok {
		return nil, fmt.Errorf("message transport root %s is missing realtime scene", realtimeGatewayAPIMessageTransportRoot)
	}
	return runtimemessaging.NewRedisMessageTransportForRoot(
		realtimeGatewayAPIMessageTransportRoot, binding.AdapterID, realtime, realtime,
	)
}
