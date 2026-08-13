// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#sit-002
//
// Conversation 源绑定错误码的负例断言：真实驱动 Provision* 投影路径到
// generated AppError 工厂的 emit 点，并以字面 wire code 锁定端云契约。
package local_contract

import (
	"context"
	"errors"
	"testing"

	. "quwoquan_service/services/chat-service/internal/chat/conversation/application"
	model "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
	rerrors "quwoquan_service/runtime/errors"
)

type errSemGatheringReader struct {
	conversation *model.Conversation
}

func (r errSemGatheringReader) FindConversationByGatheringID(
	context.Context, string,
) (*model.Conversation, error) {
	return r.conversation, nil
}

func (r errSemGatheringReader) ApplyGatheringConversationProjection(
	context.Context, string, int64, *model.Conversation,
) (bool, error) {
	return false, nil
}

type errSemCircleGroupReader struct {
	conversation *model.Conversation
}

func (r errSemCircleGroupReader) FindConversationByCircleGroupID(
	context.Context, string,
) (*model.Conversation, error) {
	return r.conversation, nil
}

func newErrSemConversationService(storage ChatStoragePorts) *ConversationService {
	return NewConversationService(
		storage,
		noopCache{},
		syncNoopEventPublisher{},
		nil,
		nil,
		nil,
		nil,
		syncNoopGroupAvatarScheduler{},
	)
}

func requireConversationAppErrorCode(t *testing.T, err error, wantCode string) {
	t.Helper()
	if err == nil {
		t.Fatalf("expected AppError %s, got nil", wantCode)
	}
	var appErr *rerrors.AppError
	if !errors.As(err, &appErr) {
		t.Fatalf("expected *AppError %s, got %v", wantCode, err)
	}
	if appErr.Code.String() != wantCode {
		t.Fatalf("expected code %s, got %s", wantCode, appErr.Code.String())
	}
}

func errSemGatheringRequest() GatheringConversationProvisioningRequest {
	return GatheringConversationProvisioningRequest{
		SourceEventID:  "gathering-event-sem",
		SourceVersion:  1,
		GatheringID:    "gathering-sem",
		OwnerPersonaID: "owner-sem",
		Title:          "相聚房间",
		AccessMode:     ConversationAccessModeActive,
		PostingPolicy:  ConversationPostingPolicyMemberChat,
	}
}

func TestProvisionGatheringConversationWithoutReaderEmitsProjectionUnavailable(t *testing.T) {
	service := newErrSemConversationService(ChatStoragePorts{
		Transactions: passthroughTransactionRunner{},
	})

	_, err := service.ProvisionGatheringConversation(
		context.Background(), errSemGatheringRequest(),
	)
	requireConversationAppErrorCode(
		t, err, "CHAT.MIDDLEWARE.conversation_projection_unavailable",
	)
}

func TestProvisionGatheringConversationBindingOwnedByOtherPersonaEmitsGatheringBindingConflict(t *testing.T) {
	service := newErrSemConversationService(ChatStoragePorts{
		Transactions: passthroughTransactionRunner{},
		GatheringConversations: errSemGatheringReader{conversation: &model.Conversation{
			ID: "conv-gathering-sem", Type: "group", OriginType: "gathering",
			CreatorId: "someone-else", GatheringId: "gathering-sem",
		}},
	})

	_, err := service.ProvisionGatheringConversation(
		context.Background(), errSemGatheringRequest(),
	)
	requireConversationAppErrorCode(t, err, "CHAT.USER.gathering_binding_conflict")
}

func TestProvisionCircleGroupConversationBindingMismatchEmitsCircleGroupBindingConflict(t *testing.T) {
	service := newErrSemConversationService(ChatStoragePorts{
		Transactions: passthroughTransactionRunner{},
		CircleGroupConversations: errSemCircleGroupReader{conversation: &model.Conversation{
			ID: "conv-circle-sem", Type: "group", OriginType: "circle_group",
			CreatorId: "owner-sem", CircleId: "another-circle", CircleGroupId: "circle-group-sem",
		}},
	})

	_, err := service.ProvisionCircleGroupConversation(
		context.Background(), CircleGroupConversationProvisioningRequest{
			SourceEventID:  "circle-event-sem",
			CircleID:       "circle-sem",
			CircleGroupID:  "circle-group-sem",
			OwnerPersonaID: "owner-sem",
			Title:          "圈群房间",
		},
	)
	requireConversationAppErrorCode(t, err, "CHAT.SYSTEM.circle_group_binding_conflict")
}
