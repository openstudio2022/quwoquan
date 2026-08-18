package bootstrap

import (
	"context"
	"fmt"
	"strings"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	bindingdescriptor "quwoquan_service/services/user-service/generated/account/user_account"
)

// newUserMessageTransport resolves the compiler-selected runtime binding before
// exposing the provider-neutral transport to user-domain event adapters.
func newUserMessageTransport(
	ctx context.Context,
	environment string,
	router *rtredis.Router,
	cfg config,
) (runtimemessaging.MessageTransport, error) {
	const rootID = "user-service-api"
	sceneModes := map[string]string{
		"general":  cfg.Redis.General.Mode,
		"realtime": cfg.Redis.Realtime.Mode,
	}
	if strings.TrimSpace(sceneModes["realtime"]) == "" {
		sceneModes["realtime"] = sceneModes["general"]
	}
	binding, found := bindingdescriptor.CompiledBindingFor(runtimemessaging.RuntimeMessageTransportCapability)
	resolved, err := runtimemessaging.RequireConfiguredRedisMessageTransport(
		ctx,
		environment,
		found,
		runtimemessaging.MessageTransportBinding{
			State: binding.State, AdapterID: binding.AdapterID,
			TimeoutMilliseconds: binding.TimeoutMilliseconds,
		},
		runtimemessaging.MessageTransportRoot{
			RootID: rootID, RequiredRedisScenes: binding.RequiredRedisScenes,
		},
		router,
		sceneModes,
	)
	if err != nil {
		return nil, err
	}
	realtime, ok := resolved.Scene("realtime")
	if !ok {
		return nil, fmt.Errorf("message transport root %s is missing realtime scene", rootID)
	}
	durable, ok := resolved.Scene("general")
	if !ok {
		return nil, fmt.Errorf("message transport root %s is missing general scene", rootID)
	}
	return runtimemessaging.NewRedisMessageTransportForRoot(
		rootID, binding.AdapterID, realtime, durable,
	)
}
