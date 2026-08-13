package bootstrap

import (
	"context"
	"fmt"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	bindingdescriptor "quwoquan_service/services/chat-service/generated/chat/conversation"
)

func requireChatMessageTransport(
	ctx context.Context,
	environment string,
	router *rtredis.Router,
	sceneModes map[string]string,
) (*runtimemessaging.RedisMessageTransport, *runtimemessaging.RedisMessageTransport, error) {
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
			RootID: "chat-service-api", RequiredRedisScenes: binding.RequiredRedisScenes,
		},
		router, sceneModes,
	)
	if err != nil {
		return nil, nil, err
	}
	realtime, ok := resolved.Scene("realtime")
	if !ok {
		return nil, nil, fmt.Errorf("message transport root chat-service-api is missing realtime scene")
	}
	durable, ok := resolved.Scene("general")
	if !ok {
		return nil, nil, fmt.Errorf("message transport root chat-service-api is missing general scene")
	}
	transport, err := runtimemessaging.NewRedisMessageTransportForRoot(
		"chat-service-api", messageBinding.AdapterID, realtime, durable,
	)
	if err != nil {
		return nil, nil, err
	}
	resumeTransport, err := runtimemessaging.NewRedisMessageTransportForRoot(
		"chat-service-api-resume", messageBinding.AdapterID, realtime, realtime,
	)
	if err != nil {
		return nil, nil, err
	}
	return transport, resumeTransport, nil
}
