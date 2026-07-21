package main

import (
	"context"
	"fmt"
	"strings"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	searchgenerated "quwoquan_service/services/search-service/internal/generated"
)

const searchAPIMessageTransportRoot = "search-service-api"

func requireSearchAPIMessageTransport(
	ctx context.Context,
	environment string,
	router *rtredis.Router,
	sceneModes map[string]string,
) (*runtimemessaging.RedisMessageTransport, error) {
	descriptor, found := searchgenerated.ExternalProviderBindingFor(
		environment,
		runtimemessaging.RuntimeMessageTransportCapability,
	)
	rootDescriptor, rootFound := searchgenerated.ExternalProviderBindingRootFor(
		runtimemessaging.RuntimeMessageTransportCapability,
		searchAPIMessageTransportRoot,
	)
	if !rootFound {
		return nil, fmt.Errorf(
			"generated message transport root %s is missing",
			searchAPIMessageTransportRoot,
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
	if len(rootDescriptor.RequiredRedisScenes) != 1 {
		return nil, fmt.Errorf(
			"generated message transport root %s must declare exactly one Redis scene",
			rootDescriptor.RootID,
		)
	}
	scene, ok := resolved.Scene(
		strings.TrimSpace(rootDescriptor.RequiredRedisScenes[0]),
	)
	if !ok {
		return nil, fmt.Errorf(
			"preflighted message transport root %s is missing its declared Redis scene",
			rootDescriptor.RootID,
		)
	}
	return runtimemessaging.NewRedisMessageTransportForRoot(
		rootDescriptor.RootID,
		descriptor.AdapterID,
		scene,
		scene,
	)
}
