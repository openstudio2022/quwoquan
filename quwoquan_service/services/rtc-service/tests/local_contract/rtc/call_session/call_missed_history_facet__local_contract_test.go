package local_contract

import (
	"testing"
	"time"

	"quwoquan_service/services/rtc-service/internal/rtc/call_session/domain/model"
)

// 未接来电谓词与 ListCalls 的 missed 过滤条件是同一条规则的两处表达
// （status=ended、发起人不是本人、结束原因属于无人接听族）。任何一处漂移都会让
// 端侧未接红点与通话记录列表互相矛盾，因此三个条件逐一钉死。
func TestMissedCallFacetRequiresEndedInboundCallWithUnansweredReason(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name      string
		status    string
		endReason string
		userID    string
		want      bool
	}{
		{
			name:      "callee sees an unanswered call as missed",
			status:    model.StatusEnded,
			endReason: model.EndReasonNoAnswer,
			userID:    "callee",
			want:      true,
		},
		{
			name:      "callee sees a ring timeout as missed",
			status:    model.StatusEnded,
			endReason: model.EndReasonTimeout,
			userID:    "callee",
			want:      true,
		},
		{
			name:      "callee sees a caller cancellation as missed",
			status:    model.StatusEnded,
			endReason: model.EndReasonCancelled,
			userID:    "callee",
			want:      true,
		},
		{
			name:      "caller never misses a call it started",
			status:    model.StatusEnded,
			endReason: model.EndReasonNoAnswer,
			userID:    "caller",
			want:      false,
		},
		{
			name:      "callee that rejected the call did not miss it",
			status:    model.StatusEnded,
			endReason: model.EndReasonRejected,
			userID:    "callee",
			want:      false,
		},
		{
			name:      "callee that hung up normally did not miss it",
			status:    model.StatusEnded,
			endReason: model.EndReasonNormal,
			userID:    "callee",
			want:      false,
		},
		{
			name:      "still ringing call is not yet missed",
			status:    model.StatusRinging,
			endReason: "",
			userID:    "callee",
			want:      false,
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()

			session := endedSessionForMissedFacet(test.status, test.endReason)
			if got := session.IsMissedFor(test.userID); got != test.want {
				t.Fatalf(
					"IsMissedFor(%q) = %t, want %t for %s/%s",
					test.userID,
					got,
					test.want,
					test.status,
					test.endReason,
				)
			}
		})
	}
}

// 通话记录页会对未加载到的条目求值；缺席的会话不是未接来电，不能崩溃也不能算命中。
func TestMissedCallFacetTreatsAbsentSessionAsNotMissed(t *testing.T) {
	t.Parallel()

	var absent *model.CallSession
	if absent.IsMissedFor("callee") {
		t.Fatal("absent session must not count as a missed call")
	}
}

func endedSessionForMissedFacet(status, endReason string) *model.CallSession {
	createdAt := time.Date(2026, time.July, 20, 12, 0, 0, 0, time.UTC)
	return &model.CallSession{
		ID:               "call-missed",
		Status:           status,
		EndReason:        endReason,
		InitiatorID:      "caller",
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
				Status: model.ParticipantRinging,
			},
		},
		CreatedAt: createdAt,
		UpdatedAt: createdAt,
	}
}
