package main

import (
	"context"
	"fmt"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	bindingdescriptor "quwoquan_service/services/rtc-service/generated/rtc/call_session"
)

type rtcMessageTransport interface {
	runtimemessaging.MessageTransport
	runtimemessaging.DurableDeliveryTransport
}

func requireRTCMessageTransport(
	ctx context.Context,
	environment string,
	router *rtredis.Router,
	sceneModes map[string]string,
) (rtcMessageTransport, error) {
	const rootID = "rtc-service-api"
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
			RootID: rootID, RequiredRedisScenes: binding.RequiredRedisScenes,
		},
		router, sceneModes,
	)
	if err != nil {
		return nil, err
	}
	realtime, found := resolved.Scene("realtime")
	if !found {
		return nil, fmt.Errorf("message transport root %s is missing realtime scene", rootID)
	}
	durable, found := resolved.Scene("general")
	if !found {
		return nil, fmt.Errorf("message transport root %s is missing general scene", rootID)
	}
	return runtimemessaging.NewRedisMessageTransportForRoot(
		rootID, binding.AdapterID, realtime, durable,
	)
}
