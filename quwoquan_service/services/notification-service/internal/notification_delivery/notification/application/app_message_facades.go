package application

import (
	"context"
	"fmt"
	"slices"
	"strings"
	"time"

	rtid "quwoquan_service/runtime/id"
	"quwoquan_service/runtime/reliabletask"
	notification "quwoquan_service/services/notification-service/internal/notification_delivery/notification/domain"
	generated "quwoquan_service/services/notification-service/generated/notification_delivery/notification"
)

type AppMessageInboxQuery struct {
	UserID      string
	MessageType string
	Read        *bool
	Cursor      string
	Limit       int
}

type AppMessageInboxReader interface {
	ListInbox(ctx context.Context, query AppMessageInboxQuery) (notification.AppMessageInboxSlice, error)
}

type AppMessageDetailReader interface {
	Get(ctx context.Context, userID, messageID string) (notification.AppMessage, error)
}

type AppMessageUnreadCountReader interface {
	CountUnread(ctx context.Context, userID string) (int64, error)
}

type AppMessageTransactionBoundary interface {
	RunInTransaction(ctx context.Context, fn func(context.Context) error) error
}

type NotificationDeliveryOutbox interface {
	CreateNotification(
		ctx context.Context,
		record reliabletask.NotificationOutboxRecord,
	) (reliabletask.NotificationOutboxRecord, error)
}

type AppMessageCommandFacade struct {
	store  notification.AppMessageAggregateStore
	tx     AppMessageTransactionBoundary
	outbox NotificationDeliveryOutbox
	now    func() time.Time
}

type AppMessageQueryFacade struct {
	inboxReader       AppMessageInboxReader
	detailReader      AppMessageDetailReader
	unreadCountReader AppMessageUnreadCountReader
}

type CreateAppMessageCommand struct {
	IdempotencyKey string                             `json:"-"`
	UserID         string                             `json:"userId"`
	MessageType    string                             `json:"messageType"`
	Source         string                             `json:"source"`
	SourceID       string                             `json:"sourceId"`
	Destination    notification.AppMessageDestination `json:"destination"`
	Title          string                             `json:"title"`
	Summary        string                             `json:"summary"`
	Target         notification.AppMessageTarget      `json:"target"`
	Provenance     notification.AppMessageProvenance  `json:"provenance"`
}

func NewAppMessageCommandFacade(
	store notification.AppMessageAggregateStore,
	tx AppMessageTransactionBoundary,
	outbox NotificationDeliveryOutbox,
) (*AppMessageCommandFacade, error) {
	if store == nil || tx == nil || outbox == nil {
		return nil, fmt.Errorf("app message store, transaction boundary, and delivery outbox are required")
	}
	return &AppMessageCommandFacade{
		store:  store,
		tx:     tx,
		outbox: outbox,
		now:    func() time.Time { return time.Now().UTC() },
	}, nil
}

func NewAppMessageQueryFacade(
	inboxReader AppMessageInboxReader,
	detailReader AppMessageDetailReader,
	unreadCountReader AppMessageUnreadCountReader,
) (*AppMessageQueryFacade, error) {
	if inboxReader == nil || detailReader == nil || unreadCountReader == nil {
		return nil, fmt.Errorf("app message inbox, detail, and unread-count readers are required")
	}
	return &AppMessageQueryFacade{
		inboxReader:       inboxReader,
		detailReader:      detailReader,
		unreadCountReader: unreadCountReader,
	}, nil
}

func (f *AppMessageCommandFacade) Create(
	ctx context.Context,
	command CreateAppMessageCommand,
) (notification.AppMessage, error) {
	normalized, err := f.normalizeCreate(command)
	if err != nil {
		return notification.AppMessage{}, err
	}
	if existing, ok, err := f.store.FindByIdempotencyKey(ctx, normalized.IdempotencyKey); err != nil {
		return notification.AppMessage{}, generated.AppErrorFromStorageReadFailed(err.Error())
	} else if ok {
		if !sameAppMessage(existing, normalized) {
			return notification.AppMessage{}, generated.AppErrorFromIdempotencyConflict("idempotency payload mismatch")
		}
		return existing, nil
	}

	var committed notification.AppMessage
	err = f.tx.RunInTransaction(ctx, func(txCtx context.Context) error {
		created, inserted, createErr := f.store.Create(txCtx, normalized)
		if createErr != nil {
			return generated.AppErrorFromStorageWriteFailed(createErr.Error())
		}
		if !inserted {
			if !sameAppMessage(created, normalized) {
				return generated.AppErrorFromIdempotencyConflict("idempotency payload mismatch")
			}
			committed = created
			return nil
		}
		record, recordErr := deliveryRecord(created)
		if recordErr != nil {
			return generated.AppErrorFromStorageWriteFailed(recordErr.Error())
		}
		if _, outboxErr := f.outbox.CreateNotification(txCtx, record); outboxErr != nil {
			return generated.AppErrorFromStorageWriteFailed(outboxErr.Error())
		}
		committed = created
		return nil
	})
	if err != nil {
		return notification.AppMessage{}, err
	}
	return committed, nil
}

func (f *AppMessageCommandFacade) Acknowledge(
	ctx context.Context,
	userID, messageID string,
) (notification.AppMessage, error) {
	userID, messageID, err := requiredOwnerAndMessage(userID, messageID)
	if err != nil {
		return notification.AppMessage{}, err
	}
	message, err := f.store.Acknowledge(ctx, userID, messageID, f.now())
	if err != nil {
		return notification.AppMessage{}, err
	}
	return message, nil
}

func (f *AppMessageCommandFacade) MarkRead(
	ctx context.Context,
	userID, messageID string,
) (notification.AppMessage, error) {
	userID, messageID, err := requiredOwnerAndMessage(userID, messageID)
	if err != nil {
		return notification.AppMessage{}, err
	}
	message, err := f.store.MarkRead(ctx, userID, messageID, f.now())
	if err != nil {
		return notification.AppMessage{}, err
	}
	return message, nil
}

func (f *AppMessageQueryFacade) ListInbox(
	ctx context.Context,
	query AppMessageInboxQuery,
) (notification.AppMessageInboxSlice, error) {
	query.UserID = strings.TrimSpace(query.UserID)
	query.MessageType = strings.TrimSpace(query.MessageType)
	query.Cursor = strings.TrimSpace(query.Cursor)
	if query.UserID == "" {
		return notification.AppMessageInboxSlice{}, generated.AppErrorFromUnauthorized("missing authenticated account")
	}
	if query.Limit <= 0 {
		query.Limit = 20
	}
	if query.Limit > 100 {
		return notification.AppMessageInboxSlice{}, generated.AppErrorFromInvalidArgument("limit exceeds 100")
	}
	return f.inboxReader.ListInbox(ctx, query)
}

func (f *AppMessageQueryFacade) GetDetail(
	ctx context.Context,
	userID, messageID string,
) (notification.AppMessage, error) {
	userID, messageID, err := requiredOwnerAndMessage(userID, messageID)
	if err != nil {
		return notification.AppMessage{}, err
	}
	return f.detailReader.Get(ctx, userID, messageID)
}

func (f *AppMessageQueryFacade) GetUnreadCount(
	ctx context.Context,
	userID string,
) (notification.AppMessageUnreadCountSlice, error) {
	userID = strings.TrimSpace(userID)
	if userID == "" {
		return notification.AppMessageUnreadCountSlice{}, generated.AppErrorFromUnauthorized("missing authenticated account")
	}
	count, err := f.unreadCountReader.CountUnread(ctx, userID)
	if err != nil {
		return notification.AppMessageUnreadCountSlice{}, err
	}
	return notification.AppMessageUnreadCountSlice{UnreadCount: count}, nil
}

func (f *AppMessageCommandFacade) normalizeCreate(
	command CreateAppMessageCommand,
) (notification.AppMessage, error) {
	command.IdempotencyKey = strings.TrimSpace(command.IdempotencyKey)
	command.UserID = strings.TrimSpace(command.UserID)
	command.MessageType = strings.TrimSpace(command.MessageType)
	command.Source = strings.TrimSpace(command.Source)
	command.SourceID = strings.TrimSpace(command.SourceID)
	command.Title = strings.TrimSpace(command.Title)
	command.Summary = strings.TrimSpace(command.Summary)
	command.Destination.Type = strings.TrimSpace(command.Destination.Type)
	command.Destination.ID = strings.TrimSpace(command.Destination.ID)
	command.Target.TargetType = strings.TrimSpace(command.Target.TargetType)
	command.Target.TargetID = strings.TrimSpace(command.Target.TargetID)
	command.Target.RouteID = strings.TrimSpace(command.Target.RouteID)
	command.Target.RoutePath = strings.TrimSpace(command.Target.RoutePath)
	command.Target.Query.Dimension = strings.TrimSpace(command.Target.Query.Dimension)
	command.Provenance.InterestTags = compactStrings(command.Provenance.InterestTags)
	command.Provenance.MatchedSegments = compactStrings(command.Provenance.MatchedSegments)
	command.Provenance.LifecycleStage = strings.TrimSpace(command.Provenance.LifecycleStage)
	if command.IdempotencyKey == "" || command.UserID == "" || command.Source == "" ||
		command.SourceID == "" || command.Title == "" || command.Summary == "" {
		return notification.AppMessage{}, generated.AppErrorFromInvalidArgument("required app message field is empty")
	}
	if command.MessageType == "" {
		command.MessageType = "system"
	}
	if command.Destination.Type == "" {
		command.Destination.Type = "user"
	}
	if command.Destination.Type != "user" {
		return notification.AppMessage{}, generated.AppErrorFromInvalidArgument("destination type must be user")
	}
	if command.Destination.ID == "" {
		command.Destination.ID = command.UserID
	}
	if command.Destination.ID != command.UserID {
		return notification.AppMessage{}, generated.AppErrorFromInvalidArgument("destination does not match owner")
	}
	messageID, err := rtid.Generate(rtid.PrefixAppMessage)
	if err != nil {
		return notification.AppMessage{}, generated.AppErrorFromStorageWriteFailed(err.Error())
	}
	return notification.AppMessage{
		MessageID:      messageID,
		IdempotencyKey: command.IdempotencyKey,
		UserID:         command.UserID,
		MessageType:    command.MessageType,
		Source:         command.Source,
		SourceID:       command.SourceID,
		Destination:    command.Destination,
		Title:          command.Title,
		Summary:        command.Summary,
		Target:         command.Target,
		Provenance:     command.Provenance,
		CreatedAt:      f.now(),
	}, nil
}

func requiredOwnerAndMessage(userID, messageID string) (string, string, error) {
	userID = strings.TrimSpace(userID)
	messageID = strings.TrimSpace(messageID)
	if userID == "" {
		return "", "", generated.AppErrorFromUnauthorized("missing authenticated account")
	}
	if messageID == "" {
		return "", "", generated.AppErrorFromInvalidArgument("messageId is required")
	}
	return userID, messageID, nil
}

func sameAppMessage(left, right notification.AppMessage) bool {
	return left.UserID == right.UserID &&
		left.MessageType == right.MessageType &&
		left.Source == right.Source &&
		left.SourceID == right.SourceID &&
		left.Destination == right.Destination &&
		left.Title == right.Title &&
		left.Summary == right.Summary &&
		left.Target == right.Target &&
		left.Provenance.Personalized == right.Provenance.Personalized &&
		left.Provenance.LifecycleStage == right.Provenance.LifecycleStage &&
		slices.Equal(left.Provenance.InterestTags, right.Provenance.InterestTags) &&
		slices.Equal(left.Provenance.MatchedSegments, right.Provenance.MatchedSegments)
}

func compactStrings(values []string) []string {
	out := make([]string, 0, len(values))
	seen := make(map[string]struct{}, len(values))
	for _, value := range values {
		normalized := strings.TrimSpace(value)
		if normalized == "" {
			continue
		}
		if _, ok := seen[normalized]; ok {
			continue
		}
		seen[normalized] = struct{}{}
		out = append(out, normalized)
	}
	return out
}

func deliveryRecord(message notification.AppMessage) (reliabletask.NotificationOutboxRecord, error) {
	jobID, err := rtid.Generate(rtid.PrefixNotificationDeliveryJob)
	if err != nil {
		return reliabletask.NotificationOutboxRecord{}, err
	}
	return reliabletask.NotificationOutboxRecord{
		NotificationID:        jobID,
		SubjectNotificationID: message.MessageID,
		Channel:               "push",
		DestinationRef:        message.UserID,
		EventType:             NotificationPushRequestedEvent,
		OwnerDomain:           "notification",
		AggregateType:         "NotificationDeliveryJob",
		AggregateID:           message.MessageID,
		DedupeKey:             "app-message:" + message.IdempotencyKey,
		Payload: map[string]string{
			"messageId":   message.MessageID,
			"messageType": message.MessageType,
			"title":       message.Title,
			"summary":     message.Summary,
			"targetType":  message.Target.TargetType,
			"targetId":    message.Target.TargetID,
		},
		RecipientIDs:  []string{message.UserID},
		Status:        reliabletask.NotificationStatusPending,
		NextAttemptAt: message.CreatedAt,
		CreatedAt:     message.CreatedAt,
		UpdatedAt:     message.CreatedAt,
		Version:       1,
		AttemptEpoch:  1,
	}, nil
}
