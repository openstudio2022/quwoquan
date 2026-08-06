// spec_ref: specs/feature-tree/chat-conversation/commercial-message-system/interaction-notification-inbox/spec.md#gwt-001
// readiness_case: create-app-message-local
// readiness_case: list-app-messages-local
// readiness_case: get-app-message-local
// readiness_case: ack-app-message-local
// readiness_case: read-app-message-local
// readiness_case: get-app-message-unread-count-local
package local_contract

import (
	"context"
	"errors"
	"testing"
	"time"

	"quwoquan_service/runtime/reliabletask"
	"quwoquan_service/services/notification-service/internal/notification_delivery/notification/application"
	notification "quwoquan_service/services/notification-service/internal/notification_delivery/notification/domain"
)

type appMessageMemoryPorts struct {
	messages map[string]notification.AppMessage
	jobs     []reliabletask.NotificationOutboxRecord
}

func newAppMessageMemoryPorts() *appMessageMemoryPorts {
	return &appMessageMemoryPorts{messages: map[string]notification.AppMessage{}}
}

func (p *appMessageMemoryPorts) RunInTransaction(
	ctx context.Context,
	fn func(context.Context) error,
) error {
	return fn(ctx)
}

func (p *appMessageMemoryPorts) Create(
	_ context.Context,
	message notification.AppMessage,
) (notification.AppMessage, bool, error) {
	if existing, ok := p.messages[message.MessageID]; ok {
		return existing, false, nil
	}
	p.messages[message.MessageID] = message
	return message, true, nil
}

func (p *appMessageMemoryPorts) FindByIdempotencyKey(
	_ context.Context,
	key string,
) (notification.AppMessage, bool, error) {
	for _, message := range p.messages {
		if message.IdempotencyKey == key {
			return message, true, nil
		}
	}
	return notification.AppMessage{}, false, nil
}

func (p *appMessageMemoryPorts) Acknowledge(
	_ context.Context,
	userID, messageID string,
	at time.Time,
) (notification.AppMessage, error) {
	message, ok := p.messages[messageID]
	if !ok || message.UserID != userID {
		return notification.AppMessage{}, errors.New("message not found")
	}
	acknowledgedAt := at.UTC()
	message.AckedAt = &acknowledgedAt
	p.messages[messageID] = message
	return message, nil
}

func (p *appMessageMemoryPorts) MarkRead(
	_ context.Context,
	userID, messageID string,
	at time.Time,
) (notification.AppMessage, error) {
	message, ok := p.messages[messageID]
	if !ok || message.UserID != userID {
		return notification.AppMessage{}, errors.New("message not found")
	}
	readAt := at.UTC()
	message.Read = true
	message.ReadAt = &readAt
	p.messages[messageID] = message
	return message, nil
}

func (p *appMessageMemoryPorts) ListInbox(
	_ context.Context,
	query application.AppMessageInboxQuery,
) (notification.AppMessageInboxSlice, error) {
	items := make([]notification.AppMessage, 0, len(p.messages))
	for _, message := range p.messages {
		if message.UserID == query.UserID {
			items = append(items, message)
		}
	}
	return notification.AppMessageInboxSlice{Items: items}, nil
}

func (p *appMessageMemoryPorts) Get(
	_ context.Context,
	userID, messageID string,
) (notification.AppMessage, error) {
	message, ok := p.messages[messageID]
	if !ok || message.UserID != userID {
		return notification.AppMessage{}, errors.New("message not found")
	}
	return message, nil
}

func (p *appMessageMemoryPorts) CountUnread(
	_ context.Context,
	userID string,
) (int64, error) {
	var count int64
	for _, message := range p.messages {
		if message.UserID == userID && !message.Read {
			count++
		}
	}
	return count, nil
}

func (p *appMessageMemoryPorts) CreateNotification(
	_ context.Context,
	record reliabletask.NotificationOutboxRecord,
) (reliabletask.NotificationOutboxRecord, error) {
	p.jobs = append(p.jobs, record)
	return record, nil
}

func TestAppMessageFacadesKeepLifecycleAndUnreadStateOnOneTypedAggregate(t *testing.T) {
	ports := newAppMessageMemoryPorts()
	commands, err := application.NewAppMessageCommandFacade(ports, ports, ports)
	if err != nil {
		t.Fatalf("construct command facade: %v", err)
	}
	queries, err := application.NewAppMessageQueryFacade(ports, ports, ports)
	if err != nil {
		t.Fatalf("construct query facade: %v", err)
	}

	created, err := commands.Create(t.Context(), application.CreateAppMessageCommand{
		IdempotencyKey: "notification-local-1",
		UserID:         "account-local-1",
		MessageType:    "interaction",
		Source:         "comment",
		SourceID:       "comment-local-1",
		Title:          "新的评论",
		Summary:        "有人评论了你的内容",
		Destination: notification.AppMessageDestination{
			Type: "user",
			ID:   "account-local-1",
		},
		Target: notification.AppMessageTarget{
			TargetType: "post",
			TargetID:   "post-local-1",
		},
	})
	if err != nil {
		t.Fatalf("create app message: %v", err)
	}
	if len(ports.jobs) != 1 || ports.jobs[0].SubjectNotificationID != created.MessageID {
		t.Fatalf("delivery job is not bound to aggregate: %+v", ports.jobs)
	}

	inbox, err := queries.ListInbox(t.Context(), application.AppMessageInboxQuery{
		UserID: "account-local-1",
		Limit:  20,
	})
	if err != nil || len(inbox.Items) != 1 || inbox.Items[0].MessageID != created.MessageID {
		t.Fatalf("typed inbox=%+v err=%v", inbox, err)
	}
	detail, err := queries.GetDetail(t.Context(), "account-local-1", created.MessageID)
	if err != nil || detail.MessageID != created.MessageID {
		t.Fatalf("typed detail=%+v err=%v", detail, err)
	}
	unread, err := queries.GetUnreadCount(t.Context(), "account-local-1")
	if err != nil || unread.UnreadCount != 1 {
		t.Fatalf("unread before read=%+v err=%v", unread, err)
	}
	acknowledged, err := commands.Acknowledge(t.Context(), "account-local-1", created.MessageID)
	if err != nil || acknowledged.AckedAt == nil || acknowledged.Read {
		t.Fatalf("acknowledged=%+v err=%v", acknowledged, err)
	}
	read, err := commands.MarkRead(t.Context(), "account-local-1", created.MessageID)
	if err != nil || !read.Read || read.ReadAt == nil {
		t.Fatalf("read=%+v err=%v", read, err)
	}
	unread, err = queries.GetUnreadCount(t.Context(), "account-local-1")
	if err != nil || unread.UnreadCount != 0 {
		t.Fatalf("unread after read=%+v err=%v", unread, err)
	}
}
