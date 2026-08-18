package bootstrap

import (
	"context"
	"fmt"
	"strings"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	bindingdescriptor "quwoquan_service/services/tag-service/generated/tag/tag_node_view"
)

func requireTagAPIMessageTransport(
	ctx context.Context,
	environment string,
	router *rtredis.Router,
	sceneModes map[string]string,
) (*runtimemessaging.RedisMessageTransport, error) {
	binding, found := bindingdescriptor.CompiledBindingFor(runtimemessaging.RuntimeMessageTransportCapability)
	rootID := bindingdescriptor.ExternalProviderBindingObject
	resolved, err := runtimemessaging.RequireConfiguredRedisMessageTransport(
		ctx,
		environment,
		found,
		runtimemessaging.MessageTransportBinding{
			State:               binding.State,
			AdapterID:           binding.AdapterID,
			TimeoutMilliseconds: binding.TimeoutMilliseconds,
		},
		runtimemessaging.MessageTransportRoot{
			RootID:              rootID,
			RequiredRedisScenes: binding.RequiredRedisScenes,
		},
		router,
		sceneModes,
	)
	if err != nil {
		return nil, err
	}
	if len(binding.RequiredRedisScenes) != 1 {
		return nil, fmt.Errorf(
			"generated message transport root %s must declare exactly one Redis scene",
			rootID,
		)
	}
	sceneName := strings.TrimSpace(binding.RequiredRedisScenes[0])
	scene, ok := resolved.Scene(sceneName)
	if !ok {
		return nil, fmt.Errorf(
			"preflighted message transport root %s is missing scene %s",
			rootID,
			sceneName,
		)
	}
	return runtimemessaging.NewRedisMessageTransportForRoot(
		rootID,
		binding.AdapterID,
		scene,
		scene,
	)
}
