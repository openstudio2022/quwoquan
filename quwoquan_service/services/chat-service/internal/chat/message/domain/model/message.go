package model

import (
	"errors"
	"time"
)

var (
	ErrMessageNotFound             = errors.New("message not found")
	ErrMessageIdempotencyConflict  = errors.New("message idempotency conflict")
	ErrMessageReceiptAlreadyExists = errors.New("message receipt already exists")
)

// Message is the aggregate root for one immutable send followed by an optional
// recall transition. Media delivery data belongs to content.MediaAsset; this
// aggregate stores only the stable cross-context reference.
type Message struct {
	ID                        string       `json:"id" bson:"_id"`
	ConversationID            string       `json:"conversationId" bson:"conversationId"`
	Seq                       int64        `json:"seq" bson:"seq"`
	ClientMessageID           string       `json:"clientMsgId" bson:"clientMsgId"`
	SenderID                  string       `json:"senderId" bson:"senderId"`
	SenderDisplayNameSnapshot string       `json:"senderDisplayNameSnapshot,omitempty" bson:"senderDisplayNameSnapshot,omitempty"`
	SenderAvatarURLSnapshot   string       `json:"senderAvatarUrlSnapshot,omitempty" bson:"senderAvatarUrlSnapshot,omitempty"`
	PersonaContextVersion     int64        `json:"personaContextVersion,omitempty" bson:"personaContextVersion,omitempty"`
	Type                      string       `json:"type" bson:"type"`
	Content                   string       `json:"content" bson:"content"`
	MediaAssetID              string       `json:"mediaAssetId,omitempty" bson:"mediaAssetId,omitempty"`
	Card                      *MessageCard `json:"card,omitempty" bson:"card,omitempty"`
	ReplyToMessageID          string       `json:"replyToMessageId,omitempty" bson:"replyToMessageId,omitempty"`
	Mentions                  []string     `json:"mentions,omitempty" bson:"mentions,omitempty"`
	Status                    string       `json:"status" bson:"status"`
	RecalledAt                *time.Time   `json:"recalledAt,omitempty" bson:"recalledAt,omitempty"`
	Timestamp                 time.Time    `json:"timestamp" bson:"timestamp"`
	Version                   int64        `json:"version" bson:"version"`
}

// MessageCard is a Message-owned value object. It has no identity, Store or
// public mutation entrypoint outside the Message aggregate.
type MessageCard struct {
	Kind         string                 `json:"kind" bson:"kind"`
	Title        string                 `json:"title" bson:"title"`
	Subtitle     string                 `json:"subtitle,omitempty" bson:"subtitle,omitempty"`
	ThumbnailURL string                 `json:"thumbnailUrl,omitempty" bson:"thumbnailUrl,omitempty"`
	DeepLink     string                 `json:"deeplink,omitempty" bson:"deeplink,omitempty"`
	LandingURL   string                 `json:"landingUrl,omitempty" bson:"landingUrl,omitempty"`
	ShareText    string                 `json:"shareText,omitempty" bson:"shareText,omitempty"`
	Message      string                 `json:"message,omitempty" bson:"message,omitempty"`
	Attributes   []MessageCardAttribute `json:"attributes" bson:"attributes"`
}

type MessageCardAttribute struct {
	Name  string `json:"name" bson:"name"`
	Value string `json:"value" bson:"value"`
}

// PreviewText is the stable semantic consumed by the Conversation projection.
func (m Message) PreviewText() string {
	switch m.Type {
	case "audio":
		return "[语音消息]"
	case "image":
		return "[图片]"
	case "video":
		return "[视频]"
	case "file":
		return "[文件]"
	case "system_call_log":
		return "[通话]"
	default:
		runes := []rune(m.Content)
		if len(runes) > 100 {
			return string(runes[:100])
		}
		return m.Content
	}
}

// MessageReceipt is an append-only read fact emitted for a Message.
type MessageReceipt struct {
	ID             string    `json:"id" bson:"_id"`
	MessageID      string    `json:"messageId" bson:"messageId"`
	ConversationID string    `json:"conversationId" bson:"conversationId"`
	UserID         string    `json:"userId" bson:"userId"`
	ReadAt         time.Time `json:"readAt" bson:"readAt"`
}
