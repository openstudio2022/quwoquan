package bootstrap

import (
	"context"
	"fmt"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	bindingdescriptor "quwoquan_service/services/user-service/generated/account/user_account"
)

// newUserMessageTransport resolves the compiler-selected runtime binding before
// exposing the provider-neutral transport to user-domain event adapters.
// sceneModes 是装配后各 scene 的**解析后** mode（含缺地址回落 memory 的结果），
// 由 servicekit 的 Redis 装配返回：preflight 判定「是否接到真实 Redis」必须看
// 实际装配结果，看快照原文会让缺地址的 scene 通过 preflight 后落 memory。
func newUserMessageTransport(
	ctx context.Context,
	environment string,
	router *rtredis.Router,
	sceneModes map[string]string,
) (runtimemessaging.MessageTransport, error) {
	const rootID = "user-service-api"
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
