// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/model-attribute-semantics/spec.md#gwt-001.t1
// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/model-attribute-semantics/spec.md#gwt-001.t2
// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/model-attribute-semantics/spec.md#gwt-001.t3
package local_contract

import (
	"context"
	"os"
	"path/filepath"
	. "quwoquan_service/services/chat-service/internal/chat/conversation/application"
	"strings"
	"testing"

	model "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
)

// statusOnlyConversationStore 让测试直接声明 Conversation.Status 的取值，
// 用于证明闭集零值与闭集内终态取值走同一条判否路径。
type statusOnlyConversationStore struct {
	ConversationStore
	status model.ConversationStatus
}

func (s statusOnlyConversationStore) FindConversationByID(
	context.Context,
	string,
) (*model.Conversation, error) {
	return &model.Conversation{
		ID:     "conv-status-1",
		Type:   "group",
		Status: s.status,
	}, nil
}

func newMemberServiceWithConversationStatus(
	status model.ConversationStatus,
) *MemberService {
	return NewMemberService(
		ChatStoragePorts{
			Transactions:       passthroughTransactionRunner{},
			Conversations:      statusOnlyConversationStore{status: status},
			Members:            activeMemberStore{},
			UserStates:         &memoryUserStateStore{},
			MembershipCommands: newMemoryAggregateCommandStore(),
		},
		noopCache{},
		syncNoopEventPublisher{},
		nil,
		nil,
		nil,
		syncNoopGroupAvatarScheduler{},
	)
}

func newConversationServiceWithConversationStatus(
	status model.ConversationStatus,
) *ConversationService {
	return NewConversationService(
		ChatStoragePorts{
			Transactions:      passthroughTransactionRunner{},
			Conversations:     statusOnlyConversationStore{status: status},
			Members:           activeMemberStore{},
			UserStates:        &memoryUserStateStore{},
			UserStateCommands: newMemoryAggregateCommandStore(),
		},
		noopCache{},
		syncNoopEventPublisher{},
		nil,
		nil,
		nil,
		nil,
		syncNoopGroupAvatarScheduler{},
	)
}

// TestConversationStatusZeroValueIsRejectedLikeTerminalStatus 锁定 gwt-001.t1：
// Conversation.status 的契约声明是 enum + NOT_NULL，闭集只有 active 与 dissolved，
// 因此语言零值不是合法取值，必须与 dissolved 走同一条判否路径而不是获得放行。
func TestConversationStatusZeroValueIsRejectedLikeTerminalStatus(t *testing.T) {
	t.Parallel()

	muted := true
	updateSettings := func(status model.ConversationStatus, key string) error {
		return newConversationServiceWithConversationStatus(status).UpdateSettings(
			commandContext("owner", key),
			UpdateSettingsRequest{
				ConversationId: "conv-status-1",
				UserId:         "owner",
				Muted:          &muted,
			},
		)
	}

	zeroValueErr := updateSettings("", "status-zero-settings")
	if zeroValueErr == nil {
		t.Fatal("zero-value conversation status must not pass the membership authorization gate")
	}
	dissolvedErr := updateSettings(model.ConversationStatusDissolved, "status-dissolved-settings")
	if dissolvedErr == nil {
		t.Fatal("dissolved conversation status must be rejected")
	}
	if zeroValueErr.Error() != dissolvedErr.Error() {
		t.Fatalf(
			"zero-value status must be rejected on the same path as dissolved:\n zero: %v\n dissolved: %v",
			zeroValueErr,
			dissolvedErr,
		)
	}
	if activeErr := updateSettings(model.ConversationStatusActive, "status-active-settings"); activeErr != nil {
		t.Fatalf("active conversation status must stay admissible, got %v", activeErr)
	}
}

// TestConversationStatusGateIsSingleForEveryCommand 锁定 gwt-001.t2：
// 零值判否来自唯一授权门，不靠各调用点各自补写零值分支，
// 因此跨 service 的命令在同一取值下必须得到同一结论。
func TestConversationStatusGateIsSingleForEveryCommand(t *testing.T) {
	t.Parallel()

	memberErr := newMemberServiceWithConversationStatus("").AddMembers(
		commandContext("owner", "status-zero-gate-member"),
		AddMembersRequest{
			ConversationId: "conv-status-1",
			InvitedBy:      "owner",
			UserIds:        []string{"invitee-1"},
		},
	)
	if memberErr == nil {
		t.Fatal("MemberService command must reject zero-value conversation status")
	}

	muted := true
	settingsErr := newConversationServiceWithConversationStatus("").UpdateSettings(
		commandContext("owner", "status-zero-gate-settings"),
		UpdateSettingsRequest{
			ConversationId: "conv-status-1",
			UserId:         "owner",
			Muted:          &muted,
		},
	)
	if settingsErr == nil {
		t.Fatal("ConversationService.UpdateSettings must reject zero-value conversation status")
	}
	if memberErr.Error() != settingsErr.Error() {
		t.Fatalf(
			"both commands must reject through the same gate:\n member: %v\n settings: %v",
			memberErr,
			settingsErr,
		)
	}
}

// TestConversationStatusHasNoZeroValueEscapeOrLiteralCompare 锁定 gwt-001.t2 与 gwt-001.t3：
// 消费点不得为 status 的零值单开豁免分支，判定与写入都必须使用闭集的具名常量。
func TestConversationStatusHasNoZeroValueEscapeOrLiteralCompare(t *testing.T) {
	t.Parallel()

	root := chatServiceContractRoot(t)
	scanned := 0
	for _, dir := range []string{
		filepath.Join(root, "internal", "chat", "conversation", "application"),
		filepath.Join(root, "cmd", "api"),
	} {
		entries, err := os.ReadDir(dir)
		if err != nil {
			t.Fatalf("read %s: %v", dir, err)
		}
		for _, entry := range entries {
			if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".go") {
				continue
			}
			path := filepath.Join(dir, entry.Name())
			source := readChatContract(t, path)
			scanned++
			for _, escape := range []string{
				`Status != ""`,
				`Status == ""`,
				`Status) != ""`,
				`Status) == ""`,
			} {
				if strings.Contains(source, escape) {
					t.Errorf(
						"%s keeps a zero-value escape for a closed-set status: %s",
						path,
						escape,
					)
				}
			}
			for _, literal := range []string{
				`Status != "active"`,
				`Status == "active"`,
				`Status) != "active"`,
				`Status) == "active"`,
				`Status:                     "active"`,
			} {
				if strings.Contains(source, literal) {
					t.Errorf(
						"%s compares or writes conversation status by literal instead of the named constant: %s",
						path,
						literal,
					)
				}
			}
		}
	}
	if scanned == 0 {
		t.Fatal("conversation status scan covered no source file")
	}
}
