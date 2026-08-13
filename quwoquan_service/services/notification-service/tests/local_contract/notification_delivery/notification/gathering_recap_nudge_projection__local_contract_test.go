// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#req-009
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/spec.md#sit-003
package local_contract

import (
	"testing"

	"quwoquan_service/services/notification-service/internal/notification_delivery/notification/application"
)

// 结束催回顾投影契约（比例②发动机）：
// - Completed 且 outcome=occurred → 向完成时冻结的每位 active 参与者各一条催发，
//   target 回链行动公开详情（详情内有携带 gatheringRef 的发布回顾入口）；
// - did_not_happen / disputed / unverified 不催（不推动为未确认发生的行动造回顾）；
// - 名单空不投、重复 persona 收敛、gatheringId 缺失 fail-closed。

func recapNudgeEvent(
	t *testing.T,
	eventID string,
	outcome string,
	participants []any,
) application.InteractionStreamEvent {
	t.Helper()
	return contentEvent(t, "GatheringCompleted", eventID, map[string]any{
		"gatheringId":           "gathering-hike-1",
		"aggregateVersion":      7,
		"lifecycleStatus":       "completed",
		"actorPersonaId":        "persona-host",
		"outcomeStatus":         outcome,
		"roomBindingStatus":     "ready",
		"conversationId":        "conv-hike-1",
		"participantPersonaIds": participants,
		"occurredAt":            "2026-08-13T09:00:00Z",
	})
}

func TestRecapNudgeNotifiesEachActiveParticipantOnOccurred(t *testing.T) {
	projection := application.InteractionNotificationProjection{}
	commands, err := projection.Project(recapNudgeEvent(
		t,
		"evt-recap-occurred",
		"occurred",
		[]any{"persona-host", "persona-joiner"},
	))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(commands) != 2 {
		t.Fatalf("expected one nudge per participant, got %d", len(commands))
	}
	recipients := map[string]bool{}
	keys := map[string]bool{}
	for _, command := range commands {
		recipients[command.UserID] = true
		if command.MessageType != "circle" ||
			command.Source != "gathering_recap_nudge" ||
			command.SourceID != "gathering-hike-1" {
			t.Fatalf("type/source identity mismatch: %+v", command)
		}
		if command.Target.TargetType != "gathering" ||
			command.Target.TargetID != "gathering-hike-1" {
			t.Fatalf("target must link the gathering detail: %+v", command.Target)
		}
		if command.Title == "" || command.Summary == "" {
			t.Fatalf("nudge copy must be present: %+v", command)
		}
		if keys[command.IdempotencyKey] {
			t.Fatalf("idempotency keys must be unique per recipient: %+v", command)
		}
		keys[command.IdempotencyKey] = true
	}
	if !recipients["persona-host"] || !recipients["persona-joiner"] {
		t.Fatalf("both participants must be nudged: %v", recipients)
	}
}

func TestRecapNudgeSkipsUnconfirmedOutcomes(t *testing.T) {
	projection := application.InteractionNotificationProjection{}
	for _, outcome := range []string{
		"did_not_happen", "disputed", "unverified", "ended_early", "",
	} {
		commands, err := projection.Project(recapNudgeEvent(
			t,
			"evt-recap-"+outcome,
			outcome,
			[]any{"persona-host", "persona-joiner"},
		))
		if err != nil {
			t.Fatalf("%q: unexpected error: %v", outcome, err)
		}
		if len(commands) != 0 {
			t.Fatalf("%q: unconfirmed outcome must not nudge: %d", outcome, len(commands))
		}
	}
}

func TestRecapNudgeCollapsesDuplicatesAndSkipsEmptyRoster(t *testing.T) {
	projection := application.InteractionNotificationProjection{}
	commands, err := projection.Project(recapNudgeEvent(
		t,
		"evt-recap-dup",
		"occurred",
		[]any{"persona-host", "persona-host", " ", ""},
	))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(commands) != 1 {
		t.Fatalf("duplicate personas must collapse to one nudge, got %d", len(commands))
	}

	empty, err := projection.Project(recapNudgeEvent(
		t,
		"evt-recap-empty",
		"occurred",
		[]any{},
	))
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(empty) != 0 {
		t.Fatalf("empty roster must not emit commands, got %d", len(empty))
	}
}

func TestRecapNudgeFailsClosedOnMissingGatheringIdentity(t *testing.T) {
	projection := application.InteractionNotificationProjection{}
	event := contentEvent(t, "GatheringCompleted", "evt-recap-noid", map[string]any{
		"gatheringId":           " ",
		"outcomeStatus":         "occurred",
		"participantPersonaIds": []any{"persona-host"},
	})
	if _, err := projection.Project(event); err == nil {
		t.Fatal("missing gathering identity must fail closed")
	}
}
