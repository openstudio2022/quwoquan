package servicekit

import (
	"context"
	"fmt"
	"strings"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
)

// MessageTransportSpec 承载消息传输装配所需的全部 generated 输入。
// binding 由服务 bootstrap 从自己的 generated descriptor 包读出后以值对象传入，
// servicekit 不 import 任何 generated/**。
type MessageTransportSpec struct {
	// RootID 是该服务在 descriptor 中声明的静态组合根。
	RootID string
	// BindingFound 对应 generated CompiledBindingFor 的第二返回值。
	BindingFound bool
	Binding      runtimemessaging.MessageTransportBinding
	// RequiredRedisScenes 来自 generated binding 的 scene 声明。
	RequiredRedisScenes []string
}

// NewMessageTransport 用 generated binding 值对象完成消息传输 preflight 并
// 构造 Redis 消息传输。失败即失败：任何 preflight 不通过都不允许降级为
// WARN、memory 或跳过消费。
func NewMessageTransport(
	ctx context.Context,
	environment string,
	spec MessageTransportSpec,
	router *rtredis.Router,
	sceneModes map[string]string,
) (*runtimemessaging.RedisMessageTransport, error) {
	rootID := strings.TrimSpace(spec.RootID)
	if rootID == "" {
		return nil, fmt.Errorf("message transport spec requires a root ID")
	}
	resolved, err := runtimemessaging.RequireConfiguredRedisMessageTransport(
		ctx, environment, spec.BindingFound,
		spec.Binding,
		runtimemessaging.MessageTransportRoot{
			RootID:              rootID,
			RequiredRedisScenes: spec.RequiredRedisScenes,
		},
		router, sceneModes,
	)
	if err != nil {
		return nil, err
	}
	if len(spec.RequiredRedisScenes) != 1 {
		return nil, fmt.Errorf(
			"generated message transport root %s must declare exactly one Redis scene",
			rootID,
		)
	}
	scene, ok := resolved.Scene(strings.TrimSpace(spec.RequiredRedisScenes[0]))
	if !ok {
		return nil, fmt.Errorf(
			"preflighted message transport root %s is missing its declared Redis scene",
			rootID,
		)
	}
	return runtimemessaging.NewRedisMessageTransportForRoot(
		rootID, spec.Binding.AdapterID, scene, scene,
	)
}
