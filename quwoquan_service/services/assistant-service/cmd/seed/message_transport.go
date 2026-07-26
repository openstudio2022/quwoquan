package main

import (
	"context"
	"fmt"
	"strings"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	bindingdescriptor "quwoquan_service/services/assistant-service/generated/assistant/assistant_conversation"
)

const assistantSeedMessageTransportRoot = "assistant-service-seed"

func requireAssistantSeedMessageTransport(
	ctx context.Context,
	environment string,
	router *rtredis.Router,
	sceneModes map[string]string,
) (*runtimemessaging.RedisMessageTransport, error) {
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
			RootID:              assistantSeedMessageTransportRoot,
			RequiredRedisScenes: binding.RequiredRedisScenes,
		},
		router, sceneModes,
	)
	if err != nil {
		return nil, err
	}
	if len(binding.RequiredRedisScenes) != 1 {
		return nil, fmt.Errorf("generated message transport root %s must declare exactly one Redis scene", assistantSeedMessageTransportRoot)
	}
	scene, ok := resolved.Scene(strings.TrimSpace(binding.RequiredRedisScenes[0]))
	if !ok {
		return nil, fmt.Errorf("preflighted message transport root %s is missing its declared Redis scene", assistantSeedMessageTransportRoot)
	}
	return runtimemessaging.NewRedisMessageTransportForRoot(
		assistantSeedMessageTransportRoot, binding.AdapterID, scene, scene,
	)
}
