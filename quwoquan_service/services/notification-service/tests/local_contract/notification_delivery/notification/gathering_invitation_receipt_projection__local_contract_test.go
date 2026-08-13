// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-006
package local_contract

import (
	"testing"

	"quwoquan_service/services/notification-service/internal/notification_delivery/notification/application"
)

// 邀请回执（发起方侧）投影契约：
// - 受邀方真实应答（accepted/declined）→ 给 inviter 一条回执，target 回链行动；
// - pending（无应答事实）/ revoked（邀请方自己操作）不生成回执；
// - identity 不完整 fail-closed；受邀方卡片由独立投影承载，本分支不触碰。

func invitationReceiptEvent(
	t *testing.T,
	eventID string,
	status string,
) application.InteractionStreamEvent {
	t.Helper()
	return contentEvent(t, "GatheringInvitationChanged", eventID, map[string]any{
		"gatheringId":        "gathering-duo-1",
		"inviterPersonaId":   "persona-inviter",
		"recipientPersonaId": "persona-recipient",
		"purposeSummary":     "去森林公园走走",
		"participationVersion": 2,
		"status":             status,
		"actionIntents":      []any{},
		"occurredAt":         "2026-08-13T01:00:00Z",
	})
}

func TestInvitationReceiptNotifiesInviterOnAnswer(t *testing.T) {
	projection := application.InteractionNotificationProjection{}
	for _, status := range []string{"accepted", "declined"} {
		commands, err := projection.Project(
			invitationReceiptEvent(t, "evt-receipt-"+status, status),
		)
		if err != nil {
			t.Fatalf("%s: unexpected error: %v", status, err)
		}
		if len(commands) != 1 {
			t.Fatalf("%s: expected exactly one receipt, got %d", status, len(commands))
		}
		command := commands[0]
		if command.UserID != "persona-inviter" {
			t.Fatalf("%s: receipt must go to the inviter: %+v", status, command)
		}
		if command.MessageType != "circle" ||
			command.Source != "gathering_invitation_receipt" ||
			command.SourceID != "gathering-duo-1:"+status {
			t.Fatalf("%s: type/source identity mismatch: %+v", status, command)
		}
		if command.Target.TargetType != "gathering" ||
			command.Target.TargetID != "gathering-duo-1" {
			t.Fatalf("%s: target must link the gathering: %+v", status, command.Target)
		}
		if command.Title == "" || command.Summary == "" {
			t.Fatalf("%s: receipt copy must be present: %+v", status, command)
		}
	}
}

func TestInvitationReceiptSkipsNonAnswerStates(t *testing.T) {
	projection := application.InteractionNotificationProjection{}
	for _, status := range []string{"pending", "revoked", "expired", "cancelled"} {
		commands, err := projection.Project(
			invitationReceiptEvent(t, "evt-receipt-"+status, status),
		)
		if err != nil {
			t.Fatalf("%s: unexpected error: %v", status, err)
		}
		if len(commands) != 0 {
			t.Fatalf(
				"%s: non-answer states must not notify the inviter, got %d",
				status,
				len(commands),
			)
		}
	}
}

func TestInvitationReceiptFailsClosedOnIncompleteIdentity(t *testing.T) {
	projection := application.InteractionNotificationProjection{}
	event := contentEvent(t, "GatheringInvitationChanged", "evt-receipt-bad", map[string]any{
		"gatheringId":        "",
		"inviterPersonaId":   "persona-inviter",
		"recipientPersonaId": "persona-recipient",
		"status":             "accepted",
	})

	if _, err := projection.Project(event); err == nil {
		t.Fatalf("incomplete receipt identity must fail closed")
	}
}
