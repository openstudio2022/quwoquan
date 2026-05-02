package tests

import (
	"net/http"
	"testing"
)

func TestContract_InitiateCall(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	resp := createTestCall(t, "user_initiator_001")
	session := extractSession(t, resp)

	if session["_id"] == nil {
		t.Error("session missing _id")
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

	token, _ := resp["token"].(string)
	if token == "" {
		t.Error("response missing token")
	}
}

func TestContract_InitiateCall_VideoType(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	resp := doPost(t, "/v1/rtc/calls",
		`{"callType":"video","inviteeIds":["user_b"]}`,
		"user_a", http.StatusCreated)
	session := extractSession(t, resp)

	if session["callType"] != "video" {
		t.Errorf("expected callType=video, got %v", session["callType"])
	}
}

func TestContract_InitiateCall_ConflictWhenActive(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	createTestCall(t, "user_conflict_001")

	code, _ := doPostAny(t, "/v1/rtc/calls",
		`{"callType":"audio","inviteeIds":["user_another"]}`,
		"user_conflict_001")
	if code != http.StatusConflict {
		t.Fatalf("expected 409 for active call conflict, got %d", code)
	}
}

func TestContract_AnswerCall(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	resp := createTestCall(t, "user_caller_001")
	callID := extractSessionID(t, resp)

	answerResp := doPost(t, "/v1/rtc/calls/"+callID+"/answer", `{}`, "user_invitee_001", http.StatusOK)
	session := extractSession(t, answerResp)
	if session["status"] != "connecting" {
		t.Errorf("expected status=connecting, got %v", session["status"])
	}
}

func TestContract_RejectCall(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	resp := createTestCall(t, "user_caller_002")
	callID := extractSessionID(t, resp)

	rejectResp := doPost(t, "/v1/rtc/calls/"+callID+"/reject", `{}`, "user_invitee_001", http.StatusOK)
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

	cancelResp := doPost(t, "/v1/rtc/calls/"+callID+"/cancel", `{}`, "user_caller_003", http.StatusOK)
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

	code, _ := doPostAny(t, "/v1/rtc/calls/"+callID+"/cancel", `{}`, "user_invitee_001")
	if code == http.StatusOK {
		t.Error("non-initiator should not be able to cancel")
	}
}

func TestContract_FullLifecycle_InitiateAnswerHangup(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	resp := createTestCall(t, "user_lc_001")
	callID := extractSessionID(t, resp)

	doPost(t, "/v1/rtc/calls/"+callID+"/answer", `{}`, "user_invitee_001", http.StatusOK)

	doPost(t, "/v1/rtc/calls/"+callID+"/join", `{}`, "user_invitee_001", http.StatusOK)
	doPost(t, "/v1/rtc/calls/"+callID+"/join", `{}`, "user_lc_001", http.StatusOK)

	hangupResp := doPost(t, "/v1/rtc/calls/"+callID+"/hangup", `{}`, "user_lc_001", http.StatusOK)

	leaveResp := doPost(t, "/v1/rtc/calls/"+callID+"/leave", `{}`, "user_invitee_001", http.StatusOK)
	if leaveResp["status"] != "ended" {
		t.Errorf("expected status=ended after last leave, got %v", leaveResp["status"])
	}
	_ = hangupResp
}

func TestContract_GetCall(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	resp := createTestCall(t, "user_get_001")
	callID := extractSessionID(t, resp)

	code, getResp := doGet(t, "/v1/rtc/calls/"+callID, "user_get_001")
	if code != http.StatusOK {
		t.Fatalf("expected 200, got %d", code)
	}
	if getResp["_id"] != callID {
		t.Errorf("expected _id=%s, got %v", callID, getResp["_id"])
	}
}

func TestContract_GetCall_NotFound(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	code, _ := doGet(t, "/v1/rtc/calls/nonexistent_call_id", "user_001")
	if code != http.StatusNotFound {
		t.Fatalf("expected 404, got %d", code)
	}
}

func TestContract_ListCalls(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	createTestCall(t, "user_list_001")

	code, listResp := doGet(t, "/v1/rtc/calls?limit=10", "user_list_001")
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

func TestContract_ToggleMute(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	resp := createTestCall(t, "user_mute_001")
	callID := extractSessionID(t, resp)

	doPost(t, "/v1/rtc/calls/"+callID+"/answer", `{}`, "user_invitee_001", http.StatusOK)
	doPost(t, "/v1/rtc/calls/"+callID+"/join", `{}`, "user_invitee_001", http.StatusOK)

	muteResp := doPost(t, "/v1/rtc/calls/"+callID+"/mute",
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

	resp := doPost(t, "/v1/rtc/calls",
		`{"callType":"video","inviteeIds":["user_cam_invitee"]}`,
		"user_cam_001", http.StatusCreated)
	callID := extractSessionID(t, resp)

	doPost(t, "/v1/rtc/calls/"+callID+"/answer", `{}`, "user_cam_invitee", http.StatusOK)
	doPost(t, "/v1/rtc/calls/"+callID+"/join", `{}`, "user_cam_invitee", http.StatusOK)

	camResp := doPost(t, "/v1/rtc/calls/"+callID+"/camera",
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

func TestContract_Recording_StartStop(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	resp := createTestCall(t, "user_rec_001")
	callID := extractSessionID(t, resp)

	doPost(t, "/v1/rtc/calls/"+callID+"/answer", `{}`, "user_invitee_001", http.StatusOK)
	doPost(t, "/v1/rtc/calls/"+callID+"/join", `{}`, "user_invitee_001", http.StatusOK)
	doPost(t, "/v1/rtc/calls/"+callID+"/join", `{}`, "user_rec_001", http.StatusOK)

	startResp := doPost(t, "/v1/rtc/calls/"+callID+"/recording/start", `{}`, "user_rec_001", http.StatusOK)
	if startResp["isRecording"] != true {
		t.Errorf("expected isRecording=true, got %v", startResp["isRecording"])
	}

	stopResp := doPost(t, "/v1/rtc/calls/"+callID+"/recording/stop", `{}`, "user_rec_001", http.StatusOK)
	if stopResp["isRecording"] != false {
		t.Errorf("expected isRecording=false, got %v", stopResp["isRecording"])
	}
}

func TestContract_Recording_OnlyInitiator(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	resp := createTestCall(t, "user_rec_002")
	callID := extractSessionID(t, resp)

	doPost(t, "/v1/rtc/calls/"+callID+"/answer", `{}`, "user_invitee_001", http.StatusOK)
	doPost(t, "/v1/rtc/calls/"+callID+"/join", `{}`, "user_invitee_001", http.StatusOK)
	doPost(t, "/v1/rtc/calls/"+callID+"/join", `{}`, "user_rec_002", http.StatusOK)

	code, _ := doPostAny(t, "/v1/rtc/calls/"+callID+"/recording/start", `{}`, "user_invitee_001")
	if code == http.StatusOK {
		t.Error("non-initiator should not start recording")
	}
}

func TestContract_ScreenShare_StartStop(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	resp := createTestCall(t, "user_ss_001")
	callID := extractSessionID(t, resp)

	doPost(t, "/v1/rtc/calls/"+callID+"/answer", `{}`, "user_invitee_001", http.StatusOK)
	doPost(t, "/v1/rtc/calls/"+callID+"/join", `{}`, "user_invitee_001", http.StatusOK)
	doPost(t, "/v1/rtc/calls/"+callID+"/join", `{}`, "user_ss_001", http.StatusOK)

	startResp := doPost(t, "/v1/rtc/calls/"+callID+"/screen-share/start", `{}`, "user_invitee_001", http.StatusOK)
	if startResp["isScreenSharing"] != true {
		t.Errorf("expected isScreenSharing=true, got %v", startResp["isScreenSharing"])
	}
	if startResp["screenShareUserId"] != "user_invitee_001" {
		t.Errorf("expected screenShareUserId=user_invitee_001, got %v", startResp["screenShareUserId"])
	}

	stopResp := doPost(t, "/v1/rtc/calls/"+callID+"/screen-share/stop", `{}`, "user_invitee_001", http.StatusOK)
	if stopResp["isScreenSharing"] != false {
		t.Errorf("expected isScreenSharing=false, got %v", stopResp["isScreenSharing"])
	}
}

func TestContract_ScreenShare_SingleSharer(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	resp := createTestCall(t, "user_ss_002")
	callID := extractSessionID(t, resp)

	doPost(t, "/v1/rtc/calls/"+callID+"/answer", `{}`, "user_invitee_001", http.StatusOK)
	doPost(t, "/v1/rtc/calls/"+callID+"/join", `{}`, "user_invitee_001", http.StatusOK)
	doPost(t, "/v1/rtc/calls/"+callID+"/join", `{}`, "user_ss_002", http.StatusOK)

	doPost(t, "/v1/rtc/calls/"+callID+"/screen-share/start", `{}`, "user_invitee_001", http.StatusOK)

	code, _ := doPostAny(t, "/v1/rtc/calls/"+callID+"/screen-share/start", `{}`, "user_ss_002")
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
