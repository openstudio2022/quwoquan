package application

import (
	"context"
	"strings"

	rterr "quwoquan_service/runtime/errors"
	messagemodel "quwoquan_service/services/chat-service/internal/chat/message/domain/model"
	messageports "quwoquan_service/services/chat-service/internal/chat/message/domain/ports"
)

type SendMessageRequest struct {
	ConversationId            string
	SenderId                  string
	SenderAccountID           string
	PersonaContextVersion     int64
	SenderDisplayNameSnapshot string
	SenderAvatarUrlSnapshot   string
	Type                      string
	Content                   string
	MediaAssetID              string
	AudioDurationMs           int64
	AudioWaveform             []float64
	Card                      *MessageCardCommand
	ReplyToMessageId          string
	Mentions                  []string
	ClientMsgId               string
}

type MessageCardCommand struct {
	Kind         string                        `json:"kind"`
	Title        string                        `json:"title"`
	ObjectRef    *MessageCardObjectRefCommand  `json:"objectRef"`
	Subtitle     string                        `json:"subtitle"`
	ThumbnailURL string                        `json:"thumbnailUrl"`
	DeepLink     string                        `json:"deeplink"`
	LandingURL   string                        `json:"landingUrl"`
	ShareText    string                        `json:"shareText"`
	Message      string                        `json:"message"`
	Attributes   []MessageCardAttributeCommand `json:"attributes"`
}

type MessageCardObjectRefCommand struct {
	ObjectTypeRef string `json:"objectTypeRef"`
	ObjectID      string `json:"objectId"`
	RouteID       string `json:"routeId"`
}

type MessageCardAttributeCommand struct {
	Name  string `json:"name"`
	Value string `json:"value"`
}

type SendMessageResponse struct {
	MessageId string `json:"messageId"`
	Seq       int64  `json:"seq"`
	Timestamp string `json:"timestamp"`
}

type AssistantDeliveryMessageRequest struct {
	ConversationID   string
	CreatorPersonaID string
	Type             string
	Content          string
	ClientMsgID      string
}

type ListMessagesRequest struct {
	ConversationId string
	ViewerID       string
	Limit          int
	AfterSeq       int64
	BeforeSeq      int64
	Cursor         string
}

type MessageSlice struct {
	Message messagemodel.Message
	Media   *messageports.MediaAssetDeliverySlice
}

type SyncMessagesRequest struct {
	ConversationId string
	ViewerID       string
	LastSeq        int64
	Limit          int
}

type SyncMessagesResponse struct {
	Messages []MessageSlice `json:"-"`
	HasMore  bool           `json:"hasMore"`
}

type Backend interface {
	SendMessage(context.Context, SendMessageRequest) (*SendMessageResponse, error)
	SendAssistantDeliveryMessage(
		context.Context,
		AssistantDeliveryMessageRequest,
	) (*SendMessageResponse, error)
	RecallMessage(context.Context, string, string, string) error
	ListMessages(context.Context, ListMessagesRequest) ([]MessageSlice, error)
	ListAssistantGroundingMessages(
		context.Context,
		string,
		string,
		int64,
		int,
	) ([]MessageSlice, error)
	SyncMessages(context.Context, SyncMessagesRequest) (*SyncMessagesResponse, error)
}

type UseCases struct{ backend Backend }

func NewUseCases(backend Backend) *UseCases {
	if backend == nil {
		panic("message backend is required")
	}
	return &UseCases{backend: backend}
}

func (s *UseCases) Send(ctx context.Context, req SendMessageRequest) (*SendMessageResponse, error) {
	if strings.TrimSpace(req.ConversationId) == "" ||
		strings.TrimSpace(req.SenderId) == "" ||
		strings.TrimSpace(req.SenderAccountID) == "" {
		return nil, rterr.NewInvalidArgument(
			rterr.ModuleChat,
			"conversationId 和发送者身份不能为空",
			"missing trusted message account or persona owner",
		)
	}
	return s.backend.SendMessage(ctx, req)
}
func (s *UseCases) SendAssistantDelivery(
	ctx context.Context,
	req AssistantDeliveryMessageRequest,
) (*SendMessageResponse, error) {
	return s.backend.SendAssistantDeliveryMessage(ctx, req)
}
func (s *UseCases) Recall(ctx context.Context, conversationID, messageID, senderID string) error {
	return s.backend.RecallMessage(ctx, conversationID, messageID, senderID)
}
func (s *UseCases) List(ctx context.Context, req ListMessagesRequest) ([]MessageSlice, error) {
	return s.backend.ListMessages(ctx, req)
}
func (s *UseCases) ListAssistantGrounding(
	ctx context.Context,
	conversationID string,
	creatorPersonaID string,
	beforeSeq int64,
	limit int,
) ([]MessageSlice, error) {
	return s.backend.ListAssistantGroundingMessages(
		ctx,
		conversationID,
		creatorPersonaID,
		beforeSeq,
		limit,
	)
}
func (s *UseCases) Sync(ctx context.Context, req SyncMessagesRequest) (*SyncMessagesResponse, error) {
	return s.backend.SyncMessages(ctx, req)
}
