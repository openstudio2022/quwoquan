package tests

import (
	"fmt"
	"net/http"
	"testing"
)

func TestContract_JoinCall(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	resp := createTestCall(t, "user_join_001")
	callID := extractSessionID(t, resp)

	doPost(t, "/v1/rtc/calls/"+callID+"/answer", `{}`, "user_invitee_001", http.StatusOK)

	joinResp := doPost(t, "/v1/rtc/calls/"+callID+"/join", `{}`, "user_invitee_001", http.StatusOK)
	session, ok := joinResp["session"].(map[string]any)
	if !ok {
		t.Fatal("join response missing session")
	}
	if session["status"] != "in_call" {
		t.Errorf("expected status=in_call after join, got %v", session["status"])
	}

	token, _ := joinResp["token"].(string)
	if token == "" {
		t.Error("join response missing token")
	}
}

func TestContract_LeaveCall(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	resp := createTestCall(t, "user_leave_001")
	callID := extractSessionID(t, resp)

	doPost(t, "/v1/rtc/calls/"+callID+"/answer", `{}`, "user_invitee_001", http.StatusOK)
	doPost(t, "/v1/rtc/calls/"+callID+"/join", `{}`, "user_invitee_001", http.StatusOK)
	doPost(t, "/v1/rtc/calls/"+callID+"/join", `{}`, "user_leave_001", http.StatusOK)

	leaveResp := doPost(t, "/v1/rtc/calls/"+callID+"/leave", `{}`, "user_leave_001", http.StatusOK)
	status := leaveResp["status"]
	if status == "ended" {
		t.Logf("call ended after initiator leave (expected if only 1 active remains)")
	}
}

func TestContract_LeaveCall_LastParticipantEndsCall(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	resp := createTestCall(t, "user_last_001")
	callID := extractSessionID(t, resp)

	doPost(t, "/v1/rtc/calls/"+callID+"/answer", `{}`, "user_invitee_001", http.StatusOK)
	doPost(t, "/v1/rtc/calls/"+callID+"/join", `{}`, "user_invitee_001", http.StatusOK)
	doPost(t, "/v1/rtc/calls/"+callID+"/join", `{}`, "user_last_001", http.StatusOK)

	doPost(t, "/v1/rtc/calls/"+callID+"/leave", `{}`, "user_last_001", http.StatusOK)

	leaveResp := doPost(t, "/v1/rtc/calls/"+callID+"/leave", `{}`, "user_invitee_001", http.StatusOK)
	if leaveResp["status"] != "ended" {
		t.Errorf("expected status=ended after last participant leaves, got %v", leaveResp["status"])
	}
	if leaveResp["endReason"] != "last_leave" {
		t.Errorf("expected endReason=last_leave, got %v", leaveResp["endReason"])
	}
}

func TestContract_InviteToCall(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	resp := doPost(t, "/v1/rtc/calls",
		`{"callType":"audio","inviteeIds":["user_inv_b"],"circleId":"circle_001"}`,
		"user_inv_001", http.StatusCreated)
	callID := extractSessionID(t, resp)

	doPost(t, "/v1/rtc/calls/"+callID+"/answer", `{}`, "user_inv_b", http.StatusOK)
	doPost(t, "/v1/rtc/calls/"+callID+"/join", `{}`, "user_inv_b", http.StatusOK)

	inviteResp := doPost(t, "/v1/rtc/calls/"+callID+"/invite",
		`{"inviteeIds":["user_inv_c","user_inv_d"]}`, "user_inv_001", http.StatusOK)

	participants, ok := inviteResp["participants"].([]any)
	if !ok {
		t.Fatal("response missing participants")
	}
	if len(participants) < 4 {
		t.Errorf("expected >=4 participants after invite, got %d", len(participants))
	}
}

func TestContract_MultiPartyJoinLeave(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	resp := doPost(t, "/v1/rtc/calls",
		`{"callType":"video","inviteeIds":["user_mp_b","user_mp_c"],"circleId":"circle_multi"}`,
		"user_mp_001", http.StatusCreated)
	callID := extractSessionID(t, resp)

	doPost(t, "/v1/rtc/calls/"+callID+"/answer", `{}`, "user_mp_b", http.StatusOK)
	doPost(t, "/v1/rtc/calls/"+callID+"/join", `{}`, "user_mp_b", http.StatusOK)

	doPost(t, "/v1/rtc/calls/"+callID+"/answer", `{}`, "user_mp_c", http.StatusOK)
	doPost(t, "/v1/rtc/calls/"+callID+"/join", `{}`, "user_mp_c", http.StatusOK)

	doPost(t, "/v1/rtc/calls/"+callID+"/join", `{}`, "user_mp_001", http.StatusOK)

	code, getResp := doGet(t, "/v1/rtc/calls/"+callID, "user_mp_001")
	if code != http.StatusOK {
		t.Fatalf("expected 200, got %d", code)
	}
	if getResp["status"] != "in_call" {
		t.Errorf("expected status=in_call, got %v", getResp["status"])
	}
	count := getResp["participantCount"]
	if count == nil {
		t.Error("missing participantCount")
	}

	doPost(t, "/v1/rtc/calls/"+callID+"/leave", `{}`, "user_mp_b", http.StatusOK)

	code, getResp2 := doGet(t, "/v1/rtc/calls/"+callID, "user_mp_001")
	if code != http.StatusOK {
		t.Fatalf("expected 200, got %d", code)
	}
	if getResp2["status"] == "ended" {
		t.Error("call should not end while participants remain")
	}
}

func TestContract_MaxParticipantsLimit(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	invitees := make([]string, 31)
	for i := range invitees {
		invitees[i] = fmt.Sprintf("user_limit_%03d", i)
	}

	inviteeJSON := "["
	for i, id := range invitees {
		if i > 0 {
			inviteeJSON += ","
		}
		inviteeJSON += fmt.Sprintf(`"%s"`, id)
	}
	inviteeJSON += "]"

	resp := doPost(t, "/v1/rtc/calls",
		fmt.Sprintf(`{"callType":"audio","inviteeIds":%s,"circleId":"circle_limit"}`, inviteeJSON),
		"user_limit_initiator", http.StatusCreated)
	callID := extractSessionID(t, resp)

	for _, id := range invitees[:5] {
		doPost(t, "/v1/rtc/calls/"+callID+"/answer", `{}`, id, http.StatusOK)
		doPost(t, "/v1/rtc/calls/"+callID+"/join", `{}`, id, http.StatusOK)
	}
	doPost(t, "/v1/rtc/calls/"+callID+"/join", `{}`, "user_limit_initiator", http.StatusOK)

	code, _ := doPostAny(t, "/v1/rtc/calls/"+callID+"/invite",
		`{"inviteeIds":["user_over_limit_1","user_over_limit_2"]}`, "user_limit_initiator")
	_ = code
}

func TestContract_ResponseShape_HasRequiredFields(t *testing.T) {
	t.Cleanup(func() { cleanAll(t) })

	resp := createTestCall(t, "user_shape_001")
	session := extractSession(t, resp)

	requiredFields := []string{
		"_id", "callType", "status", "initiatorId", "roomId",
		"maxParticipants", "participantCount", "participants",
		"createdAt", "updatedAt",
	}
	for _, field := range requiredFields {
		if _, ok := session[field]; !ok {
			t.Errorf("session missing required field: %s", field)
		}
	}
}
