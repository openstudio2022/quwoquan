// Message 聚合的事务提交、outbox relay 与读端口实现（MongoChatStore 分文件）。
package persistence

import (
	"context"
	"crypto/sha256"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/chat-service/internal/chat/conversation/application"
	model "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
	messagemodel "quwoquan_service/services/chat-service/internal/chat/message/domain/model"
	messageports "quwoquan_service/services/chat-service/internal/chat/message/domain/ports"
)

type messageCommandReceiptDocument struct {
	ID            string               `bson:"_id"`
	MessageID     string               `bson:"messageId"`
	CommandDigest string               `bson:"commandDigest"`
	Result        messagemodel.Message `bson:"result"`
	CreatedAt     time.Time            `bson:"createdAt"`
}

type messageOutboxDocument struct {
	ID               string         `bson:"_id"`
	OutboxSequence   int64          `bson:"outboxSequence"`
	AggregateID      string         `bson:"aggregateId"`
	AggregateVersion int64          `bson:"aggregateVersion"`
	EventType        string         `bson:"eventType"`
	ConversationID   string         `bson:"conversationId"`
	ActorID          string         `bson:"actorId"`
	Payload          map[string]any `bson:"payload"`
	Status           string         `bson:"status"`
	CreatedAt        time.Time      `bson:"createdAt"`
	DispatchedAt     *time.Time     `bson:"dispatchedAt,omitempty"`
}

type messageSequenceDocument struct {
	ID        string    `bson:"_id"`
	Seq       int64     `bson:"seq"`
	UpdatedAt time.Time `bson:"updatedAt"`
}

type messageOutboxSequenceDocument struct {
	ID  string `bson:"_id"`
	Seq int64  `bson:"seq"`
}

type messageProjectionCheckpointDocument struct {
	ID        string    `bson:"_id"`
	Sequence  int64     `bson:"sequence"`
	UpdatedAt time.Time `bson:"updatedAt"`
}

func (s *MongoChatStore) CommitMessage(
	ctx context.Context,
	commit application.MessageCommit,
) (application.MessageCommitResult, error) {
	message := commit.Message
	if strings.TrimSpace(message.ID) == "" ||
		strings.TrimSpace(message.ConversationID) == "" ||
		strings.TrimSpace(message.SenderID) == "" ||
		strings.TrimSpace(message.ClientMessageID) == "" ||
		strings.TrimSpace(commit.CommandDigest) == "" {
		return application.MessageCommitResult{}, errors.New("message commit identity and command digest are required")
	}
	if message.Version != 1 {
		return application.MessageCommitResult{}, errors.New("new message aggregate version must be 1")
	}
	receiptID := messageReceiptID(message)
	if replay, ok, err := s.loadMessageCommitReplay(ctx, receiptID, commit.CommandDigest); err != nil || ok {
		return replay, err
	}

	var result application.MessageCommitResult
	err := s.RunInTransaction(ctx, func(txCtx context.Context) error {
		if replay, ok, loadErr := s.loadMessageCommitReplay(txCtx, receiptID, commit.CommandDigest); loadErr != nil {
			return loadErr
		} else if ok {
			result = replay
			return nil
		}
		var sequence messageSequenceDocument
		if sequenceErr := s.messageSequences.FindOneAndUpdate(
			txCtx,
			bson.M{"_id": message.ConversationID},
			bson.M{
				"$inc": bson.M{"seq": 1},
				"$set": bson.M{"updatedAt": message.Timestamp.UTC()},
			},
			options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After),
		).Decode(&sequence); sequenceErr != nil {
			return sequenceErr
		}
		message.Seq = sequence.Seq
		events := bindMessageOutboxEvents(message, commit.Events)
		outboxSequenceStart := int64(0)
		if len(events) > 0 {
			var outboxSequence messageOutboxSequenceDocument
			if sequenceErr := s.messageOutboxSequences.FindOneAndUpdate(
				txCtx,
				bson.M{"_id": "Message"},
				bson.M{"$inc": bson.M{"seq": len(events)}},
				options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After),
			).Decode(&outboxSequence); sequenceErr != nil {
				return sequenceErr
			}
			outboxSequenceStart = outboxSequence.Seq - int64(len(events)) + 1
		}
		if _, insertErr := s.messages.InsertOne(txCtx, message); insertErr != nil {
			return insertErr
		}
		if _, insertErr := s.messageCommandReceipts.InsertOne(txCtx, messageCommandReceiptDocument{
			ID:            receiptID,
			MessageID:     message.ID,
			CommandDigest: commit.CommandDigest,
			Result:        message,
			CreatedAt:     message.Timestamp.UTC(),
		}); insertErr != nil {
			return insertErr
		}
		for index, event := range events {
			if strings.TrimSpace(event.EventID) == "" ||
				strings.TrimSpace(event.EventType) == "" ||
				event.ConversationID != message.ConversationID ||
				event.ActorID != message.SenderID {
				return errors.New("message outbox event does not match aggregate commit")
			}
			if _, insertErr := s.messageOutbox.InsertOne(txCtx, messageOutboxDocument{
				ID:               event.EventID,
				OutboxSequence:   outboxSequenceStart + int64(index),
				AggregateID:      message.ID,
				AggregateVersion: message.Version,
				EventType:        event.EventType,
				ConversationID:   event.ConversationID,
				ActorID:          event.ActorID,
				Payload:          event.Payload,
				Status:           "pending",
				CreatedAt:        message.Timestamp.UTC(),
			}); insertErr != nil {
				return insertErr
			}
		}
		result = application.MessageCommitResult{Message: message, Events: events}
		return nil
	})
	if mongo.IsDuplicateKeyError(err) {
		if replay, ok, loadErr := s.loadMessageCommitReplay(ctx, receiptID, commit.CommandDigest); loadErr != nil || ok {
			return replay, loadErr
		}
	}
	return result, err
}

// AppendMessageOutboxEvent 在调用方事务内为已提交消息追加一条事件；
// (aggregateId, aggregateVersion, eventType) 唯一索引把重放折叠为幂等。
func (s *MongoChatStore) AppendMessageOutboxEvent(
	ctx context.Context,
	event messageports.OutboxEvent,
	aggregateID string,
	aggregateVersion int64,
) error {
	var outboxSequence messageOutboxSequenceDocument
	if err := s.messageOutboxSequences.FindOneAndUpdate(
		ctx,
		bson.M{"_id": "Message"},
		bson.M{"$inc": bson.M{"seq": 1}},
		options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After),
	).Decode(&outboxSequence); err != nil {
		return err
	}
	if _, err := s.messageOutbox.InsertOne(ctx, messageOutboxDocument{
		ID:               event.EventID,
		OutboxSequence:   outboxSequence.Seq,
		AggregateID:      aggregateID,
		AggregateVersion: aggregateVersion,
		EventType:        event.EventType,
		ConversationID:   event.ConversationID,
		ActorID:          event.ActorID,
		Payload:          event.Payload,
		Status:           "pending",
		CreatedAt:        time.Now().UTC(),
	}); err != nil {
		if mongo.IsDuplicateKeyError(err) {
			return nil
		}
		return err
	}
	return nil
}

func bindMessageOutboxEvents(
	message messagemodel.Message,
	events []messageports.OutboxEvent,
) []messageports.OutboxEvent {
	bound := make([]messageports.OutboxEvent, 0, len(events))
	for _, event := range events {
		payload := make(map[string]any, len(event.Payload)+3)
		for key, value := range event.Payload {
			payload[key] = value
		}
		payload["messageId"] = message.ID
		payload["seq"] = message.Seq
		payload["timestamp"] = message.Timestamp.UTC()
		event.Payload = payload
		event.Status = "pending"
		bound = append(bound, event)
	}
	return bound
}

func (s *MongoChatStore) MarkMessageOutboxDispatched(
	ctx context.Context,
	eventID string,
	dispatchedAt time.Time,
) error {
	result, err := s.messageOutbox.UpdateOne(
		ctx,
		bson.M{"_id": strings.TrimSpace(eventID), "status": "pending"},
		bson.M{"$set": bson.M{"status": "dispatched", "dispatchedAt": dispatchedAt.UTC()}},
	)
	if err != nil {
		return err
	}
	if result.MatchedCount == 0 {
		var existing messageOutboxDocument
		if err := s.messageOutbox.FindOne(ctx, bson.M{"_id": strings.TrimSpace(eventID), "status": "dispatched"}).Decode(&existing); err == nil {
			return nil
		}
		return fmt.Errorf("message outbox event %s is not pending", eventID)
	}
	return nil
}

func (s *MongoChatStore) ReadMessageOutboxAfter(
	ctx context.Context,
	checkpoint string,
	limit int,
) ([]messageports.OutboxEvent, error) {
	if limit <= 0 {
		limit = 100
	}
	if limit > 1000 {
		limit = 1000
	}
	filter := bson.M{}
	if strings.TrimSpace(checkpoint) != "" {
		sequence, err := parseMessageOutboxCheckpoint(checkpoint)
		if err != nil {
			return nil, err
		}
		filter["outboxSequence"] = bson.M{"$gt": sequence}
	}
	cursor, err := s.messageOutbox.Find(
		ctx,
		filter,
		options.Find().
			SetSort(bson.D{{Key: "outboxSequence", Value: 1}}).
			SetLimit(int64(limit)),
	)
	if err != nil {
		return nil, fmt.Errorf("read message outbox: %w", err)
	}
	defer cursor.Close(ctx)

	events := make([]messageports.OutboxEvent, 0, limit)
	for cursor.Next(ctx) {
		var document messageOutboxDocument
		if err := cursor.Decode(&document); err != nil {
			return nil, fmt.Errorf("decode message outbox: %w", err)
		}
		events = append(events, messageOutboxEventFromDocument(document))
	}
	if err := cursor.Err(); err != nil {
		return nil, fmt.Errorf("iterate message outbox: %w", err)
	}
	return events, nil
}

func (s *MongoChatStore) LoadMessageOutboxCheckpoint(
	ctx context.Context,
	consumer string,
) (string, error) {
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		return "", errors.New("message outbox consumer is required")
	}
	var document messageProjectionCheckpointDocument
	err := s.messageCheckpoints.FindOne(ctx, bson.M{"_id": "message:" + consumer}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return "", nil
	}
	if err != nil {
		return "", fmt.Errorf("load message outbox checkpoint: %w", err)
	}
	if document.Sequence <= 0 {
		return "", nil
	}
	return strconv.FormatInt(document.Sequence, 10), nil
}

func (s *MongoChatStore) SaveMessageOutboxCheckpoint(
	ctx context.Context,
	consumer string,
	checkpoint string,
) error {
	consumer = strings.TrimSpace(consumer)
	if consumer == "" {
		return errors.New("message outbox consumer is required")
	}
	sequence, err := parseMessageOutboxCheckpoint(checkpoint)
	if err != nil {
		return err
	}
	_, err = s.messageCheckpoints.UpdateOne(
		ctx,
		bson.M{"_id": "message:" + consumer},
		bson.M{
			"$max": bson.M{"sequence": sequence},
			"$set": bson.M{"updatedAt": time.Now().UTC()},
		},
		options.UpdateOne().SetUpsert(true),
	)
	if err != nil {
		return fmt.Errorf("save message outbox checkpoint: %w", err)
	}
	return nil
}

func parseMessageOutboxCheckpoint(checkpoint string) (int64, error) {
	sequence, err := strconv.ParseInt(strings.TrimSpace(checkpoint), 10, 64)
	if err != nil || sequence <= 0 {
		return 0, errors.New("invalid message outbox checkpoint")
	}
	return sequence, nil
}

func messageOutboxEventFromDocument(document messageOutboxDocument) messageports.OutboxEvent {
	payload := document.Payload
	if raw, ok := payload["mentions"].(bson.A); ok {
		mentions := make([]string, 0, len(raw))
		for _, item := range raw {
			if mention, stringValue := item.(string); stringValue {
				mentions = append(mentions, mention)
			}
		}
		payload["mentions"] = mentions
	}
	return messageports.OutboxEvent{
		EventID:        document.ID,
		EventType:      document.EventType,
		ConversationID: document.ConversationID,
		ActorID:        document.ActorID,
		Payload:        payload,
		Status:         document.Status,
		Checkpoint:     strconv.FormatInt(document.OutboxSequence, 10),
	}
}

func (s *MongoChatStore) loadMessageCommitReplay(
	ctx context.Context,
	receiptID string,
	commandDigest string,
) (application.MessageCommitResult, bool, error) {
	var receipt messageCommandReceiptDocument
	if err := s.messageCommandReceipts.FindOne(ctx, bson.M{"_id": receiptID}).Decode(&receipt); err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return application.MessageCommitResult{}, false, nil
		}
		return application.MessageCommitResult{}, false, err
	}
	if receipt.CommandDigest != commandDigest {
		return application.MessageCommitResult{}, false, messagemodel.ErrMessageIdempotencyConflict
	}
	cursor, err := s.messageOutbox.Find(
		ctx,
		bson.M{"aggregateId": receipt.MessageID, "status": "pending"},
		options.Find().SetSort(bson.D{{Key: "createdAt", Value: 1}, {Key: "_id", Value: 1}}),
	)
	if err != nil {
		return application.MessageCommitResult{}, false, err
	}
	defer cursor.Close(ctx)
	events := make([]messageports.OutboxEvent, 0)
	for cursor.Next(ctx) {
		var document messageOutboxDocument
		if err := cursor.Decode(&document); err != nil {
			return application.MessageCommitResult{}, false, err
		}
		events = append(events, messageOutboxEventFromDocument(document))
	}
	if err := cursor.Err(); err != nil {
		return application.MessageCommitResult{}, false, err
	}
	return application.MessageCommitResult{Message: receipt.Result, Events: events, Replayed: true}, true, nil
}

func messageReceiptID(message messagemodel.Message) string {
	sum := sha256.Sum256([]byte(
		message.ConversationID + "\x00" + message.SenderID + "\x00" + message.ClientMessageID,
	))
	return fmt.Sprintf("message-receipt:%x", sum[:])
}

func (s *MongoChatStore) FindMessageByID(ctx context.Context, id string) (*messagemodel.Message, error) {
	var msg messagemodel.Message
	err := s.messages.FindOne(ctx, bson.M{"_id": id}).Decode(&msg)
	if err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return nil, fmt.Errorf("%w: %s", messagemodel.ErrMessageNotFound, id)
		}
		return nil, fmt.Errorf("message not found: %w", err)
	}
	return &msg, nil
}

func (s *MongoChatStore) FindMessageByClientMsgID(ctx context.Context, conversationId, clientMsgId string) (*messagemodel.Message, error) {
	var msg messagemodel.Message
	err := s.messages.FindOne(ctx, bson.M{
		"conversationId": conversationId,
		"clientMsgId":    clientMsgId,
	}).Decode(&msg)
	if err != nil {
		return nil, err
	}
	return &msg, nil
}

func (s *MongoChatStore) ListMessages(ctx context.Context, conversationId string, limit int, afterSeq, beforeSeq int64) ([]messagemodel.Message, error) {
	if limit <= 0 {
		limit = 20
	}

	filter := bson.M{"conversationId": conversationId}
	if afterSeq > 0 {
		filter["seq"] = bson.M{"$gt": afterSeq}
	}
	if beforeSeq > 0 {
		if _, ok := filter["seq"]; ok {
			filter["seq"].(bson.M)["$lt"] = beforeSeq
		} else {
			filter["seq"] = bson.M{"$lt": beforeSeq}
		}
	}

	// 纯 afterSeq 是增量补齐语义（sync gap-fill）：必须从缺口最早处按 seq
	// 递增取满 limit；沿用递减会在缺口大于 limit 时跳过最早的缺口消息，
	// 造成永久缺号。keyset 历史分页（beforeSeq / 无游标取最近）保持递减。
	sortDirection := -1
	if afterSeq > 0 && beforeSeq <= 0 {
		sortDirection = 1
	}
	opts := options.Find().
		SetSort(bson.D{{Key: "seq", Value: sortDirection}}).
		SetLimit(int64(limit))

	cur, err := s.messages.Find(ctx, filter, opts)
	if err != nil {
		return nil, err
	}
	defer cur.Close(ctx)

	var msgs []messagemodel.Message
	if err := cur.All(ctx, &msgs); err != nil {
		return nil, err
	}
	return msgs, nil
}

func (s *MongoChatStore) CountUnreadMessages(
	ctx context.Context,
	conversationID string,
	userID string,
	afterSeq int64,
	throughSeq int64,
) (application.UnreadMessageCounts, error) {
	if throughSeq <= afterSeq {
		return application.UnreadMessageCounts{}, nil
	}
	base := bson.M{
		"conversationId": conversationID,
		"seq":            bson.M{"$gt": afterSeq, "$lte": throughSeq},
		"senderId":       bson.M{"$ne": userID},
	}
	total, err := s.messages.CountDocuments(ctx, base)
	if err != nil {
		return application.UnreadMessageCounts{}, fmt.Errorf(
			"count unread messages: %w",
			err,
		)
	}
	mentionFilter := bson.M{
		"conversationId": base["conversationId"],
		"seq":            base["seq"],
		"senderId":       base["senderId"],
		"mentions":       bson.M{"$in": bson.A{userID, "__all__"}},
	}
	mentioned, err := s.messages.CountDocuments(ctx, mentionFilter)
	if err != nil {
		return application.UnreadMessageCounts{}, fmt.Errorf(
			"count unread mentioned messages: %w",
			err,
		)
	}
	return application.UnreadMessageCounts{
		Total:     int(total),
		Mentioned: int(mentioned),
	}, nil
}

func (s *MongoChatStore) UpdateMessageStatus(ctx context.Context, id, status string) error {
	_, err := s.messages.UpdateOne(ctx, bson.M{"_id": id}, bson.M{
		"$set": bson.M{"status": status},
	})
	return err
}

func (s *MongoChatStore) SetMessageRecalled(ctx context.Context, id string) error {
	now := time.Now()
	_, err := s.messages.UpdateOne(ctx, bson.M{"_id": id}, bson.M{
		"$set": bson.M{"status": "recalled", "recalledAt": now},
	})
	return err
}

func (s *MongoChatStore) ProjectCommittedMessage(ctx context.Context, message messagemodel.Message) error {
	preview := message.PreviewText()
	result, err := s.conversations.UpdateOne(
		ctx,
		bson.M{
			"_id": message.ConversationID,
			"$or": bson.A{
				bson.M{"maxSeq": bson.M{"$exists": false}},
				bson.M{"maxSeq": bson.M{"$lt": message.Seq}},
			},
		},
		bson.M{
			"$set": bson.M{
				"maxSeq":             message.Seq,
				"lastMessageId":      message.ID,
				"lastMessagePreview": preview,
				"lastMessageType":    message.Type,
				"lastMessageTime":    message.Timestamp.UTC(),
				"updatedAt":          message.Timestamp.UTC(),
			},
			"$inc": bson.M{"messageCount": 1},
		},
	)
	if err != nil {
		return err
	}
	if result.MatchedCount == 0 {
		var conversation model.Conversation
		if err := s.conversations.FindOne(ctx, bson.M{"_id": message.ConversationID}).Decode(&conversation); err != nil {
			return err
		}
		if conversation.MaxSeq < message.Seq {
			return fmt.Errorf("conversation %s message projection did not advance to seq %d", message.ConversationID, message.Seq)
		}
	}
	return nil
}

// ── Member ───────────────────────────────────────────────────────────────────
