// spec_ref: specs/feature-tree/object-homepage-network/intersection-unified-experience/spec.md#sit-008
package local_contract

import (
	"testing"

	"quwoquan_service/services/notification-service/internal/notification_delivery/notification/application"
)

// 创作者促成通知投影契约：
// - IntersectionFacilitationRecorded → 内容维度通知，接收者为种草内容创作者，
//   target 回链 Gathering 公开详情；不携带参与者名单。
// - identity 不完整（缺 facilitationId/gatheringId/creator/seedPost）fail-closed。

func TestProjectIntersectionFacilitationCreatesCreatorNotice(t *testing.T) {
	projection := application.InteractionNotificationProjection{}
	event := contentEvent(
		t,
		"IntersectionFacilitationRecorded",
		"evt-facilitation-1",
		map[string]any{
			"facilitationId":   "fac-1",
			"gatheringId":      "gathering-1",
			"creatorPersonaId": "persona-creator",
			"seedPostId":       "post-seed-1",
			"occurredAt":       "2026-08-12T12:00:00Z",
		},
	)

	commands, err := projection.Project(event)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if len(commands) != 1 {
		t.Fatalf("expected exactly one command, got %d", len(commands))
	}
	command := commands[0]
	if command.UserID != "persona-creator" {
		t.Fatalf("recipient must be the seed content creator: %+v", command)
	}
	if command.MessageType != "content" ||
		command.Source != "intersection_facilitation" ||
		command.SourceID != "fac-1" {
		t.Fatalf("type/source identity mismatch: %+v", command)
	}
	if command.Target.TargetType != "gathering" ||
		command.Target.TargetID != "gathering-1" {
		t.Fatalf("target must link the public gathering detail: %+v", command.Target)
	}
	if command.Title == "" || command.Summary == "" {
		t.Fatalf("notice copy must be present: %+v", command)
	}
}

func TestProjectIntersectionFacilitationFailsClosedOnIncompleteIdentity(t *testing.T) {
	projection := application.InteractionNotificationProjection{}
	event := contentEvent(
		t,
		"IntersectionFacilitationRecorded",
		"evt-facilitation-2",
		map[string]any{
			"facilitationId":   "fac-2",
			"gatheringId":      "",
			"creatorPersonaId": "persona-creator",
			"seedPostId":       "post-seed-1",
		},
	)

	if _, err := projection.Project(event); err == nil {
		t.Fatalf("incomplete facilitation identity must fail closed")
	}
}
