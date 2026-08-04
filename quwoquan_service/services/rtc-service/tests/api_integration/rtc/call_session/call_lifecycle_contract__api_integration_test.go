package api_integration

import (
	"net/http"
	"testing"
)

func TestContract_InitiateCall(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	resp := createTestCall(t, "user_initiator_001")
	session := extractSession(t, resp)

	if session["callId"] == nil {
		t.Error("session missing callId")
	}
	if session["callType"] != "audio" {
		t.Errorf("expected callType=audio, got %v", session["callType"])
	}
	if session["status"] != "ringing" {
		t.Errorf("expected status=ringing, got %v", session["status"])
	}
	if session["initiatorId"] != "user_initiator_001" {
		t.Errorf("expected initiatorId=user_initiator_001, got %v", session["initiatorId"])
	}
	if session["roomId"] == nil {
		t.Error("session missing roomId")
	}

	extractMediaAccess(t, resp)
}

func TestContract_InitiateCall_VideoType(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	resp := doPost(t, "/rtc/calls",
		`{"callType":"video","inviteeIds":["user_b"],"maxParticipants":2}`,
		"user_a", http.StatusCreated)
	session := extractSession(t, resp)

	if session["callType"] != "video" {
		t.Errorf("expected callType=video, got %v", session["callType"])
	}
}

func TestContract_InitiateCall_HonorsDeclaredGroupCapacity(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	resp := doPost(
		t,
		"/rtc/calls",
		`{"callType":"video","conversationId":"conversation_capacity","inviteeIds":["capacity_a","capacity_b"],"maxParticipants":8}`,
		"capacity_initiator",
		http.StatusCreated,
	)
	session := extractSession(t, resp)
	if session["maxParticipants"] != float64(8) {
		t.Fatalf(
			"server ignored canonical maxParticipants: got %v want 8",
			session["maxParticipants"],
		)
	}
}

func TestContract_InitiateCall_RejectsIncompleteOrUnknownBody(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	code, body := doPostAny(
		t,
		"/rtc/calls",
		`{"callType":"audio","inviteeIds":["missing_capacity"]}`,
		"invalid_initiator",
	)
	if code != http.StatusBadRequest ||
		body["code"] != "RTC.USER.invalid_argument" {
		t.Fatalf("missing maxParticipants = %d/%v", code, body)
	}

	code, body = doPostAny(
		t,
		"/rtc/calls",
		`{"callType":"audio","inviteeIds":["unknown_field"],"maxParticipants":2,"retiredLimit":2}`,
		"invalid_initiator",
	)
	if code != http.StatusBadRequest ||
		body["code"] != "RTC.USER.invalid_argument" {
		t.Fatalf("unknown request field = %d/%v", code, body)
	}
}

func TestContract_InitiateCall_ConflictWhenActive(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	createTestCall(t, "user_conflict_001")

	code, _ := doPostAny(t, "/rtc/calls",
		`{"callType":"audio","inviteeIds":["user_another"],"maxParticipants":2}`,
		"user_conflict_001")
	if code != http.StatusConflict {
		t.Fatalf("expected 409 for active call conflict, got %d", code)
	}
}

func TestContract_AnswerCall(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	resp := createTestCall(t, "user_caller_001")
	callID := extractSessionID(t, resp)

	answerResp := doPost(t, "/rtc/calls/"+callID+"/answer", `{}`, "user_invitee_001", http.StatusOK)
	session := extractSession(t, answerResp)
	if session["status"] != "connecting" {
		t.Errorf("expected status=connecting, got %v", session["status"])
	}
	extractMediaAccess(t, answerResp)
}

func TestContract_RejectCall(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	resp := createTestCall(t, "user_caller_002")
	callID := extractSessionID(t, resp)

	rejectResp := doPost(t, "/rtc/calls/"+callID+"/reject", `{}`, "user_invitee_001", http.StatusOK)
	if rejectResp["status"] != "ended" {
		t.Errorf("expected status=ended, got %v", rejectResp["status"])
	}
	if rejectResp["endReason"] != "rejected" {
		t.Errorf("expected endReason=rejected, got %v", rejectResp["endReason"])
	}
}

func TestContract_CancelCall(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	resp := createTestCall(t, "user_caller_003")
	callID := extractSessionID(t, resp)

	cancelResp := doPost(t, "/rtc/calls/"+callID+"/cancel", `{}`, "user_caller_003", http.StatusOK)
	if cancelResp["status"] != "ended" {
		t.Errorf("expected status=ended, got %v", cancelResp["status"])
	}
	if cancelResp["endReason"] != "cancelled" {
		t.Errorf("expected endReason=cancelled, got %v", cancelResp["endReason"])
	}
}

func TestContract_CancelCall_OnlyInitiator(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	resp := createTestCall(t, "user_caller_004")
	callID := extractSessionID(t, resp)

	code, _ := doPostAny(t, "/rtc/calls/"+callID+"/cancel", `{}`, "user_invitee_001")
	if code == http.StatusOK {
		t.Error("non-initiator should not be able to cancel")
	}
}

func TestContract_FullLifecycle_InitiateAnswerHangup(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	resp := createTestCall(t, "user_lc_001")
	callID := extractSessionID(t, resp)

	doPost(t, "/rtc/calls/"+callID+"/answer", `{}`, "user_invitee_001", http.StatusOK)

	doPost(t, "/rtc/calls/"+callID+"/join", `{}`, "user_invitee_001", http.StatusOK)
	doPost(t, "/rtc/calls/"+callID+"/join", `{}`, "user_lc_001", http.StatusOK)

	hangupResp := doPost(t, "/rtc/calls/"+callID+"/hangup", `{}`, "user_lc_001", http.StatusOK)

	leaveResp := doPost(t, "/rtc/calls/"+callID+"/leave", `{}`, "user_invitee_001", http.StatusOK)
	if leaveResp["status"] != "ended" {
		t.Errorf("expected status=ended after last leave, got %v", leaveResp["status"])
	}
	_ = hangupResp
}

func TestContract_GetCall(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	resp := createTestCall(t, "user_get_001")
	callID := extractSessionID(t, resp)

	code, getResp := doGet(t, "/rtc/calls/"+callID, "user_get_001")
	if code != http.StatusOK {
		t.Fatalf("expected 200, got %d", code)
	}
	if getResp["callId"] != callID {
		t.Errorf("expected callId=%s, got %v", callID, getResp["callId"])
	}
}

func TestContract_GetCall_NotFound(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	code, _ := doGet(t, "/rtc/calls/nonexistent_call_id", "user_001")
	if code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d", code)
	}
}

func TestContract_ListCalls(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	createTestCall(t, "user_list_001")

	code, listResp := doGet(t, "/rtc/calls?limit=10", "user_list_001")
	if code != http.StatusOK {
		t.Fatalf("expected 200, got %d", code)
	}
	items, ok := listResp["items"].([]any)
	if !ok {
		t.Fatal("response missing items array")
	}
	if len(items) < 1 {
		t.Error("expected at least 1 call in list")
	}
}

// 对齐 operations.yaml SIT scenario list_calls_with_missed_filter：
// GET /rtc/calls?missed=true 仅返回被叫方的未接来电。
func TestContract_ListCalls_MissedFilter(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	// 发起人发起后立即取消 → 对被叫方 user_invitee_001 而言是未接来电。
	resp := createTestCall(t, "user_caller_missed")
	missedCallID := extractSessionID(t, resp)
	doPost(t, "/rtc/calls/"+missedCallID+"/cancel", `{}`, "user_caller_missed", http.StatusOK)

	// 被叫方接通并挂断的通话 → 不应出现在 missed 列表。
	resp2 := createTestCall(t, "user_caller_answered")
	answeredCallID := extractSessionID(t, resp2)
	doPost(t, "/rtc/calls/"+answeredCallID+"/answer", `{}`, "user_invitee_001", http.StatusOK)
	doPost(t, "/rtc/calls/"+answeredCallID+"/hangup", `{}`, "user_invitee_001", http.StatusOK)

	code, listResp := doGet(t, "/rtc/calls?missed=true", "user_invitee_001")
	if code != http.StatusOK {
		t.Fatalf("expected 200, got %d", code)
	}
	items, ok := listResp["items"].([]any)
	if !ok {
		t.Fatal("response missing items array")
	}
	for _, it := range items {
		m, _ := it.(map[string]any)
		if m["callId"] == answeredCallID {
			t.Error("answered call should not appear in missed list")
		}
		if m["endReason"] == "normal" {
			t.Errorf("missed list should not include normal-ended call, got %v", m["callId"])
		}
	}
}

func TestContract_ToggleMute(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	resp := createTestCall(t, "user_mute_001")
	callID := extractSessionID(t, resp)

	doPost(t, "/rtc/calls/"+callID+"/answer", `{}`, "user_invitee_001", http.StatusOK)
	doPost(t, "/rtc/calls/"+callID+"/join", `{}`, "user_invitee_001", http.StatusOK)

	muteResp := doPost(t, "/rtc/calls/"+callID+"/mute",
		`{"muted":true}`, "user_invitee_001", http.StatusOK)

	participants, ok := muteResp["participants"].([]any)
	if !ok {
		t.Fatal("response missing participants")
	}
	for _, p := range participants {
		pm := p.(map[string]any)
		if pm["userId"] == "user_invitee_001" {
			if pm["isMuted"] != true {
				t.Errorf("expected isMuted=true, got %v", pm["isMuted"])
			}
		}
	}
}

func TestContract_ToggleCamera(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	resp := doPost(t, "/rtc/calls",
		`{"callType":"video","inviteeIds":["user_cam_invitee"],"maxParticipants":2}`,
		"user_cam_001", http.StatusCreated)
	callID := extractSessionID(t, resp)

	doPost(t, "/rtc/calls/"+callID+"/answer", `{}`, "user_cam_invitee", http.StatusOK)
	doPost(t, "/rtc/calls/"+callID+"/join", `{}`, "user_cam_invitee", http.StatusOK)

	camResp := doPost(t, "/rtc/calls/"+callID+"/camera",
		`{"cameraOn":true}`, "user_cam_invitee", http.StatusOK)

	participants, ok := camResp["participants"].([]any)
	if !ok {
		t.Fatal("response missing participants")
	}
	for _, p := range participants {
		pm := p.(map[string]any)
		if pm["userId"] == "user_cam_invitee" {
			if pm["isCameraOn"] != true {
				t.Errorf("expected isCameraOn=true, got %v", pm["isCameraOn"])
			}
		}
	}
}

func TestContract_ServerOwnedCASAndNoopReceipt(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	resp := createTestCall(t, "user_cas_001")
	callID := extractSessionID(t, resp)
	doPost(t, "/rtc/calls/"+callID+"/answer", `{}`, "user_invitee_001", http.StatusOK)
	doPost(t, "/rtc/calls/"+callID+"/join", `{}`, "user_invitee_001", http.StatusOK)
	doPost(t, "/rtc/calls/"+callID+"/join", `{}`, "user_cas_001", http.StatusOK)

	// 首次静音成功，版本推进。
	firstCode, first := doPostWithKey(t, "/rtc/calls/"+callID+"/mute", `{"muted":true}`, "user_cas_001", "mute-key-1")
	if firstCode != http.StatusOK {
		t.Fatalf("first mute status = %d: %v", firstCode, first)
	}
	firstVersion := first["version"]

	// 相同 Idempotency-Key 重放：返回首次结果，版本不变。
	replayCode, replay := doPostWithKey(t, "/rtc/calls/"+callID+"/mute", `{"muted":true}`, "user_cas_001", "mute-key-1")
	if replayCode != http.StatusOK || replay["version"] != firstVersion {
		t.Fatalf("replay must return first result: code=%d version=%v want %v", replayCode, replay["version"], firstVersion)
	}

	// 同一 key 改变命令载荷必须结构化冲突，不能重放首次结果或误判为 CAS。
	conflictCode, conflict := doPostWithKey(
		t,
		"/rtc/calls/"+callID+"/mute",
		`{"muted":false}`,
		"user_cas_001",
		"mute-key-1",
	)
	if conflictCode != http.StatusConflict ||
		conflict["code"] != "RTC.USER.idempotency_conflict" {
		t.Fatalf(
			"idempotency payload conflict = %d/%v",
			conflictCode,
			conflict,
		)
	}

	// 新 key、目标状态已满足（已静音）：no-op receipt，版本不递增。
	noopCode, noop := doPostWithKey(t, "/rtc/calls/"+callID+"/mute", `{"muted":true}`, "user_cas_001", "mute-key-2")
	if noopCode != http.StatusOK {
		t.Fatalf("noop mute status = %d: %v", noopCode, noop)
	}
	if noop["version"] != firstVersion {
		t.Fatalf("noop must not advance version: got %v want %v", noop["version"], firstVersion)
	}
}

func TestContract_NonParticipantIsRejected(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	resp := createTestCall(t, "user_bola_owner")
	callID := extractSessionID(t, resp)

	code, _ := doGet(t, "/rtc/calls/"+callID, "user_bola_intruder")
	if code == http.StatusOK {
		t.Fatalf("non-participant GetCall must not succeed, got %d", code)
	}
	mutateCode, _ := doPostAny(t, "/rtc/calls/"+callID+"/hangup", `{}`, "user_bola_intruder")
	if mutateCode == http.StatusOK {
		t.Fatalf("non-participant hangup must not succeed, got %d", mutateCode)
	}
}

func TestContract_ScreenShare_StartStop(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	resp := createTestCall(t, "user_ss_001")
	callID := extractSessionID(t, resp)

	doPost(t, "/rtc/calls/"+callID+"/answer", `{}`, "user_invitee_001", http.StatusOK)
	doPost(t, "/rtc/calls/"+callID+"/join", `{}`, "user_invitee_001", http.StatusOK)
	doPost(t, "/rtc/calls/"+callID+"/join", `{}`, "user_ss_001", http.StatusOK)

	startResp := doPost(t, "/rtc/calls/"+callID+"/screen-share/start", `{}`, "user_invitee_001", http.StatusOK)
	if startResp["isScreenSharing"] != true {
		t.Errorf("expected isScreenSharing=true, got %v", startResp["isScreenSharing"])
	}
	if startResp["screenShareUserId"] != "user_invitee_001" {
		t.Errorf("expected screenShareUserId=user_invitee_001, got %v", startResp["screenShareUserId"])
	}

	stopResp := doPost(t, "/rtc/calls/"+callID+"/screen-share/stop", `{}`, "user_invitee_001", http.StatusOK)
	if stopResp["isScreenSharing"] != false {
		t.Errorf("expected isScreenSharing=false, got %v", stopResp["isScreenSharing"])
	}
}

func TestContract_ScreenShare_SingleSharer(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	resp := createTestCall(t, "user_ss_002")
	callID := extractSessionID(t, resp)

	doPost(t, "/rtc/calls/"+callID+"/answer", `{}`, "user_invitee_001", http.StatusOK)
	doPost(t, "/rtc/calls/"+callID+"/join", `{}`, "user_invitee_001", http.StatusOK)
	doPost(t, "/rtc/calls/"+callID+"/join", `{}`, "user_ss_002", http.StatusOK)

	doPost(t, "/rtc/calls/"+callID+"/screen-share/start", `{}`, "user_invitee_001", http.StatusOK)

	code, _ := doPostAny(t, "/rtc/calls/"+callID+"/screen-share/start", `{}`, "user_ss_002")
	if code == http.StatusOK {
		t.Error("second sharer should be rejected")
	}
}

func TestContract_Healthz(t *testing.T) {
	code, resp := doGet(t, "/healthz", "")
	if code != http.StatusOK {
		t.Fatalf("expected 200, got %d", code)
	}
	if resp["status"] != "ok" {
		t.Errorf("expected status=ok, got %v", resp["status"])
	}
}
