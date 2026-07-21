package main

import (
	"context"
	"fmt"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	chatgenerated "quwoquan_service/services/chat-service/internal/generated"
)

func requireChatMessageTransport(
	ctx context.Context,
	environment string,
	router *rtredis.Router,
	sceneModes map[string]string,
) (runtimemessaging.ResolvedMessageTransport, error) {
	binding, bindingFound := chatgenerated.ExternalProviderBindingFor(
		environment,
		runtimemessaging.RuntimeMessageTransportCapability,
	)
	root, rootFound := chatgenerated.ExternalProviderBindingRootFor(
		runtimemessaging.RuntimeMessageTransportCapability,
		"chat-service-api",
	)
	if !rootFound {
		return runtimemessaging.ResolvedMessageTransport{}, fmt.Errorf(
			"generated message transport root chat-service-api is missing",
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
