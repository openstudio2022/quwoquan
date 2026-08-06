package support

import (
	"testing"

	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
)

// NewRedisMessageTransport 供 circle-service 各对象的消费者测试共用，
// 避免同一启动器在多个对象测试包内重复定义。
func NewRedisMessageTransport(t testing.TB, client rtredis.Client) *runtimemessaging.RedisMessageTransport {
	t.Helper()
	transport, err := runtimemessaging.NewRedisMessageTransportForRoot(
		"circle-service-test",
		runtimemessaging.RedisMessageTransportFixture,
		client,
		client,
	)
	if err != nil {
		t.Fatalf("new circle test message transport: %v", err)
	}
	return transport
}
