package main

import (
	"context"
	"fmt"
	"strings"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	usergenerated "quwoquan_service/services/user-service/internal/generated"
)

// newUserMessageTransport resolves the compiler-selected runtime binding before
// exposing the provider-neutral transport to user-domain event adapters.
func newUserMessageTransport(
	ctx context.Context,
	environment string,
	router *rtredis.Router,
	cfg config,
) (runtimemessaging.MessageTransport, error) {
	binding, bindingFound := usergenerated.ExternalProviderBindingFor(
		environment,
		runtimemessaging.RuntimeMessageTransportCapability,
	)
	root, rootFound := usergenerated.ExternalProviderBindingRootFor(
		runtimemessaging.RuntimeMessageTransportCapability,
		"user-service-api",
	)
	if !rootFound {
		return nil, fmt.Errorf(
			"generated message transport root user-service-api is missing",
		)
	}
	sceneModes := map[string]string{
		"general":  cfg.Redis.General.Mode,
		"realtime": cfg.Redis.Realtime.Mode,
	}
	// Keep the preflight scene modes aligned with buildRedisRouter: realtime
	// inherits general when the service config does not override it.
	if strings.TrimSpace(sceneModes["realtime"]) == "" {
		sceneModes["realtime"] = sceneModes["general"]
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
	realtime, ok := resolved.Scene("realtime")
	if !ok {
		return nil, fmt.Errorf(
			"message transport root %s is missing realtime scene",
			root.RootID,
		)
	}
	durable, ok := resolved.Scene("general")
	if !ok {
		return nil, fmt.Errorf(
			"message transport root %s is missing general scene",
			root.RootID,
		)
	}
	return runtimemessaging.NewRedisMessageTransportForRoot(
		root.RootID,
		binding.AdapterID,
		realtime,
		durable,
	)
}
