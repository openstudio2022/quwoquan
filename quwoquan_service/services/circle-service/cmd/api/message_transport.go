package main

import (
	"context"
	"fmt"
	"strings"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	circlegenerated "quwoquan_service/services/circle-service/internal/generated"
)

const circleAPIMessageTransportRoot = "circle-service-api"

func requireCircleAPIMessageTransport(
	ctx context.Context,
	environment string,
	router *rtredis.Router,
	sceneModes map[string]string,
) (*runtimemessaging.RedisMessageTransport, error) {
	binding, bindingFound := circlegenerated.ExternalProviderBindingFor(
		environment,
		runtimemessaging.RuntimeMessageTransportCapability,
	)
	root, rootFound := circlegenerated.ExternalProviderBindingRootFor(
		runtimemessaging.RuntimeMessageTransportCapability,
		circleAPIMessageTransportRoot,
	)
	if !rootFound {
		return nil, fmt.Errorf(
			"generated message transport root %s is missing",
			circleAPIMessageTransportRoot,
		)
	}
	resolved, err := runtimemessaging.RequireConfiguredRedisMessageTransport(
		ctx,
		environment,
		bindingFound,
		runtimemessaging.MessageTransportBinding{
			State:               binding.State,
			AdapterID:           binding.AdapterID,
			TimeoutMilliseconds: binding.TimeoutMilliseconds,
		},
		runtimemessaging.MessageTransportRoot{
			RootID:              root.RootID,
			RequiredRedisScenes: root.RequiredRedisScenes,
		},
		router,
		sceneModes,
	)
	if err != nil {
		return nil, err
	}
	if len(root.RequiredRedisScenes) != 1 {
		return nil, fmt.Errorf(
			"generated message transport root %s must declare exactly one Redis scene",
			root.RootID,
		)
	}
	scene, ok := resolved.Scene(strings.TrimSpace(root.RequiredRedisScenes[0]))
	if !ok {
		return nil, fmt.Errorf(
			"preflighted message transport root %s is missing its declared Redis scene",
			root.RootID,
		)
	}
	return runtimemessaging.NewRedisMessageTransportForRoot(
		root.RootID,
		binding.AdapterID,
		scene,
		scene,
	)
}
