package local_contract

import (
	"testing"
	"time"

	callsession "quwoquan_service/services/rtc-service/internal/rtc/call_session/domain"
	"quwoquan_service/services/rtc-service/internal/rtc/call_session/domain/model"
)

func TestCallSessionTimeoutFacetUsesOneToOneAndGroupBoundaries(t *testing.T) {
	t.Parallel()

	service := callsession.NewCallSessionService()
	now := time.Date(2026, time.July, 20, 12, 0, 0, 0, time.UTC)

	tests := []struct {
		name            string
		maxParticipants int
		age             time.Duration
		wantTimedOut    bool
	}{
		{
			name:            "one-to-one remains ringing before thirty seconds",
			maxParticipants: model.MaxParticipants1v1,
			age:             30*time.Second - time.Nanosecond,
			wantTimedOut:    false,
		},
		{
			name:            "one-to-one times out at thirty seconds",
			maxParticipants: model.MaxParticipants1v1,
			age:             30 * time.Second,
			wantTimedOut:    true,
		},
		{
			name:            "group remains ringing before sixty seconds",
			maxParticipants: model.MaxParticipantsGroup,
			age:             60*time.Second - time.Nanosecond,
			wantTimedOut:    false,
		},
		{
			name:            "group times out at sixty seconds",
			maxParticipants: model.MaxParticipantsGroup,
			age:             60 * time.Second,
			wantTimedOut:    true,
		},
	}

	for _, test := range tests {
		test := test
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()

			session := ringingSession(now.Add(-test.age), test.maxParticipants)
			timedOut, err := service.HandleTimeout(session, now)
			if err != nil {
				t.Fatalf("HandleTimeout() error = %v", err)
			}
			if timedOut != test.wantTimedOut {
				t.Fatalf("HandleTimeout() = %t, want %t", timedOut, test.wantTimedOut)
			}
			if !test.wantTimedOut {
				if session.Status != model.StatusRinging || session.EndedAt != nil {
					t.Fatalf("non-expired session mutated: status=%s endedAt=%v", session.Status, session.EndedAt)
				}
				return
			}
			if session.Status != model.StatusEnded || session.EndReason != model.EndReasonNoAnswer {
				t.Fatalf("expired session = %s/%s, want ended/no_answer", session.Status, session.EndReason)
			}
			if session.EndedAt == nil || !session.EndedAt.Equal(now) {
				t.Fatalf("EndedAt = %v, want %v", session.EndedAt, now)
			}
			if session.Participants[1].Status != model.ParticipantTimeout {
				t.Fatalf("invitee status = %s, want timeout", session.Participants[1].Status)
			}
		})
	}
}

func TestCallSessionConnectedFacetRequiresConnectingAndStartsAtSecondParticipant(t *testing.T) {
	t.Parallel()

	service := callsession.NewCallSessionService()
	now := time.Date(2026, time.July, 20, 12, 5, 0, 0, time.UTC)
	session := connectingSession(now.Add(-time.Second))

	if err := service.SetConnected(session, "caller", now); err != nil {
		t.Fatalf("first SetConnected() error = %v", err)
	}
	if session.Status != model.StatusConnecting || session.StartedAt != nil {
		t.Fatalf("one connected participant started call: status=%s startedAt=%v", session.Status, session.StartedAt)
	}

	secondConnectedAt := now.Add(time.Second)
	if err := service.SetConnected(session, "callee", secondConnectedAt); err != nil {
		t.Fatalf("second SetConnected() error = %v", err)
	}
	if session.Status != model.StatusInCall {
		t.Fatalf("status = %s, want in_call", session.Status)
	}
	if session.StartedAt == nil || !session.StartedAt.Equal(secondConnectedAt) {
		t.Fatalf("StartedAt = %v, want %v", session.StartedAt, secondConnectedAt)
	}

	startedAt := *session.StartedAt
	updatedAt := session.UpdatedAt
	if err := service.SetConnected(session, "callee", secondConnectedAt.Add(time.Second)); err != nil {
		t.Fatalf("target-state SetConnected() error = %v", err)
	}
	if !session.StartedAt.Equal(startedAt) || !session.UpdatedAt.Equal(updatedAt) {
		t.Fatalf(
			"target-state SetConnected mutated timestamps: startedAt=%v updatedAt=%v",
			session.StartedAt,
			session.UpdatedAt,
		)
	}
}

func TestCallSessionConnectedFacetRejectsRingingAndEndedParticipants(t *testing.T) {
	t.Parallel()

	service := callsession.NewCallSessionService()
	now := time.Date(2026, time.July, 20, 12, 10, 0, 0, time.UTC)

	ringing := ringingSession(now.Add(-time.Second), model.MaxParticipants1v1)
	if err := service.SetConnected(ringing, "callee", now); err == nil {
		t.Fatal("ringing invitee reported media connected without answering")
	}
	if ringing.Participants[1].Status != model.ParticipantRinging {
		t.Fatalf("rejected report mutated invitee to %s", ringing.Participants[1].Status)
	}

	ended := connectingSession(now.Add(-time.Second))
	ended.Status = model.StatusEnded
	ended.EndReason = model.EndReasonCancelled
	if err := service.SetConnected(ended, "caller", now); err == nil {
		t.Fatal("ended call accepted media connected report")
	}
	if ended.Participants[0].Status != model.ParticipantConnecting {
		t.Fatalf("ended-call report mutated participant to %s", ended.Participants[0].Status)
	}
}

func ringingSession(createdAt time.Time, maxParticipants int) *model.CallSession {
	return &model.CallSession{
		ID:               "call-ringing",
		Status:           model.StatusRinging,
		MaxParticipants:  maxParticipants,
		ParticipantCount: 2,
		Participants: []model.Participant{
			{
				UserID: "caller",
				Role:   model.RoleInitiator,
				Status: model.ParticipantConnecting,
			},
			{
				UserID: "callee",
				Role:   model.RoleInvitee,
				Status: model.ParticipantRinging,
			},
		},
		CreatedAt: createdAt,
		UpdatedAt: createdAt,
	}
}

func connectingSession(createdAt time.Time) *model.CallSession {
	return &model.CallSession{
		ID:               "call-connecting",
		Status:           model.StatusConnecting,
		MaxParticipants:  model.MaxParticipants1v1,
		ParticipantCount: 2,
		Participants: []model.Participant{
			{
				UserID: "caller",
				Role:   model.RoleInitiator,
				Status: model.ParticipantConnecting,
			},
			{
				UserID: "callee",
				Role:   model.RoleInvitee,
				Status: model.ParticipantConnecting,
			},
		},
		CreatedAt: createdAt,
		UpdatedAt: createdAt,
	}
}
