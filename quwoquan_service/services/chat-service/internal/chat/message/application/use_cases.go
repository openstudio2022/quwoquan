package application

import (
	"context"
	"strings"
	"time"

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

type ListConversationAssetsRequest struct {
	ConversationId string
	ViewerID       string
	Kind           string
	BeforeSeq      int64
	Limit          int
}

// ConversationAssetRow 是群空间相册/文件宫格的索引行 + 交付字段。
type ConversationAssetRow struct {
	MessageID          string
	Seq                int64
	MediaAssetID       string
	MessageType        string
	SenderID           string
	SenderName         string
	FileName           string
	MediaDeliveryURL   string
	MediaContentType   string
	MediaFileSizeBytes int64
	CreatedAt          time.Time
}

type ConversationAssetsPage struct {
	Items         []ConversationAssetRow
	HasMore       bool
	NextBeforeSeq *int64
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
	ListConversationAssets(
		context.Context,
		ListConversationAssetsRequest,
	) (*ConversationAssetsPage, error)
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

func (s *UseCases) ListConversationAssets(
	ctx context.Context,
	req ListConversationAssetsRequest,
) (*ConversationAssetsPage, error) {
	return s.backend.ListConversationAssets(ctx, req)
}
