// chat 会话消息的离线推送投影（chat-offline-push-delivery）：
// 消费 chat-service 的 events.chat.messages durable 扇出，对每个收件人做
// presence 在线抑制，离线收件人写入 push 通道的 NotificationOutboxRecord，
// 由既有通用投递 worker（notification.push.requested）经 integration
// PushDelivery 下发 APNs/FCM。
//
// 诚实边界：
//   - 不写 AppMessage inbox 行——会话消息不是站内互动通知（DEC-003 与
//     commercial-message-system 的通知维度语义）。
//   - 投递记录只携带裁剪后的推送预览，不保留正文全文（REQ-004）。
//   - 幂等键 = 事件 ID + 收件人（REQ-001：同一事件同一收件人最多一个投递作业）。
package application

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	rtid "quwoquan_service/runtime/id"
	"quwoquan_service/runtime/reliabletask"
	jobapplication "quwoquan_service/services/notification-service/internal/notification_delivery/notification_delivery_job/application"
)

// ChatOfflinePushStream 是 chat-service MessageSent 面向本服务的 durable 扇出。
const ChatOfflinePushStream = "events.chat.messages"

// chatOfflinePushPreviewLimit 限制投递记录中的推送预览长度（rune）。
const chatOfflinePushPreviewLimit = 64

// ChatOfflinePushProjectionHandler 把一条 MessageSent durable 事件投影为
// 零到多条 push 投递作业（每个离线收件人一条）。
type ChatOfflinePushProjectionHandler struct {
	presence jobapplication.PersonaPresenceReader
	outbox   NotificationDeliveryOutbox
	now      func() time.Time
}

func NewChatOfflinePushProjectionHandler(
	presence jobapplication.PersonaPresenceReader,
	outbox NotificationDeliveryOutbox,
) (*ChatOfflinePushProjectionHandler, error) {
	if presence == nil || outbox == nil {
		return nil, fmt.Errorf(
			"chat offline push projection requires presence reader and delivery outbox",
		)
	}
	return &ChatOfflinePushProjectionHandler{
		presence: presence,
		outbox:   outbox,
		now:      func() time.Time { return time.Now().UTC() },
	}, nil
}

// Handle 逐收件人投影；单个收件人失败不中断其余收件人，错误聚合返回
// 交由 consumer 的失败计数与 DLQ 机制处理（at-least-once + 幂等键收敛重放）。
func (h *ChatOfflinePushProjectionHandler) Handle(
	ctx context.Context,
	event InteractionStreamEvent,
) error {
	if event.EventType != "MessageSent" {
		return fmt.Errorf("chat offline push projection got unsupported event %q", event.EventType)
	}
	conversationID := strings.TrimSpace(event.Values["conversationId"])
	messageID := strings.TrimSpace(event.Values["messageId"])
	if conversationID == "" || messageID == "" {
		return fmt.Errorf("chat offline push event %s misses conversation or message id", event.EventID)
	}
	var recipients []string
	if raw := strings.TrimSpace(event.Values["recipients"]); raw != "" {
		if err := json.Unmarshal([]byte(raw), &recipients); err != nil {
			return fmt.Errorf("decode chat offline push recipients: %w", err)
		}
	}
	var recipientErrors []error
	for _, recipient := range recipients {
		recipient = strings.TrimSpace(recipient)
		if recipient == "" {
			continue
		}
		if err := h.projectRecipient(ctx, event, conversationID, messageID, recipient); err != nil {
			recipientErrors = append(
				recipientErrors,
				fmt.Errorf("chat offline push for %s: %w", recipient, err),
			)
		}
	}
	return errors.Join(recipientErrors...)
}

func (h *ChatOfflinePushProjectionHandler) projectRecipient(
	ctx context.Context,
	event InteractionStreamEvent,
	conversationID string,
	messageID string,
	recipient string,
) error {
	presence, err := h.presence.GetPersonaPresence(ctx, recipient)
	if err != nil {
		return fmt.Errorf("read presence: %w", err)
	}
	if len(presence.Devices) > 0 {
		// 在线收件人由 realtime 通道即时送达，不产生设备推送作业。
		return nil
	}
	jobID, err := rtid.Generate(rtid.PrefixNotificationDeliveryJob)
	if err != nil {
		return fmt.Errorf("generate delivery job id: %w", err)
	}
	now := h.now()
	record := reliabletask.NotificationOutboxRecord{
		NotificationID:        jobID,
		SubjectNotificationID: messageID,
		Channel:               "push",
		DestinationRef:        recipient,
		EventType:             NotificationPushRequestedEvent,
		OwnerDomain:           "notification",
		AggregateType:         "NotificationDeliveryJob",
		AggregateID:           messageID,
		// REQ-001：同一事件同一收件人最多一个投递作业；stream 重放由该
		// 幂等键收敛。
		DedupeKey: "chat-message:" + event.EventID + ":" + recipient,
		Payload: map[string]string{
			"messageType":    "chat_message",
			"conversationId": conversationID,
			"messageId":      messageID,
			"seq":            strings.TrimSpace(event.Values["seq"]),
			"title":          strings.TrimSpace(event.Values["senderDisplayNameSnapshot"]),
			"summary": chatOfflinePushPreview(
				event.Values["messageType"],
				event.Values["content"],
			),
			// 推送 tap 直达会话的路由锚点（App 端按 conversation 目标分发）。
			"targetType": "conversation",
			"targetId":   conversationID,
		},
		RecipientIDs:  []string{recipient},
		Status:        reliabletask.NotificationStatusPending,
		NextAttemptAt: now,
		CreatedAt:     now,
		UpdatedAt:     now,
		Version:       1,
		AttemptEpoch:  1,
	}
	if _, err := h.outbox.CreateNotification(ctx, record); err != nil {
		return fmt.Errorf("create push delivery record: %w", err)
	}
	return nil
}

// chatOfflinePushPreview 生成投递记录允许携带的最小推送预览：
// 文本消息裁剪到上限，媒体消息只保留类型（正文与媒体细节不入投递记录）。
func chatOfflinePushPreview(messageType string, content string) string {
	switch strings.TrimSpace(messageType) {
	case "text", "":
		trimmed := strings.TrimSpace(content)
		runes := []rune(trimmed)
		if len(runes) <= chatOfflinePushPreviewLimit {
			return trimmed
		}
		return string(runes[:chatOfflinePushPreviewLimit])
	default:
		return ""
	}
}
