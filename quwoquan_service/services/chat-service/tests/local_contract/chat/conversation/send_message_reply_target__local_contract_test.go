// spec_ref: specs/feature-tree/chat-conversation/spec.md#dom-002
// spec_ref: specs/feature-tree/chat-conversation/list-detail-message-delivery/voice-message/spec.md#gwt-004.t1
// spec_ref: specs/feature-tree/chat-conversation/list-detail-message-delivery/voice-message/spec.md#gwt-004.t2
// spec_ref: specs/feature-tree/chat-conversation/list-detail-message-delivery/voice-message/spec.md#gwt-004.t3
//
// 引用回复目标的服务端校验：replyToMessageId 必须指向同会话内已存在的
// 消息（脏 ID 不入库，接收端引用块不出现永不可解析的引用）；
// 不存在或跨会话引用返回 canonical MessageInvalid。
// 语音元数据契约：audio 消息必须绑定 owner-scoped ready audio MediaAsset
//（gwt-004.t1），audioDurationMs/audioWaveform 仅 type=audio 合法且按
// 发送值落库（gwt-004.t2）。
package local_contract

import (
	"context"
	"errors"
	"strings"
	"testing"

	. "quwoquan_service/services/chat-service/internal/chat/conversation/application"
	conversationmodel "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
	rerrors "quwoquan_service/runtime/errors"
	messagemodel "quwoquan_service/services/chat-service/internal/chat/message/domain/model"
	messageports "quwoquan_service/services/chat-service/internal/chat/message/domain/ports"
)

func newReplyTargetFixture(
	store *replyTargetMessageStore,
) *MessageService {
	return NewMessageService(
		ChatStoragePorts{
			Conversations:     replyTargetConversationStore{},
			Members:           replyTargetMemberStore{},
			Messages:          store,
			MessageProjection: &rtcCallLogProjectionStub{},
		},
		&rtcCallLogCacheStub{},
		syncNoopEventPublisher{},
		nil,
		readyAudioAssetReader{},
	)
}

// 发送者自有、ready 的 audio MediaAsset（audio 元数据用例的媒体前置）。
type readyAudioAssetReader struct{}

func (readyAudioAssetReader) ReadOwnedReadyAsset(
	_ context.Context,
	assetID string,
	ownerPersonaID string,
) (messageports.MediaAssetDeliverySlice, bool, error) {
	return messageports.MediaAssetDeliverySlice{
		AssetID:          assetID,
		OwnerPersonaID:   ownerPersonaID,
		ProcessingStatus: "ready",
		MediaType:        "audio",
		ContentType:      "audio/m4a",
		FileSize:         2048,
		DeliveryURL:      "https://media.example.test/audio/" + assetID,
	}, true, nil
}

func replyRequest(replyTo string) SendMessageRequest {
	return SendMessageRequest{
		ConversationId:   "conversation-reply-1",
		SenderId:         "persona-sender",
		SenderAccountID:  "account-sender",
		Type:             "text",
		Content:          "引用回复正文",
		ClientMsgId:      "reply-client-1",
		ReplyToMessageId: replyTo,
	}
}

func TestSendMessageAcceptsReplyToExistingMessageInSameConversation(t *testing.T) {
	store := &replyTargetMessageStore{
		existing: map[string]*messagemodel.Message{
			"msg-origin-1": {
				ID:             "msg-origin-1",
				ConversationID: "conversation-reply-1",
				Type:           "text",
				Content:        "原始消息",
			},
		},
	}
	service := newReplyTargetFixture(store)

	resp, err := service.SendMessage(context.Background(), replyRequest("msg-origin-1"))
	if err != nil || resp == nil {
		t.Fatalf("reply to existing message must succeed, got %v", err)
	}
	if store.committed == nil ||
		store.committed.Message.ReplyToMessageID != "msg-origin-1" {
		t.Fatalf("committed message must carry reply target: %+v", store.committed)
	}
}

func TestSendMessageRejectsReplyToMissingMessage(t *testing.T) {
	service := newReplyTargetFixture(&replyTargetMessageStore{})

	_, err := service.SendMessage(context.Background(), replyRequest("msg-ghost"))
	assertMessageInvalid(t, err, "missing reply target")
}

func TestSendMessageRejectsReplyAcrossConversations(t *testing.T) {
	store := &replyTargetMessageStore{
		existing: map[string]*messagemodel.Message{
			"msg-other-conv": {
				ID:             "msg-other-conv",
				ConversationID: "conversation-other",
				Type:           "text",
				Content:        "别的会话的消息",
			},
		},
	}
	service := newReplyTargetFixture(store)

	_, err := service.SendMessage(context.Background(), replyRequest("msg-other-conv"))
	assertMessageInvalid(t, err, "cross-conversation reply target")
}

// 语音元数据（audioDurationMs/audioWaveform）契约：仅 type=audio 允许携带；
// 落库消息必须保留发送侧提供的真实值。
func TestSendMessageRejectsAudioMetadataOnNonAudioMessage(t *testing.T) {
	service := newReplyTargetFixture(&replyTargetMessageStore{})

	req := replyRequest("")
	req.AudioDurationMs = 3200
	_, err := service.SendMessage(context.Background(), req)
	assertMessageInvalid(t, err, "text message carrying audioDurationMs")

	req = replyRequest("")
	req.AudioWaveform = []float64{0.1, 0.5}
	_, err = service.SendMessage(context.Background(), req)
	assertMessageInvalid(t, err, "text message carrying audioWaveform")
}

func TestSendMessageRejectsOversizedAudioWaveform(t *testing.T) {
	service := newReplyTargetFixture(&replyTargetMessageStore{})

	req := replyRequest("")
	req.Type = "audio"
	req.Content = ""
	req.MediaAssetID = "media-audio-1"
	req.AudioWaveform = make([]float64, 129)
	_, err := service.SendMessage(context.Background(), req)
	assertMessageInvalid(t, err, "audio waveform above 128 samples")
}

func TestSendMessagePersistsAudioMetadataForAudioMessage(t *testing.T) {
	store := &replyTargetMessageStore{}
	service := newReplyTargetFixture(store)

	req := replyRequest("")
	req.Type = "audio"
	req.Content = ""
	req.MediaAssetID = "media-audio-1"
	req.AudioDurationMs = 4700
	req.AudioWaveform = []float64{0.2, 0.8, 0.4}
	if _, err := service.SendMessage(context.Background(), req); err != nil {
		t.Fatalf("audio message with metadata must succeed, got %v", err)
	}
	committed := store.committed
	if committed == nil {
		t.Fatal("audio message must be committed")
	}
	// gwt-004.t1：audio Message 只保存强类型 MediaAsset 引用；
	// URL 等交付字段由 Reader projection 提供，聚合不落任何临时 URL。
	if committed.Message.MediaAssetID != "media-audio-1" {
		t.Fatalf(
			"audio message must persist the typed MediaAsset reference, got %q",
			committed.Message.MediaAssetID,
		)
	}
	if strings.Contains(committed.Message.Content, "http") {
		t.Fatalf(
			"audio message must not persist delivery URLs, got content %q",
			committed.Message.Content,
		)
	}
	if committed.Message.AudioDurationMs != 4700 {
		t.Fatalf("audioDurationMs must persist, got %d", committed.Message.AudioDurationMs)
	}
	if len(committed.Message.AudioWaveform) != 3 ||
		committed.Message.AudioWaveform[1] != 0.8 {
		t.Fatalf("audioWaveform must persist, got %v", committed.Message.AudioWaveform)
	}
}

func assertMessageInvalid(t *testing.T, err error, scenario string) {
	t.Helper()
	if err == nil {
		t.Fatalf("%s must be rejected", scenario)
	}
	var appErr *rerrors.AppError
	if !errors.As(err, &appErr) {
		t.Fatalf("%s must map to canonical AppError, got %T %v", scenario, err, err)
	}
}

type replyTargetConversationStore struct {
	ConversationStore
}

func (replyTargetConversationStore) FindConversationByID(
	context.Context,
	string,
) (*conversationmodel.Conversation, error) {
	return &conversationmodel.Conversation{
		ID:     "conversation-reply-1",
		Type:   "group",
		Status: "active",
	}, nil
}

type replyTargetMemberStore struct {
	MemberStore
}

func (replyTargetMemberStore) FindMember(
	_ context.Context,
	conversationID string,
	personaID string,
) (*conversationmodel.ConversationMember, error) {
	return &conversationmodel.ConversationMember{
		ID:             "member-sender",
		ConversationId: conversationID,
		UserId:         personaID,
		MemberType:     "user",
		Role:           "member",
	}, nil
}

type replyTargetMessageStore struct {
	rtcCallLogMessageStoreStub
	existing  map[string]*messagemodel.Message
	committed *MessageCommit
}

func (s *replyTargetMessageStore) FindMessageByID(
	_ context.Context,
	messageID string,
) (*messagemodel.Message, error) {
	if msg, ok := s.existing[messageID]; ok {
		copied := *msg
		return &copied, nil
	}
	return nil, messagemodel.ErrMessageNotFound
}

func (s *replyTargetMessageStore) CommitMessage(
	_ context.Context,
	commit MessageCommit,
) (MessageCommitResult, error) {
	s.committed = &commit
	return MessageCommitResult{Message: commit.Message, Events: commit.Events}, nil
}
