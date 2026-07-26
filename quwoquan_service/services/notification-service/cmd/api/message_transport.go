package main

import (
	"context"
	"fmt"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	bindingdescriptor "quwoquan_service/services/notification-service/generated/notification_delivery/notification"
)

const notificationAPIMessageTransportRoot = "notification-service-api"

func requireNotificationAPIMessageTransport(
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
			RootID:              notificationAPIMessageTransportRoot,
			RequiredRedisScenes: binding.RequiredRedisScenes,
		},
		router, sceneModes,
	)
	if err != nil {
		return nil, err
	}
	realtime, ok := resolved.Scene("realtime")
	if !ok {
		return nil, fmt.Errorf("generated message transport root %s is missing realtime scene", notificationAPIMessageTransportRoot)
	}
	durable, ok := resolved.Scene("general")
	if !ok {
		return nil, fmt.Errorf("generated message transport root %s is missing general scene", notificationAPIMessageTransportRoot)
	}
	return runtimemessaging.NewRedisMessageTransportForRoot(
		notificationAPIMessageTransportRoot, binding.AdapterID, realtime, durable,
	)
}
