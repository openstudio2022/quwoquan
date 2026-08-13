// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-002
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-003
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-008
// spec_ref: specs/feature-tree/chat-conversation/realtime-call/spec.md#sit-008.t1
// readiness_case: initiate-call-local
// readiness_case: answer-call-local
// readiness_case: reject-call-local
// readiness_case: cancel-call-local
// readiness_case: hangup-call-local
// readiness_case: join-call-local
// readiness_case: leave-call-local
// readiness_case: report-media-connected-local
// readiness_case: invite-to-call-local
// readiness_case: toggle-mute-local
// readiness_case: toggle-camera-local
// readiness_case: start-screen-share-local
// readiness_case: stop-screen-share-local
package local_contract

import (
	"testing"
	"time"

	"quwoquan_service/services/rtc-service/internal/rtc/call_session/domain/model"
)

func TestCallSessionOperationFacetsEnforceCanonicalLifecycle(t *testing.T) {
	service := newTestCallSessionService(t, 17*time.Second, 41*time.Second)

	initiated, err := service.InitiateCall(
		"caller",
		model.CallTypeVideo,
		"conversation-1",
		"",
		[]string{"callee"},
		model.MaxParticipants1v1,
	)
	if err != nil || initiated.Status != model.StatusInitiated ||
		len(initiated.Participants) != 2 {
		t.Fatalf("InitiateCall() session=%+v err=%v", initiated, err)
	}
	service.SetRinging(initiated)
	if err := service.AnswerCall(initiated, "callee"); err != nil ||
		initiated.Status != model.StatusConnecting {
		t.Fatalf("AnswerCall() status=%s err=%v", initiated.Status, err)
	}
	connectedAt := time.Date(2026, time.July, 24, 10, 0, 0, 0, time.UTC)
	if err := service.SetConnected(initiated, "caller", connectedAt); err != nil {
		t.Fatalf("SetConnected(caller): %v", err)
	}
	if err := service.SetConnected(initiated, "callee", connectedAt.Add(time.Second)); err != nil ||
		initiated.Status != model.StatusInCall {
		t.Fatalf("SetConnected(callee) status=%s err=%v", initiated.Status, err)
	}
	if err := service.ToggleMute(initiated, "caller", true); err != nil ||
		!initiated.Participants[0].IsMuted {
		t.Fatalf("ToggleMute() participant=%+v err=%v", initiated.Participants[0], err)
	}
	if err := service.ToggleCamera(initiated, "caller", true); err != nil ||
		!initiated.Participants[0].IsCameraOn {
		t.Fatalf("ToggleCamera() participant=%+v err=%v", initiated.Participants[0], err)
	}
	if err := service.StartScreenShare(initiated, "caller"); err != nil ||
		!initiated.IsScreenSharing || initiated.ScreenShareUserID != "caller" {
		t.Fatalf("StartScreenShare() session=%+v err=%v", initiated, err)
	}
	if err := service.StopScreenShare(initiated, "caller"); err != nil ||
		initiated.IsScreenSharing {
		t.Fatalf("StopScreenShare() session=%+v err=%v", initiated, err)
	}
	if err := service.HangupCall(initiated, "callee"); err != nil ||
		initiated.Status != model.StatusEnded {
		t.Fatalf("HangupCall() status=%s err=%v", initiated.Status, err)
	}

	rejected := ringingSession(time.Now().UTC(), model.MaxParticipants1v1)
	if err := service.RejectCall(rejected, "callee"); err != nil ||
		rejected.EndReason != model.EndReasonRejected {
		t.Fatalf("RejectCall() endReason=%s err=%v", rejected.EndReason, err)
	}
	cancelled := ringingSession(time.Now().UTC(), model.MaxParticipants1v1)
	cancelled.InitiatorID = "caller"
	if err := service.CancelCall(cancelled, "caller"); err != nil ||
		cancelled.EndReason != model.EndReasonCancelled {
		t.Fatalf("CancelCall() endReason=%s err=%v", cancelled.EndReason, err)
	}

	group := terminalActiveSession("call-group", "room-group", "caller", "member")
	group.MaxParticipants = 4
	if err := service.InviteToCall(group, []string{"invitee"}); err != nil {
		t.Fatalf("InviteToCall(): %v", err)
	}
	if err := service.JoinCall(group, "invitee"); err != nil ||
		group.ParticipantCount != 3 {
		t.Fatalf("JoinCall() participants=%d err=%v", group.ParticipantCount, err)
	}
	if err := service.LeaveCall(group, "invitee"); err != nil ||
		group.ParticipantCount != 2 {
		t.Fatalf("LeaveCall() participants=%d err=%v", group.ParticipantCount, err)
	}
}
