// spec_ref: specs/feature-tree/chat-conversation/intersection-native-messaging/spec.md#sit-004
//
// 破冰卡触发面的结构性保证：GatheringMemberJoinedHook 只在活动群成员真实
// 新增（事务提交后）被调用一次——精确重放、角色变更、访问回收都不触发。
// 普通群与 1v1 不经 Gathering 投影路径，结构上不存在该触发面。
package local_contract

import (
	"context"
	"testing"

	membershipapp "quwoquan_service/services/chat-service/internal/chat/conversation_membership/application"
)

type recordingMemberJoinedHook struct {
	facts []membershipapp.GatheringMemberJoinedFact
}

func (h *recordingMemberJoinedHook) OnGatheringMemberJoined(
	_ context.Context,
	fact membershipapp.GatheringMemberJoinedFact,
) {
	h.facts = append(h.facts, fact)
}

func TestGatheringMemberJoinedHookFiresOnlyOnRealJoin(t *testing.T) {
	backend := newGatheringProjectionBackend()
	hook := &recordingMemberJoinedHook{}
	facade := membershipapp.NewGatheringProjectionFacade(
		backend, backend, backend, backend, backend, backend, backend, backend,
	).WithGatheringMemberJoinedHook(hook)

	join := membershipapp.GatheringProjectionCommand{
		SourceEventID: "gathering-1:participation:persona-2:20", SourceVersion: 20,
		GatheringID: "gathering-1", PersonaID: "persona-2",
		SourceType: membershipapp.GatheringProjectionSourceParticipation,
		State:      membershipapp.GatheringProjectionStateActive,
	}
	if _, err := facade.Project(context.Background(), join); err != nil {
		t.Fatalf("Project joined: %v", err)
	}
	if len(hook.facts) != 1 {
		t.Fatalf("real join must fire hook exactly once, got %d", len(hook.facts))
	}
	fact := hook.facts[0]
	if fact.GatheringID != "gathering-1" || fact.ConversationID != "conversation-1" ||
		fact.PersonaID != "persona-2" || fact.DisplayName != "同行者" ||
		fact.SourceEventID != join.SourceEventID {
		t.Fatalf("joined fact drifted: %+v", fact)
	}

	// 精确重放：投影 no-op，不再触发。
	if _, err := facade.Project(context.Background(), join); err != nil {
		t.Fatalf("exact replay: %v", err)
	}
	if len(hook.facts) != 1 {
		t.Fatalf("replay must not fire hook again, got %d", len(hook.facts))
	}

	// 角色变更（organizer 升级）：成员已存在，不触发。
	organizer := join
	organizer.SourceEventID = "gathering-1:organizer:persona-2:30"
	organizer.SourceVersion = 30
	organizer.SourceType = membershipapp.GatheringProjectionSourceOrganizerAssignment
	if _, err := facade.Project(context.Background(), organizer); err != nil {
		t.Fatalf("Project organizer: %v", err)
	}
	if len(hook.facts) != 1 {
		t.Fatalf("role change must not fire hook, got %d", len(hook.facts))
	}

	// 访问回收（Block）：成员移除，不触发。
	blocked := join
	blocked.SourceEventID = "gathering-1:block:persona-2:40"
	blocked.SourceVersion = 40
	blocked.SourceType = membershipapp.GatheringProjectionSourceBlock
	blocked.State = membershipapp.GatheringProjectionStateBlocked
	if _, err := facade.Project(context.Background(), blocked); err != nil {
		t.Fatalf("Project block: %v", err)
	}
	if len(hook.facts) != 1 {
		t.Fatalf("member removal must not fire hook, got %d", len(hook.facts))
	}
}
