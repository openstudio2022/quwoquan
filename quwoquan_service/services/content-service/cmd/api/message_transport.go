package main

import (
	"context"
	"fmt"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
)

func requireContentMessageTransport(
	ctx context.Context,
	environment string,
	router *rtredis.Router,
	sceneModes map[string]string,
) (runtimemessaging.ResolvedMessageTransport, error) {
	binding, bindingFound := contentgenerated.ExternalProviderBindingFor(
		environment,
		runtimemessaging.RuntimeMessageTransportCapability,
	)
	root, rootFound := contentgenerated.ExternalProviderBindingRootFor(
		runtimemessaging.RuntimeMessageTransportCapability,
		"content-service-api",
	)
	if !rootFound {
		return runtimemessaging.ResolvedMessageTransport{}, fmt.Errorf(
			"generated message transport root content-service-api is missing",
		)
	}
	return runtimemessaging.RequireConfiguredRedisMessageTransport(
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
}
