package main

import (
	"context"
	"fmt"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	rtcgenerated "quwoquan_service/services/rtc-service/internal/generated"
)

func requireRTCMessageTransport(
	ctx context.Context,
	environment string,
	router *rtredis.Router,
	sceneModes map[string]string,
) (runtimemessaging.MessageTransport, error) {
	binding, bindingFound := rtcgenerated.ExternalProviderBindingFor(
		environment,
		runtimemessaging.RuntimeMessageTransportCapability,
	)
	root, rootFound := rtcgenerated.ExternalProviderBindingRootFor(
		runtimemessaging.RuntimeMessageTransportCapability,
		"rtc-service-api",
	)
	if !rootFound {
		return nil, fmt.Errorf(
			"generated message transport root rtc-service-api is missing",
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
	realtime, found := resolved.Scene("realtime")
	if !found {
		return nil, fmt.Errorf("message transport root %s is missing realtime scene", root.RootID)
	}
	durable, found := resolved.Scene("general")
	if !found {
		return nil, fmt.Errorf("message transport root %s is missing general scene", root.RootID)
	}
	return runtimemessaging.NewRedisMessageTransportForRoot(
		root.RootID,
		binding.AdapterID,
		realtime,
		durable,
	)
}
