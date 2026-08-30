package bootstrap

import (
	"context"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/runtime/servicekit"
	bindingdescriptor "quwoquan_service/services/entity-service/generated/entity_homepage/homepage"
)

const entityAPIMessageTransportRoot = "entity-service-api"

// requireEntityAPIMessageTransport 从本服务 generated descriptor 读出编译期
// binding，交给 servicekit 完成 preflight 与传输构造。descriptor 读取必须留在
// 服务侧：servicekit 不 import generated/**。
func requireEntityAPIMessageTransport(
	ctx context.Context,
	environment string,
	router *rtredis.Router,
	sceneModes map[string]string,
) (*runtimemessaging.RedisMessageTransport, error) {
	binding, found := bindingdescriptor.CompiledBindingFor(runtimemessaging.RuntimeMessageTransportCapability)
	return servicekit.NewMessageTransport(
		ctx, environment,
		servicekit.MessageTransportSpec{
			RootID:       entityAPIMessageTransportRoot,
			BindingFound: found,
			Binding: runtimemessaging.MessageTransportBinding{
				State:               binding.State,
				AdapterID:           binding.AdapterID,
				TimeoutMilliseconds: binding.TimeoutMilliseconds,
			},
			RequiredRedisScenes: binding.RequiredRedisScenes,
		},
		router, sceneModes,
	)
}
