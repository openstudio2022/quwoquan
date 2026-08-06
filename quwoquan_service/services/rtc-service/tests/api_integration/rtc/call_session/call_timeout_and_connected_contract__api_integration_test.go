// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-002
// readiness_case: report-media-connected-api
package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"testing"
	"time"

	"github.com/google/uuid"
	"go.mongodb.org/mongo-driver/v2/bson"
)

// ── ReportMediaConnected：媒体建连报告驱动 in_call/startedAt ────────────────
//
// 对应 operations.yaml ReportMediaConnected 与 events.yaml CallConnected；
// 修复「1v1 answer 后 session 永远停在 connecting、startedAt 恒空」的写模型断点。

func TestReportMediaConnected_TransitionsToInCall(t *testing.T) {
	cleanAll(t)
	resp := createTestCall(t, "user_conn_001")
	callID := extractSessionID(t, resp)
	if _, err := uuid.Parse(callID); err != nil {
		t.Fatalf("CallSession id must be RFC 4122 UUID for CallKit parity: %q", callID)
	}

	doPost(t, "/rtc/calls/"+callID+"/answer", `{}`, "user_invitee_001", http.StatusOK)

	// 双方媒体建连报告：第二个 connected 参与者驱动会话进入 in_call。
	first := doPost(t, "/rtc/calls/"+callID+"/connected", `{}`, "user_invitee_001", http.StatusOK)
	if first["status"] == "in_call" {
		t.Fatalf("single connected participant must not enter in_call yet, got %v", first["status"])
	}
	second := doPost(t, "/rtc/calls/"+callID+"/connected", `{}`, "user_conn_001", http.StatusOK)
	if second["status"] != "in_call" {
		t.Fatalf("expected in_call after both participants connected, got %v", second["status"])
	}
	if s, _ := second["startedAt"].(string); s == "" {
		t.Fatal("in_call session must record startedAt for duration accounting")
	}
	connectedEvents, err := mongoDB.Collection("call_session_outbox").CountDocuments(
		context.Background(),
		bson.M{"aggregateId": callID, "eventType": "CallConnected"},
	)
	if err != nil {
		t.Fatalf("count CallConnected outbox events: %v", err)
	}
	if connectedEvents != 2 {
		t.Fatalf("connected reports produced %d CallConnected facts, want 2", connectedEvents)
	}

	code, getResp := doGet(t, "/rtc/calls/"+callID, "user_conn_001")
	if code != http.StatusOK || getResp["status"] != "in_call" {
		t.Fatalf("GetCall after connected: code=%d status=%v", code, getResp["status"])
	}
}

func TestReportMediaConnected_RepeatIsNoop(t *testing.T) {
	cleanAll(t)
	resp := createTestCall(t, "user_conn_010")
	callID := extractSessionID(t, resp)
	doPost(t, "/rtc/calls/"+callID+"/answer", `{}`, "user_invitee_001", http.StatusOK)
	doPost(t, "/rtc/calls/"+callID+"/connected", `{}`, "user_invitee_001", http.StatusOK)
	doPost(t, "/rtc/calls/"+callID+"/connected", `{}`, "user_conn_010", http.StatusOK)

	before := fetchSessionVersion(t, callID)
	repeat := doPost(t, "/rtc/calls/"+callID+"/connected", `{}`, "user_conn_010", http.StatusOK)
	if repeat["status"] != "in_call" {
		t.Fatalf("repeat connected must keep in_call, got %v", repeat["status"])
	}
	after := fetchSessionVersion(t, callID)
	if after != before {
		t.Fatalf("repeat connected must be a no-op (version %d -> %d)", before, after)
	}
	connectedEvents, err := mongoDB.Collection("call_session_outbox").CountDocuments(
		context.Background(),
		bson.M{"aggregateId": callID, "eventType": "CallConnected"},
	)
	if err != nil {
		t.Fatalf("count CallConnected outbox events: %v", err)
	}
	if connectedEvents != 2 {
		t.Fatalf("target-state no-op produced duplicate CallConnected fact: %d", connectedEvents)
	}
}

func TestReportMediaConnected_NonParticipantRejected(t *testing.T) {
	cleanAll(t)
	resp := createTestCall(t, "user_conn_020")
	callID := extractSessionID(t, resp)
	code, body := doPostAny(t, "/rtc/calls/"+callID+"/connected", `{}`, "user_stranger_999")
	if code != http.StatusForbidden {
		t.Fatalf("non-participant connected report must be 403, got %d body=%v", code, body)
	}
}

// ── 振铃超时 sweeper：no_answer 终态与 call.ended 事实 ──────────────────────
//
// 对应 contract.yaml scenario call_no_answer_timeout 与 typed service
// ring-timeout configuration；系统命令使用确定性幂等 key。

func TestRingTimeoutSweep_NoAnswerEndsCall(t *testing.T) {
	cleanAll(t)
	resp := createTestCall(t, "user_timeout_001")
	callID := extractSessionID(t, resp)

	backdateCall(t, callID, 40*time.Second)

	swept, err := testOrchestrator.SweepRingTimeouts(context.Background())
	if err != nil {
		t.Fatalf("sweep ring timeouts: %v", err)
	}
	if swept != 1 {
		t.Fatalf("expected exactly 1 swept call, got %d", swept)
	}

	code, getResp := doGet(t, "/rtc/calls/"+callID, "user_timeout_001")
	if code != http.StatusOK {
		t.Fatalf("GetCall after timeout: code=%d", code)
	}
	if getResp["status"] != "ended" || getResp["endReason"] != "no_answer" {
		t.Fatalf("expected ended/no_answer, got status=%v endReason=%v", getResp["status"], getResp["endReason"])
	}

	// 被叫收到 call.ended 事实：outbox 必须有 CallEnded 事件（撤来电面板依据）。
	count, err := mongoDB.Collection("call_session_outbox").CountDocuments(
		context.Background(),
		bson.M{"aggregateId": callID, "eventType": "CallEnded"},
	)
	if err != nil {
		t.Fatalf("count outbox: %v", err)
	}
	if count != 1 {
		t.Fatalf("expected exactly 1 CallEnded outbox fact, got %d", count)
	}
	var outbox struct {
		Payload []byte `bson:"payload"`
	}
	if err := mongoDB.Collection("call_session_outbox").FindOne(
		context.Background(),
		bson.M{"aggregateId": callID, "eventType": "CallEnded"},
	).Decode(&outbox); err != nil {
		t.Fatalf("load timeout CallEnded outbox: %v", err)
	}
	var wire struct {
		Type       string   `json:"type"`
		ActorID    string   `json:"actorId"`
		Recipients []string `json:"recipients"`
		Payload    struct {
			EndReason string `json:"endReason"`
		} `json:"payload"`
	}
	if err := json.Unmarshal(outbox.Payload, &wire); err != nil {
		t.Fatalf("decode timeout CallEnded wire: %v", err)
	}
	if wire.Type != "call.ended" || wire.Payload.EndReason != "no_answer" {
		t.Fatalf("timeout wire = %s/%s", wire.Type, wire.Payload.EndReason)
	}
	if wire.ActorID != "system:rtc-ring-timeout-sweeper" || len(wire.Recipients) != 2 {
		t.Fatalf("timeout wire actor/recipients = %q/%v", wire.ActorID, wire.Recipients)
	}
	receiptCount, err := mongoDB.Collection("call_session_command_receipts").CountDocuments(
		context.Background(),
		bson.M{
			"aggregateId": callID,
			"commandName": "RingTimeout",
		},
	)
	if err != nil {
		t.Fatalf("count timeout command receipt: %v", err)
	}
	if receiptCount != 1 {
		t.Fatalf("timeout command receipt count = %d, want 1", receiptCount)
	}

	// 重复 sweep 幂等：ended 会话不再命中。
	sweptAgain, err := testOrchestrator.SweepRingTimeouts(context.Background())
	if err != nil {
		t.Fatalf("second sweep: %v", err)
	}
	if sweptAgain != 0 {
		t.Fatalf("second sweep must be a no-op, got %d", sweptAgain)
	}
}

func TestRingTimeoutSweep_GroupUsesLongerThreshold(t *testing.T) {
	cleanAll(t)
	payload := `{"callType":"video","circleId":"circle_group_001","inviteeIds":["user_g1","user_g2"],"maxParticipants":32}`
	resp := doPost(t, "/rtc/calls", payload, "user_timeout_010", http.StatusCreated)
	callID := extractSessionID(t, resp)

	// 群通话阈值 60s：40s 未超期，不得被收割。
	backdateCall(t, callID, 40*time.Second)
	if swept, err := testOrchestrator.SweepRingTimeouts(context.Background()); err != nil || swept != 0 {
		t.Fatalf("40s group call must not time out (swept=%d err=%v)", swept, err)
	}

	backdateCall(t, callID, 70*time.Second)
	if swept, err := testOrchestrator.SweepRingTimeouts(context.Background()); err != nil || swept != 1 {
		t.Fatalf("70s group call must time out (swept=%d err=%v)", swept, err)
	}
	code, getResp := doGet(t, "/rtc/calls/"+callID, "user_timeout_010")
	if code != http.StatusOK || getResp["endReason"] != "no_answer" {
		t.Fatalf("group timeout endReason: code=%d endReason=%v", code, getResp["endReason"])
	}
}

func TestRingTimeoutSweep_IgnoresAnsweredCall(t *testing.T) {
	cleanAll(t)
	resp := createTestCall(t, "user_timeout_020")
	callID := extractSessionID(t, resp)
	doPost(t, "/rtc/calls/"+callID+"/answer", `{}`, "user_invitee_001", http.StatusOK)

	backdateCall(t, callID, 120*time.Second)
	if swept, err := testOrchestrator.SweepRingTimeouts(context.Background()); err != nil || swept != 0 {
		t.Fatalf("answered (connecting) call must not be swept (swept=%d err=%v)", swept, err)
	}
	code, getResp := doGet(t, "/rtc/calls/"+callID, "user_timeout_020")
	if code != http.StatusOK || getResp["status"] != "connecting" {
		t.Fatalf("answered call must stay connecting: code=%d status=%v", code, getResp["status"])
	}
}

// backdateCall 把会话 createdAt 拨老，用真实存储驱动超时路径（不 mock 时钟）。
func backdateCall(t *testing.T, callID string, age time.Duration) {
	t.Helper()
	_, err := mongoDB.Collection("call_sessions").UpdateOne(
		context.Background(),
		bson.M{"_id": callID},
		bson.M{"$set": bson.M{"createdAt": time.Now().UTC().Add(-age)}},
	)
	if err != nil {
		t.Fatalf("backdate call %s: %v", callID, err)
	}
	// 缓存与存储同源：拨老后清缓存，保证 sweeper/查询读到最新事实。
	if err := integrationRedis.FlushDBs(context.Background(), 0); err != nil {
		t.Fatalf("flush cache after backdate: %v", err)
	}
}

func fetchSessionVersion(t *testing.T, callID string) int64 {
	t.Helper()
	var doc struct {
		Version int64 `bson:"version"`
	}
	if err := mongoDB.Collection("call_sessions").FindOne(
		context.Background(),
		bson.M{"_id": callID},
	).Decode(&doc); err != nil {
		t.Fatalf("load session version: %v", err)
	}
	return doc.Version
}
