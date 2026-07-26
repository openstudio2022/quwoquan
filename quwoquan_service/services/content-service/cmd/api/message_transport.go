package main

import (
	"context"
	"fmt"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	bindingdescriptor "quwoquan_service/services/content-service/generated/content/post"
)

func requireContentMessageTransport(
	ctx context.Context,
	environment string,
	router *rtredis.Router,
	sceneModes map[string]string,
) (*runtimemessaging.RedisMessageTransport, error) {
	binding, found := bindingdescriptor.ExternalProviderBindingFor(
		environment,
		runtimemessaging.RuntimeMessageTransportCapability,
	)
	messageBinding := runtimemessaging.MessageTransportBinding{
		State: binding.State, AdapterID: binding.AdapterID,
		TimeoutMilliseconds: binding.TimeoutMilliseconds,
	}
	resolved, err := runtimemessaging.RequireConfiguredRedisMessageTransport(
		ctx, environment, found, messageBinding,
		runtimemessaging.MessageTransportRoot{
			RootID: "content-service-api", RequiredRedisScenes: binding.RequiredRedisScenes,
		},
		router, sceneModes,
	)
	if err != nil {
		return nil, err
	}
	realtime, ok := resolved.Scene("realtime")
	if !ok {
		return nil, fmt.Errorf("message transport root content-service-api is missing realtime scene")
	}
	durable, ok := resolved.Scene("general")
	if !ok {
		return nil, fmt.Errorf("message transport root content-service-api is missing general scene")
	}
	return runtimemessaging.NewRedisMessageTransportForRoot(
		"content-service-api", messageBinding.AdapterID, realtime, durable,
	)
}
