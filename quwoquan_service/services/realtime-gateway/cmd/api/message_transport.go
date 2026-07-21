package main

import (
	"context"
	"fmt"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	realtimegenerated "quwoquan_service/services/realtime-gateway/internal/generated"
)

const realtimeGatewayAPIMessageTransportRoot = "realtime-gateway-api"

func requireMessageTransport(
	ctx context.Context,
	environment string,
	router *rtredis.Router,
	sceneModes map[string]string,
) (runtimemessaging.MessageTransport, error) {
	descriptor, found := realtimegenerated.ExternalProviderBindingFor(
		environment,
		runtimemessaging.RuntimeMessageTransportCapability,
	)
	rootDescriptor, rootFound := realtimegenerated.ExternalProviderBindingRootFor(
		runtimemessaging.RuntimeMessageTransportCapability,
		realtimeGatewayAPIMessageTransportRoot,
	)
	if !rootFound {
		return nil, fmt.Errorf(
			"generated message transport root %s is missing",
			realtimeGatewayAPIMessageTransportRoot,
		)
	}
	resolved, err := runtimemessaging.RequireConfiguredRedisMessageTransport(
		ctx,
		environment,
		found,
		runtimemessaging.MessageTransportBinding{
			State:               descriptor.State,
			AdapterID:           descriptor.AdapterID,
			TimeoutMilliseconds: descriptor.TimeoutMilliseconds,
		},
		runtimemessaging.MessageTransportRoot{
			RootID:              rootDescriptor.RootID,
			RequiredRedisScenes: rootDescriptor.RequiredRedisScenes,
		},
		router,
		sceneModes,
	)
	if err != nil {
		return nil, err
	}
	realtime, ok := resolved.Scene("realtime")
	if !ok {
		return nil, fmt.Errorf(
			"message transport root %s is missing realtime scene",
			rootDescriptor.RootID,
		)
	}
	return runtimemessaging.NewRedisMessageTransportForRoot(
		rootDescriptor.RootID,
		descriptor.AdapterID,
		realtime,
		realtime,
	)
}
