package main

import (
	"context"
	"fmt"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	opsgenerated "quwoquan_service/services/product-ops-service/internal/generated"
)

const productOpsAPIMessageTransportRoot = "product-ops-service-api"

func requireMessageTransport(
	ctx context.Context,
	environment string,
	router *rtredis.Router,
	sceneModes map[string]string,
) (runtimemessaging.MessageTransport, error) {
	descriptor, found := opsgenerated.ExternalProviderBindingFor(
		environment,
		runtimemessaging.RuntimeMessageTransportCapability,
	)
	rootDescriptor, rootFound := opsgenerated.ExternalProviderBindingRootFor(
		runtimemessaging.RuntimeMessageTransportCapability,
		productOpsAPIMessageTransportRoot,
	)
	if !rootFound {
		return nil, fmt.Errorf(
			"generated message transport root %s is missing",
			productOpsAPIMessageTransportRoot,
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
	general, ok := resolved.Scene("general")
	if !ok {
		return nil, fmt.Errorf(
			"message transport root %s is missing general scene",
			rootDescriptor.RootID,
		)
	}
	return runtimemessaging.NewRedisMessageTransportForRoot(
		rootDescriptor.RootID,
		descriptor.AdapterID,
		general,
		general,
	)
}
