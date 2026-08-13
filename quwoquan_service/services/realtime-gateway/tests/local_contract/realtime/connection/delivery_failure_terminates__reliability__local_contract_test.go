// 实时连接投递失败的可靠性契约：sink 投递失败必须立即终止连接
// （reason=delivery_failed），不得静默丢帧伪装投递成功。
//
// spec_ref: specs/feature-tree/runtime/runtime-testinfra/fault-injection-harness/spec.md#gwt-001
package local_contract

import (
	"context"
	"encoding/json"
	"sync"
	"testing"
	"time"

	"quwoquan_service/services/realtime-gateway/internal/realtime/connection/application"
)

// failingConnectionSink 模拟客户端写通道故障：Deliver 恒失败。
type failingConnectionSink struct {
	mu       sync.Mutex
	delivers int
	kicked   chan string
}

func newFailingConnectionSink() *failingConnectionSink {
	return &failingConnectionSink{kicked: make(chan string, 1)}
}

func (sink *failingConnectionSink) Deliver(_ string) bool {
	sink.mu.Lock()
	sink.delivers++
	sink.mu.Unlock()
	return false
}

func (sink *failingConnectionSink) Kick(reason string) {
	select {
	case sink.kicked <- reason:
	default:
	}
}

func (sink *failingConnectionSink) Delivers() int {
	sink.mu.Lock()
	defer sink.mu.Unlock()
	return sink.delivers
}

func TestDeliveryFailureTerminatesConnectionFailClosed(t *testing.T) {
	t.Parallel()
	harness := newGatewayHarness(t)
	identity := application.TrustedIdentity{
		AccountID: "acct-deliver-fail",
		PersonaID: "persona-deliver-fail",
		DeviceID:  "device-deliver-fail",
	}
	sink := newFailingConnectionSink()
	detach, err := harness.hub.Attach(
		context.Background(),
		identity,
		1,
		"conn-deliver-fail",
		"websocket",
		sink,
	)
	if err != nil {
		t.Fatalf("attach connection: %v", err)
	}
	t.Cleanup(detach)

	payload, err := json.Marshal(map[string]any{"type": "chat.test_event"})
	if err != nil {
		t.Fatal(err)
	}
	if err := harness.client.Publish(
		context.Background(),
		"rt:user:acct-deliver-fail",
		string(payload),
	); err != nil {
		t.Fatalf("publish event: %v", err)
	}

	select {
	case reason := <-sink.kicked:
		if reason != "delivery_failed" {
			t.Fatalf("terminate reason=%q want=delivery_failed", reason)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("delivery failure did not terminate the connection（不得静默丢帧伪成功）")
	}
	if sink.Delivers() != 1 {
		t.Fatalf(
			"deliver attempts=%d want=1（投递失败后不得继续向失效通道推送）",
			sink.Delivers(),
		)
	}
}
