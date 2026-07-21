package main

import (
	"context"
	"fmt"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	notificationgenerated "quwoquan_service/services/notification-service/internal/generated"
)

const notificationAPIMessageTransportRoot = "notification-service-api"

func requireNotificationAPIMessageTransport(
	ctx context.Context,
	environment string,
	router *rtredis.Router,
	sceneModes map[string]string,
) (*runtimemessaging.RedisMessageTransport, error) {
	descriptor, found := notificationgenerated.ExternalProviderBindingFor(
		environment,
		runtimemessaging.RuntimeMessageTransportCapability,
	)
	rootDescriptor, rootFound := notificationgenerated.ExternalProviderBindingRootFor(
		runtimemessaging.RuntimeMessageTransportCapability,
		notificationAPIMessageTransportRoot,
	)
	if !rootFound {
		return nil, fmt.Errorf(
			"generated message transport root %s is missing",
			notificationAPIMessageTransportRoot,
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
	realtime, ok := resolved.Scene("realtime")
	if !ok {
		return nil, fmt.Errorf(
			"generated message transport root %s is missing realtime scene",
			rootDescriptor.RootID,
		)
	}
	durable, ok := resolved.Scene("general")
	if !ok {
		return nil, fmt.Errorf(
			"generated message transport root %s is missing general scene",
			rootDescriptor.RootID,
		)
	}
	return runtimemessaging.NewRedisMessageTransportForRoot(
		rootDescriptor.RootID,
		descriptor.AdapterID,
		realtime,
		durable,
	)
}
