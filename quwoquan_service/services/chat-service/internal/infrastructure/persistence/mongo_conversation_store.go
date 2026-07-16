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

	"quwoquan_service/services/chat-service/internal/application"
	messagemodel "quwoquan_service/services/chat-service/internal/domain/chat/message/model"
	model "quwoquan_service/services/chat-service/internal/domain/conversation/model"
)

// MongoChatStore 以 MongoDB 实现应用层的细粒度存储端口。
type MongoChatStore struct {
	db                     *mongo.Database
	conversations          *mongo.Collection
	messages               *mongo.Collection
	members                *mongo.Collection
	userStates             *mongo.Collection
	messageReceipts        *mongo.Collection
	messageCommandReceipts *mongo.Collection
	messageSequences       *mongo.Collection
	messageOutbox          *mongo.Collection
	messageOutboxSequences *mongo.Collection
	messageCheckpoints     *mongo.Collection
}

var (
	_ application.TransactionRunner            = (*MongoChatStore)(nil)
	_ application.ConversationStore            = (*MongoChatStore)(nil)
	_ application.MessageStore                 = (*MongoChatStore)(nil)
	_ application.MessageOutboxReader          = (*MongoChatStore)(nil)
	_ application.MessageOutboxDispatchStore   = (*MongoChatStore)(nil)
	_ application.MessageOutboxCheckpointStore = (*MongoChatStore)(nil)
	_ application.ConversationMessageProjector = (*MongoChatStore)(nil)
	_ application.MemberStore                  = (*MongoChatStore)(nil)
	_ application.UserStateStore               = (*MongoChatStore)(nil)
	_ application.ReceiptStore                 = (*MongoChatStore)(nil)
)

func NewMongoChatStore(db *mongo.Database) *MongoChatStore {
	return &MongoChatStore{
		db:                     db,
		conversations:          db.Collection("conversations"),
		messages:               db.Collection("messages"),
		members:                db.Collection("conversation_memberships"),
		userStates:             db.Collection("conversation_user_states"),
		messageReceipts:        db.Collection("message_receipts"),
		messageCommandReceipts: db.Collection("messages_command_receipts"),
		messageSequences:       db.Collection("messages_sequences"),
		messageOutbox:          db.Collection("messages_outbox"),
		messageOutboxSequences: db.Collection("messages_outbox_sequences"),
		messageCheckpoints:     db.Collection("messages_projection_checkpoints"),
	}
}

func (s *MongoChatStore) EnsureIndexes(ctx context.Context) error {
	indexSets := []struct {
		collection *mongo.Collection
		models     []mongo.IndexModel
	}{
		{s.conversations, []mongo.IndexModel{
			{Keys: bson.D{{Key: "type", Value: 1}, {Key: "updatedAt", Value: -1}}, Options: options.Index().SetName("idx_conv_type_updated")},
			{Keys: bson.D{{Key: "circleId", Value: 1}}, Options: options.Index().SetName("idx_conv_circle").SetSparse(true)},
			{Keys: bson.D{{Key: "circleGroupId", Value: 1}}, Options: options.Index().SetName("idx_conv_circle_group").SetSparse(true)},
			{Keys: bson.D{{Key: "status", Value: 1}}, Options: options.Index().SetName("idx_conv_status")},
			{Keys: bson.D{{Key: "lastMessageTime", Value: -1}}, Options: options.Index().SetName("idx_conv_last_msg_time")},
			{Keys: bson.D{{Key: "originRequestId", Value: 1}}, Options: options.Index().SetName("uq_conv_origin_request").SetUnique(true).SetSparse(true)},
		}},
		{s.messages, []mongo.IndexModel{
			{Keys: bson.D{{Key: "conversationId", Value: 1}, {Key: "seq", Value: 1}}, Options: options.Index().SetName("uq_messages_conversation_seq").SetUnique(true)},
			{Keys: bson.D{{Key: "conversationId", Value: 1}, {Key: "senderId", Value: 1}, {Key: "clientMsgId", Value: 1}}, Options: options.Index().SetName("uq_messages_client_message").SetUnique(true)},
			{Keys: bson.D{{Key: "conversationId", Value: 1}, {Key: "timestamp", Value: -1}}, Options: options.Index().SetName("idx_messages_conversation_time")},
			{Keys: bson.D{{Key: "replyToMessageId", Value: 1}}, Options: options.Index().SetName("idx_messages_reply").SetSparse(true)},
		}},
		{s.members, []mongo.IndexModel{
			{Keys: bson.D{{Key: "conversationId", Value: 1}, {Key: "userId", Value: 1}}, Options: options.Index().SetName("uq_conversation_memberships_identity").SetUnique(true)},
			{Keys: bson.D{{Key: "conversationId", Value: 1}, {Key: "role", Value: 1}, {Key: "joinedAt", Value: 1}}, Options: options.Index().SetName("idx_conversation_memberships_role_joined")},
			{Keys: bson.D{{Key: "conversationId", Value: 1}, {Key: "displayName", Value: 1}, {Key: "userId", Value: 1}}, Options: options.Index().SetName("idx_conversation_memberships_display_name")},
		}},
		{s.userStates, []mongo.IndexModel{
			{Keys: bson.D{{Key: "userId", Value: 1}, {Key: "conversationId", Value: 1}}, Options: options.Index().SetName("uq_conversation_user_states_identity").SetUnique(true)},
			{Keys: bson.D{{Key: "userId", Value: 1}, {Key: "pinned", Value: -1}, {Key: "updatedAt", Value: -1}}, Options: options.Index().SetName("idx_conversation_user_states_inbox")},
		}},
		{s.messageReceipts, []mongo.IndexModel{
			{Keys: bson.D{{Key: "messageId", Value: 1}, {Key: "userId", Value: 1}}, Options: options.Index().SetName("uq_message_receipts_identity").SetUnique(true)},
			{Keys: bson.D{{Key: "conversationId", Value: 1}, {Key: "messageId", Value: 1}}, Options: options.Index().SetName("idx_message_receipts_conversation_message")},
		}},
		{s.messageCommandReceipts, []mongo.IndexModel{
			{Keys: bson.D{{Key: "messageId", Value: 1}, {Key: "createdAt", Value: -1}}, Options: options.Index().SetName("idx_message_command_receipts_message")},
		}},
		{s.messageOutbox, []mongo.IndexModel{
			{Keys: bson.D{{Key: "outboxSequence", Value: 1}}, Options: options.Index().SetName("uq_messages_outbox_sequence").SetUnique(true)},
			{Keys: bson.D{{Key: "aggregateId", Value: 1}, {Key: "aggregateVersion", Value: 1}, {Key: "eventType", Value: 1}}, Options: options.Index().SetName("uq_messages_outbox_event").SetUnique(true)},
			{Keys: bson.D{{Key: "status", Value: 1}, {Key: "createdAt", Value: 1}}, Options: options.Index().SetName("idx_messages_outbox_pending")},
		}},
	}
	for _, set := range indexSets {
		if _, err := set.collection.Indexes().CreateMany(ctx, set.models); err != nil {
			return fmt.Errorf("ensure %s indexes: %w", set.collection.Name(), err)
		}
	}
	return nil
}

func (s *MongoChatStore) RunInTransaction(ctx context.Context, fn func(context.Context) error) error {
	if mongo.SessionFromContext(ctx) != nil {
		return fn(ctx)
	}
	session, err := s.db.Client().StartSession()
	if err != nil {
		return err
	}
	defer session.EndSession(ctx)
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		return nil, fn(txCtx)
	})
	return err
}

// ── Conversation ─────────────────────────────────────────────────────────────

func (s *MongoChatStore) CreateConversation(ctx context.Context, conv *model.Conversation) error {
	_, err := s.conversations.InsertOne(ctx, conv)
	return err
}

func (s *MongoChatStore) FindConversationByID(ctx context.Context, id string) (*model.Conversation, error) {
	var conv model.Conversation
	err := s.conversations.FindOne(ctx, bson.M{"_id": id}).Decode(&conv)
	if err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return nil, fmt.Errorf("%w: %s", model.ErrConversationNotFound, id)
		}
		return nil, fmt.Errorf("find conversation %s: %w", id, err)
	}
	return &conv, nil
}

func (s *MongoChatStore) UpdateConversation(ctx context.Context, id string, conv *model.Conversation) error {
	conv.UpdatedAt = time.Now()
	_, err := s.conversations.ReplaceOne(ctx, bson.M{"_id": id}, conv)
	return err
}

func (s *MongoChatStore) ListConversationsByUser(ctx context.Context, userId string, limit int, cursor string) ([]model.Conversation, error) {
	if limit <= 0 {
		limit = 20
	}

	states, err := s.ListUserStates(ctx, userId, limit, cursor)
	if err != nil {
		return nil, err
	}

	convIds := make([]string, 0, len(states))
	for _, st := range states {
		convIds = append(convIds, st.ConversationId)
	}
	if len(convIds) == 0 {
		return nil, nil
	}

	cur, err := s.conversations.Find(ctx, bson.M{"_id": bson.M{"$in": convIds}})
	if err != nil {
		return nil, err
	}
	defer cur.Close(ctx)

	var convs []model.Conversation
	if err := cur.All(ctx, &convs); err != nil {
		return nil, err
	}

	convMap := make(map[string]model.Conversation, len(convs))
	for _, c := range convs {
		convMap[c.ID] = c
	}

	result := make([]model.Conversation, 0, len(convIds))
	for _, id := range convIds {
		if c, ok := convMap[id]; ok {
			if c.Status != "active" {
				continue
			}
			result = append(result, c)
		}
	}
	return result, nil
}

func (s *MongoChatStore) ListGroupConversationsNeedingAvatar(ctx context.Context, limit int) ([]model.Conversation, error) {
	if limit <= 0 {
		limit = 200
	}
	filter := bson.M{
		"status": bson.M{"$in": bson.A{"", "active"}},
		"type":   "group",
		"$or": bson.A{
			bson.M{"avatarUrl": bson.M{"$exists": false}},
			bson.M{"avatarUrl": ""},
			bson.M{"groupAvatarAssetId": ""},
			bson.M{"groupAvatarVersion": bson.M{"$lte": 0}},
		},
	}
	cur, err := s.conversations.Find(ctx, filter, options.Find().SetLimit(int64(limit)))
	if err != nil {
		return nil, err
	}
	defer cur.Close(ctx)
	var convs []model.Conversation
	if err := cur.All(ctx, &convs); err != nil {
		return nil, err
	}
	return convs, nil
}

// ── Message ──────────────────────────────────────────────────────────────────

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

func bindMessageOutboxEvents(
	message messagemodel.Message,
	events []application.MessageOutboxEvent,
) []application.MessageOutboxEvent {
	bound := make([]application.MessageOutboxEvent, 0, len(events))
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
) ([]application.MessageOutboxEvent, error) {
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

	events := make([]application.MessageOutboxEvent, 0, limit)
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

func messageOutboxEventFromDocument(document messageOutboxDocument) application.MessageOutboxEvent {
	return application.MessageOutboxEvent{
		EventID:        document.ID,
		EventType:      document.EventType,
		ConversationID: document.ConversationID,
		ActorID:        document.ActorID,
		Payload:        document.Payload,
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
	events := make([]application.MessageOutboxEvent, 0)
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

	opts := options.Find().
		SetSort(bson.D{{Key: "seq", Value: -1}}).
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

func (s *MongoChatStore) CreateMember(ctx context.Context, member *model.ConversationMember) error {
	_, err := s.members.InsertOne(ctx, member)
	return err
}

func (s *MongoChatStore) DeleteMember(ctx context.Context, conversationId, userId string) error {
	_, err := s.members.DeleteOne(ctx, bson.M{
		"conversationId": conversationId,
		"userId":         userId,
	})
	return err
}

func (s *MongoChatStore) FindMember(ctx context.Context, conversationId, userId string) (*model.ConversationMember, error) {
	var member model.ConversationMember
	err := s.members.FindOne(ctx, bson.M{
		"conversationId": conversationId,
		"userId":         userId,
	}).Decode(&member)
	if err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return nil, fmt.Errorf("%w: conversation=%s persona=%s", model.ErrMemberNotFound, conversationId, userId)
		}
		return nil, err
	}
	return &member, nil
}

func (s *MongoChatStore) UpdateMemberAvatarSnapshot(
	ctx context.Context,
	conversationId string,
	userId string,
	avatarURL string,
	avatarAssetID string,
	avatarVersion int64,
) error {
	_, err := s.members.UpdateOne(ctx, bson.M{
		"conversationId": conversationId,
		"userId":         userId,
	}, bson.M{
		"$set": bson.M{
			"avatarUrl":     avatarURL,
			"avatarAssetId": avatarAssetID,
			"avatarVersion": avatarVersion,
		},
	})
	return err
}

func (s *MongoChatStore) UpdateMemberRole(ctx context.Context, conversationId, userId, role string) error {
	_, err := s.members.UpdateOne(ctx, bson.M{
		"conversationId": conversationId,
		"userId":         userId,
	}, bson.M{
		"$set": bson.M{
			"role": role,
		},
	})
	return err
}

func (s *MongoChatStore) ListMembers(
	ctx context.Context,
	conversationId string,
	query application.ListMembersQuery,
) ([]model.ConversationMember, error) {
	if query.Limit <= 0 {
		query.Limit = 20
	}

	sortMode := application.NormalizeMemberListSort(string(query.Sort))
	base := bson.M{"conversationId": conversationId}
	if query.Role != "" {
		base["role"] = query.Role
	}

	var cursorFilter bson.M
	var err error
	switch sortMode {
	case application.MemberListSortDisplayNameAsc:
		cursorFilter, err = memberListCursorFilterDisplayName(query.Cursor)
	default:
		cursorFilter, err = memberListCursorFilterJoined(query.Cursor)
	}
	if err != nil {
		return nil, err
	}

	var filter bson.M
	if cursorFilter != nil {
		filter = bson.M{"$and": []bson.M{base, cursorFilter}}
	} else {
		filter = base
	}

	var sortDoc bson.D
	switch sortMode {
	case application.MemberListSortDisplayNameAsc:
		sortDoc = bson.D{
			{Key: "displayName", Value: 1},
			{Key: "userId", Value: 1},
		}
	default:
		sortDoc = bson.D{
			{Key: "joinedAt", Value: 1},
			{Key: "_id", Value: 1},
		}
	}

	opts := options.Find().
		SetSort(sortDoc).
		SetLimit(int64(query.Limit))

	cur, err := s.members.Find(ctx, filter, opts)
	if err != nil {
		return nil, err
	}
	defer cur.Close(ctx)

	var members []model.ConversationMember
	if err := cur.All(ctx, &members); err != nil {
		return nil, err
	}
	return members, nil
}

// BumpMembersRosterRevision increments membersRosterRevision and sets updatedAt.
// When memberCount is non-nil, memberCount is set on the conversation document.
func (s *MongoChatStore) BumpMembersRosterRevision(ctx context.Context, conversationId string, memberCount *int) error {
	now := time.Now()
	setDoc := bson.M{"updatedAt": now}
	if memberCount != nil {
		setDoc["memberCount"] = *memberCount
	}
	_, err := s.conversations.UpdateOne(ctx, bson.M{"_id": conversationId}, bson.M{
		"$inc": bson.M{"membersRosterRevision": 1},
		"$set": setDoc,
	})
	return err
}

func (s *MongoChatStore) CountMembers(ctx context.Context, conversationId string) (int, error) {
	count, err := s.members.CountDocuments(ctx, bson.M{"conversationId": conversationId})
	if err != nil {
		return 0, err
	}
	return int(count), nil
}

func (s *MongoChatStore) FindAssistantMember(ctx context.Context, conversationId string) (*model.ConversationMember, error) {
	var member model.ConversationMember
	err := s.members.FindOne(ctx, bson.M{
		"conversationId": conversationId,
		"memberType":     "assistant",
	}).Decode(&member)
	if err != nil {
		return nil, err
	}
	return &member, nil
}

// ── User State ───────────────────────────────────────────────────────────────

func (s *MongoChatStore) UpsertUserState(ctx context.Context, state *model.ConversationUserState) error {
	filter := bson.M{
		"userId":         state.UserId,
		"conversationId": state.ConversationId,
	}
	state.UpdatedAt = time.Now()
	opts := options.Replace().SetUpsert(true)
	_, err := s.userStates.ReplaceOne(ctx, filter, state, opts)
	return err
}

func (s *MongoChatStore) FindUserState(ctx context.Context, userId, conversationId string) (*model.ConversationUserState, error) {
	var state model.ConversationUserState
	err := s.userStates.FindOne(ctx, bson.M{
		"userId":         userId,
		"conversationId": conversationId,
	}).Decode(&state)
	if err != nil {
		return nil, err
	}
	return &state, nil
}

func (s *MongoChatStore) ListUserStates(ctx context.Context, userId string, limit int, cursor string) ([]model.ConversationUserState, error) {
	if limit <= 0 {
		limit = 20
	}

	filter := bson.M{"userId": userId}
	if cursor != "" {
		filter["conversationId"] = bson.M{"$gt": cursor}
	}

	opts := options.Find().
		SetSort(bson.D{
			{Key: "pinned", Value: -1},
			{Key: "updatedAt", Value: -1},
		}).
		SetLimit(int64(limit))

	cur, err := s.userStates.Find(ctx, filter, opts)
	if err != nil {
		return nil, err
	}
	defer cur.Close(ctx)

	var states []model.ConversationUserState
	if err := cur.All(ctx, &states); err != nil {
		return nil, err
	}
	return states, nil
}

func (s *MongoChatStore) FindDirectConversationBetween(ctx context.Context, memberA, memberB string) (*model.Conversation, error) {
	if strings.TrimSpace(memberA) == "" || strings.TrimSpace(memberB) == "" {
		return nil, fmt.Errorf("conversation members required")
	}
	pipeline := mongo.Pipeline{
		{{Key: "$match", Value: bson.M{
			"userId":     bson.M{"$in": []string{memberA, memberB}},
			"memberType": "user",
		}}},
		{{Key: "$group", Value: bson.M{
			"_id":       "$conversationId",
			"memberIds": bson.M{"$addToSet": "$userId"},
			"count":     bson.M{"$sum": 1},
		}}},
		{{Key: "$match", Value: bson.M{
			"count": 2,
			"memberIds": bson.M{
				"$all": []string{memberA, memberB},
			},
		}}},
		{{Key: "$limit", Value: 1}},
	}
	cur, err := s.members.Aggregate(ctx, pipeline)
	if err != nil {
		return nil, err
	}
	defer cur.Close(ctx)
	var rows []struct {
		ID string `bson:"_id"`
	}
	if err := cur.All(ctx, &rows); err != nil {
		return nil, err
	}
	if len(rows) == 0 {
		return nil, nil
	}
	conv, err := s.FindConversationByID(ctx, rows[0].ID)
	if err != nil {
		return nil, err
	}
	if conv.Type != "direct" && conv.Type != "encrypted" {
		return nil, nil
	}
	if conv.Status != "" && conv.Status != "active" {
		return nil, nil
	}
	return conv, nil
}

// ── Receipts ─────────────────────────────────────────────────────────────────

func (s *MongoChatStore) CreateReceipt(ctx context.Context, receipt *messagemodel.MessageReceipt) error {
	_, err := s.messageReceipts.InsertOne(ctx, receipt)
	return err
}

func (s *MongoChatStore) ListReceiptsByMessage(ctx context.Context, messageId string) ([]messagemodel.MessageReceipt, error) {
	cur, err := s.messageReceipts.Find(ctx, bson.M{"messageId": messageId})
	if err != nil {
		return nil, err
	}
	defer cur.Close(ctx)

	var receipts []messagemodel.MessageReceipt
	if err := cur.All(ctx, &receipts); err != nil {
		return nil, err
	}
	return receipts, nil
}
