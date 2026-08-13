// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#sit-002
//
// Message 对象声明错误码的负例断言：每个用例真实驱动 application 拒绝路径
// 到 generated AppError 工厂的 emit 点，并以字面 wire code 锁定端云契约。
package local_contract

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	. "quwoquan_service/services/chat-service/internal/chat/conversation/application"
	conversationmodel "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
	messagemodel "quwoquan_service/services/chat-service/internal/chat/message/domain/model"
	messageports "quwoquan_service/services/chat-service/internal/chat/message/domain/ports"
	rerrors "quwoquan_service/runtime/errors"
)

type errSemMemberStore struct {
	MemberStore
	member *conversationmodel.ConversationMember
	err    error
}

func (s errSemMemberStore) FindMember(
	context.Context, string, string,
) (*conversationmodel.ConversationMember, error) {
	return s.member, s.err
}

type errSemConversationStore struct {
	ConversationStore
	conversation *conversationmodel.Conversation
	err          error
}

func (s errSemConversationStore) FindConversationByID(
	context.Context, string,
) (*conversationmodel.Conversation, error) {
	return s.conversation, s.err
}

type errSemMessageStore struct {
	MessageStore
	message *messagemodel.Message
	err     error
}

func (s errSemMessageStore) FindMessageByID(
	context.Context, string,
) (*messagemodel.Message, error) {
	return s.message, s.err
}

type errSemProjector struct{}

func (errSemProjector) ProjectCommittedMessage(context.Context, messagemodel.Message) error {
	return nil
}

type errSemMediaReader struct {
	err error
}

func (r errSemMediaReader) ReadOwnedReadyAsset(
	context.Context, string, string,
) (messageports.MediaAssetDeliverySlice, bool, error) {
	return messageports.MediaAssetDeliverySlice{}, false, r.err
}

type errSemNoopCache struct{}

func (errSemNoopCache) InvalidateConversation(context.Context, string) error { return nil }

type errSemNoopPublisher struct{}

func (errSemNoopPublisher) PublishDomainEvent(
	context.Context, string, string, string, map[string]any,
) error {
	return nil
}

func (errSemNoopPublisher) PublishRecordedDomainEvent(
	context.Context, string, string, string, string, map[string]any,
) error {
	return nil
}

func newErrSemMessageService(
	members errSemMemberStore,
	conversations errSemConversationStore,
	messages errSemMessageStore,
	media errSemMediaReader,
) *MessageService {
	return NewMessageService(
		ChatStoragePorts{
			Conversations:     conversations,
			Messages:          messages,
			MessageProjection: errSemProjector{},
			Members:           members,
		},
		errSemNoopCache{},
		errSemNoopPublisher{},
		AllowRelationshipGateForTest(),
		media,
	)
}

func requireAppErrorCode(t *testing.T, err error, wantCode string) {
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

func errSemActiveGroupMember() (*conversationmodel.ConversationMember, *conversationmodel.Conversation) {
	member := &conversationmodel.ConversationMember{
		ID: "member-sender", ConversationId: "conv-sem", UserId: "sender-sem",
		MemberType: "user", Role: "member", JoinedAt: time.Now().UTC(),
	}
	conversation := &conversationmodel.Conversation{
		ID: "conv-sem", Type: "group", Status: "active", CreatorId: "owner-sem",
	}
	return member, conversation
}

func TestRecallMessageWithoutIdentityEmitsUnauthorized(t *testing.T) {
	service := newErrSemMessageService(
		errSemMemberStore{}, errSemConversationStore{}, errSemMessageStore{}, errSemMediaReader{},
	)

	err := service.RecallMessage(context.Background(), "", "message-sem", "")
	requireAppErrorCode(t, err, "CHAT.USER.unauthorized")
}

func TestRecallMessageByNonSenderEmitsRecallForbidden(t *testing.T) {
	member, _ := errSemActiveGroupMember()
	service := newErrSemMessageService(
		errSemMemberStore{member: member},
		errSemConversationStore{},
		errSemMessageStore{message: &messagemodel.Message{
			ID: "message-sem", ConversationID: "conv-sem", SenderID: "someone-else",
			Status: "sent", Timestamp: time.Now().UTC(),
		}},
		errSemMediaReader{},
	)

	err := service.RecallMessage(context.Background(), "conv-sem", "message-sem", "sender-sem")
	requireAppErrorCode(t, err, "CHAT.USER.message_recall_forbidden")
}

func TestRecallMessageAfterWindowEmitsRecallExpired(t *testing.T) {
	member, _ := errSemActiveGroupMember()
	service := newErrSemMessageService(
		errSemMemberStore{member: member},
		errSemConversationStore{},
		errSemMessageStore{message: &messagemodel.Message{
			ID: "message-sem", ConversationID: "conv-sem", SenderID: "sender-sem",
			Status: "sent", Timestamp: time.Now().UTC().Add(-time.Hour),
		}},
		errSemMediaReader{},
	)

	err := service.RecallMessage(context.Background(), "conv-sem", "message-sem", "sender-sem")
	requireAppErrorCode(t, err, "CHAT.USER.message_recall_expired")
}

func TestSendMessageOverRuneLimitEmitsMessageTooLong(t *testing.T) {
	member, conversation := errSemActiveGroupMember()
	service := newErrSemMessageService(
		errSemMemberStore{member: member},
		errSemConversationStore{conversation: conversation},
		errSemMessageStore{},
		errSemMediaReader{},
	)

	_, err := service.SendMessage(context.Background(), SendMessageRequest{
		ConversationId: "conv-sem",
		SenderId:       "sender-sem",
		ClientMsgId:    "client-sem-too-long",
		Type:           "text",
		Content:        strings.Repeat("长", 5001),
	})
	requireAppErrorCode(t, err, "CHAT.USER.message_too_long")
}

func TestSendMessageWithFailingMediaReaderEmitsMessageMediaUnavailable(t *testing.T) {
	member, conversation := errSemActiveGroupMember()
	service := newErrSemMessageService(
		errSemMemberStore{member: member},
		errSemConversationStore{conversation: conversation},
		errSemMessageStore{},
		errSemMediaReader{err: errors.New("media delivery store unreachable")},
	)

	_, err := service.SendMessage(context.Background(), SendMessageRequest{
		ConversationId: "conv-sem",
		SenderId:       "sender-sem",
		ClientMsgId:    "client-sem-media",
		Type:           "image",
		MediaAssetID:   "asset-sem",
	})
	requireAppErrorCode(t, err, "CHAT.SYSTEM.message_media_unavailable")
}
