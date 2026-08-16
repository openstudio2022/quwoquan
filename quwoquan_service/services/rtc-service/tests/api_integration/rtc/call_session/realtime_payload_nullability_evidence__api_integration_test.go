// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/absent-empty-failure-nullability/spec.md#open-003
package api_integration

// RTC realtime envelope 的实测键集合证据。
//
// 这里刻意**不**断言「契约声明 NOT_NULL 的键必发」——那正是 OPEN-003 待裁决的事情，
// 现在就断言等于把待验证的结论当成既有事实。真实链路上有两道过滤先后作用：
// events.yaml 的 `payload_fields` 决定哪些键进入客户端载荷，Go 侧 `CallEventPayload`
// 的 `omitempty` 再决定空值键是否消失。所以先记录每个事件实际发出的键，作为
// authoring 收敛（codegen 改读 payload_entity + 服务端去 omitempty + 端侧移除兜底）
// 的前置证据。
//
// 证据取自真实 Redis pubsub 通道 `rt:rtc:persona:<personaID>`，与端侧订阅同一路径，
// 不是对 marshal 函数的单元调用：过滤发生在 orchestrator 与 publisher 两层，只测
// marshal 会绕过其中一层。

import (
	"context"
	"encoding/json"
	"net/http"
	"sort"
	"strings"
	"testing"
	"time"

	goredis "github.com/redis/go-redis/v9"

	runtimemessaging "quwoquan_service/runtime/messaging"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/adapters/inbound/mq"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/application"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/infrastructure/persistence"
)

// 契约 `CallEventPayload` 声明为 NOT_NULL 的字段。取自
// services/rtc-service/contracts/rtc/call_session/fields.yaml。
var callEventPayloadNotNullFields = map[string]bool{
	"callId":           true,
	"eventId":          true,
	"callType":         true,
	"initiatorId":      true,
	"maxParticipants":  true,
	"status":           true,
	"participantCount": true,
	"createdAt":        true,
}

type observedEnvelope struct {
	wireType string
	keys     []string
}

func subscribePersonaRealtime(
	t *testing.T,
	personaIDs ...string,
) (<-chan observedEnvelope, func()) {
	t.Helper()
	client := goredis.NewClient(&goredis.Options{
		Addr:     integrationRedis.Addr,
		Password: integrationRedis.Password,
		DB:       1, // realtime scene
	})
	channels := make([]string, 0, len(personaIDs))
	for _, personaID := range personaIDs {
		channels = append(channels, "rt:rtc:persona:"+personaID)
	}
	ctx := context.Background()
	subscription := client.Subscribe(ctx, channels...)
	if _, err := subscription.Receive(ctx); err != nil {
		t.Fatalf("subscribe persona realtime channels: %v", err)
	}
	observed := make(chan observedEnvelope, 64)
	done := make(chan struct{})
	go func() {
		defer close(observed)
		incoming := subscription.Channel()
		for {
			select {
			case <-done:
				return
			case message, ok := <-incoming:
				if !ok {
					return
				}
				envelope := decodeEnvelopeKeys(t, message.Payload)
				if envelope.wireType == "" {
					continue
				}
				select {
				case observed <- envelope:
				default:
				}
			}
		}
	}()
	return observed, func() {
		close(done)
		_ = subscription.Close()
		_ = client.Close()
	}
}

func decodeEnvelopeKeys(t *testing.T, payload string) observedEnvelope {
	t.Helper()
	var body struct {
		Type    string                     `json:"type"`
		Payload map[string]json.RawMessage `json:"payload"`
	}
	if err := json.Unmarshal([]byte(payload), &body); err != nil {
		t.Fatalf("decode realtime envelope %s: %v", payload, err)
	}
	keys := make([]string, 0, len(body.Payload))
	for key := range body.Payload {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return observedEnvelope{wireType: body.Type, keys: keys}
}

// newEvidenceDeliveryPump 返回一个「把 outbox 里已提交事件投递出去」的函数。
//
// 刻意不依赖 TestMain 那个后台 relay：`CallSignalDeliveryCoordinator.Run` 一旦
// `Deliver` 返回错误就直接 return，而 TestMain 用 `_ =` 接住了它——上一轮跑剩在
// 库里的 outbox 记录足以让 worker 在第一个 tick 静默死亡，后面所有事件都不再投递，
// 表现为「测试偶发收不到任何 envelope」。这里主动驱动并把错误暴露出来。
func newEvidenceDeliveryPump(t *testing.T) func() {
	t.Helper()
	transport, err := runtimemessaging.NewRedisMessageTransportForRoot(
		"rtc-evidence",
		runtimemessaging.RedisMessageTransportAdapter,
		redisRouter.Scene("realtime"),
		redisRouter.Scene("general"),
	)
	if err != nil {
		t.Fatalf("construct evidence message transport: %v", err)
	}
	relay := application.NewCallSignalDeliveryRelay(
		persistence.NewMongoCallStore(requireMongoDB(t)),
		mq.NewRealtimePublisher(transport),
	)
	return func() {
		if _, err := relay.Deliver(context.Background(), 100); err != nil {
			t.Errorf("deliver rtc outbox: %v", err)
		}
	}
}

func TestRealtimeCallEnvelopePayloadKeysAreRecordedAsEvidence(t *testing.T) {
	cleanAll(t)
	const caller = "user_evidence_caller"
	const invitee = "user_invitee_001"

	observed, stop := subscribePersonaRealtime(t, caller, invitee)
	defer stop()
	deliver := newEvidenceDeliveryPump(t)

	// 两段通话：第一段走到 leave 拿 participant.left，第二段 answer 后直接 hangup
	// 拿 call.ended。同一段里 leave 会先把 1v1 通话带到 ended，hangup 就没有事件了。
	lifecycle := extractSessionID(t, createTestCall(t, caller))
	doPost(t, "/rtc/calls/"+lifecycle+"/answer", `{}`, invitee, http.StatusOK)
	doPost(t, "/rtc/calls/"+lifecycle+"/join", `{}`, invitee, http.StatusOK)
	doPost(t, "/rtc/calls/"+lifecycle+"/leave", `{}`, invitee, http.StatusOK)
	deliver()

	hungUp := extractSessionID(t, createTestCall(t, caller))
	doPost(t, "/rtc/calls/"+hungUp+"/answer", `{}`, invitee, http.StatusOK)
	doPost(t, "/rtc/calls/"+hungUp+"/hangup", `{}`, caller, http.StatusOK)
	deliver()

	// `call.ringing` 收不到是预期的——它只追加 durable stream，不走 persona pubsub。
	expected := []string{
		"call.initiated",
		"call.answered",
		"participant.joined",
		"participant.left",
		"call.ended",
	}
	byWireType := map[string][]string{}
	deadline := time.After(30 * time.Second)
collect:
	for len(byWireType) < len(expected) {
		select {
		case envelope, ok := <-observed:
			if !ok {
				t.Fatal("realtime subscription closed before evidence was collected")
			}
			if _, seen := byWireType[envelope.wireType]; !seen {
				byWireType[envelope.wireType] = envelope.keys
			}
		case <-time.After(3 * time.Second):
			deliver()
			if len(byWireType) > 0 {
				break collect
			}
		case <-deadline:
			break collect
		}
	}
	for _, wireType := range expected {
		if _, seen := byWireType[wireType]; !seen {
			t.Errorf("预期事件 %s 未观测到，证据不完整：%v", wireType, byWireType)
		}
	}

	for _, wireType := range sortedKeys(byWireType) {
		keys := byWireType[wireType]
		present := map[string]bool{}
		for _, key := range keys {
			present[key] = true
		}
		absentNotNull := []string{}
		for field := range callEventPayloadNotNullFields {
			if !present[field] {
				absentNotNull = append(absentNotNull, field)
			}
		}
		sort.Strings(absentNotNull)
		// 输出而非断言：payload_fields 本就只挑一部分字段下发，「NOT_NULL 却缺席」
		// 在收敛前既可能是 authoring 分裂，也可能是该事件本就不该带这个字段。
		t.Logf(
			"[OPEN-003 evidence] wireType=%s emitted=%s notNullAbsent=%s",
			wireType,
			strings.Join(keys, ","),
			strings.Join(absentNotNull, ","),
		)
	}

	// 唯一可以现在就断言的事实：callId 在契约与 Go 侧都是无条件必发，任何事件都
	// 必须能被路由到某一次通话，否则端侧连丢弃都无从判断。
	for wireType, keys := range byWireType {
		found := false
		for _, key := range keys {
			if key == "callId" {
				found = true
				break
			}
		}
		if !found {
			t.Errorf("wireType=%s 缺少 callId：%v", wireType, keys)
		}
	}
}

func sortedKeys(source map[string][]string) []string {
	keys := make([]string, 0, len(source))
	for key := range source {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}
