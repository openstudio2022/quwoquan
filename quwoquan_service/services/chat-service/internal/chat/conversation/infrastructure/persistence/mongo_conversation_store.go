package persistence

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/chat-service/internal/chat/conversation/application"
	model "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
	messageports "quwoquan_service/services/chat-service/internal/chat/message/domain/ports"
)

// MongoChatStore 以 MongoDB 实现应用层的细粒度存储端口。
type MongoChatStore struct {
	db                            *mongo.Database
	conversations                 *mongo.Collection
	messages                      *mongo.Collection
	circleGroupProjections        *mongo.Collection
	circleGroupBindingProjections *mongo.Collection
	messageCommandReceipts        *mongo.Collection
	messageSequences              *mongo.Collection
	messageOutbox                 *mongo.Collection
	messageOutboxSequences        *mongo.Collection
	messageCheckpoints            *mongo.Collection
}

var (
	_ application.TransactionRunner                     = (*MongoChatStore)(nil)
	_ application.ConversationStore                     = (*MongoChatStore)(nil)
	_ application.CircleGroupConversationReader         = (*MongoChatStore)(nil)
	_ application.GatheringConversationReader           = (*MongoChatStore)(nil)
	_ application.CircleGroupMembershipProjectionStore  = (*MongoChatStore)(nil)
	_ application.CircleGroupChatBindingProjectionStore = (*MongoChatStore)(nil)
	_ application.MessageStore                          = (*MongoChatStore)(nil)
	_ messageports.OutboxReader                         = (*MongoChatStore)(nil)
	_ messageports.OutboxDispatchStore                  = (*MongoChatStore)(nil)
	_ messageports.OutboxCheckpointStore                = (*MongoChatStore)(nil)
	_ application.ConversationMessageProjector          = (*MongoChatStore)(nil)
)

func NewMongoChatStore(db *mongo.Database) *MongoChatStore {
	return &MongoChatStore{
		db:                            db,
		conversations:                 db.Collection("conversations"),
		messages:                      db.Collection("messages"),
		circleGroupProjections:        db.Collection("circle_group_membership_projection_states"),
		circleGroupBindingProjections: db.Collection("circle_group_chat_binding_projection_states"),
		messageCommandReceipts:        db.Collection("messages_command_receipts"),
		messageSequences:              db.Collection("messages_sequences"),
		messageOutbox:                 db.Collection("messages_outbox"),
		messageOutboxSequences:        db.Collection("messages_outbox_sequences"),
		messageCheckpoints:            db.Collection("messages_projection_checkpoints"),
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
			{Keys: bson.D{{Key: "circleGroupId", Value: 1}}, Options: options.Index().SetName("uq_conv_circle_group").SetSparse(true).SetUnique(true)},
			{Keys: bson.D{{Key: "gatheringId", Value: 1}}, Options: options.Index().SetName("uq_conv_gathering").SetSparse(true).SetUnique(true)},
			{Keys: bson.D{{Key: "status", Value: 1}}, Options: options.Index().SetName("idx_conv_status")},
			{Keys: bson.D{{Key: "lastMessageTime", Value: -1}}, Options: options.Index().SetName("idx_conv_last_msg_time")},
			{Keys: bson.D{{Key: "originRequestId", Value: 1}}, Options: options.Index().SetName("uq_conv_origin_request").SetUnique(true).SetSparse(true)},
		}},
		{s.messages, []mongo.IndexModel{
			{Keys: bson.D{{Key: "conversationId", Value: 1}, {Key: "seq", Value: 1}}, Options: options.Index().SetName("uq_messages_conversation_seq").SetUnique(true)},
			{Keys: bson.D{{Key: "conversationId", Value: 1}, {Key: "senderId", Value: 1}, {Key: "clientMsgId", Value: 1}}, Options: options.Index().SetName("uq_messages_client_message").SetUnique(true)},
			{Keys: bson.D{{Key: "conversationId", Value: 1}, {Key: "timestamp", Value: -1}}, Options: options.Index().SetName("idx_messages_conversation_time")},
			{Keys: bson.D{{Key: "conversationId", Value: 1}, {Key: "mentions", Value: 1}, {Key: "seq", Value: 1}}, Options: options.Index().SetName("idx_messages_conversation_mentions_seq")},
			{Keys: bson.D{{Key: "replyToMessageId", Value: 1}}, Options: options.Index().SetName("idx_messages_reply").SetSparse(true)},
		}},
		{s.circleGroupProjections, []mongo.IndexModel{
			{Keys: bson.D{{Key: "circleGroupId", Value: 1}, {Key: "userId", Value: 1}}, Options: options.Index().SetName("uq_circle_group_membership_projection_identity").SetUnique(true)},
			{Keys: bson.D{{Key: "conversationId", Value: 1}, {Key: "sourceVersion", Value: -1}}, Options: options.Index().SetName("idx_circle_group_membership_projection_conversation")},
		}},
		{s.circleGroupBindingProjections, []mongo.IndexModel{
			{Keys: bson.D{{Key: "circleGroupId", Value: 1}}, Options: options.Index().SetName("uq_circle_group_chat_binding_projection_group").SetUnique(true)},
			{Keys: bson.D{{Key: "status", Value: 1}, {Key: "sourceVersion", Value: -1}}, Options: options.Index().SetName("idx_circle_group_chat_binding_projection_status")},
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
	if mongo.IsDuplicateKeyError(err) && strings.TrimSpace(conv.CircleGroupId) != "" {
		return fmt.Errorf(
			"%w: circleGroupId=%s",
			model.ErrCircleGroupConversationAlreadyBound,
			conv.CircleGroupId,
		)
	}
	if mongo.IsDuplicateKeyError(err) && strings.TrimSpace(conv.GatheringId) != "" {
		return fmt.Errorf(
			"%w: gatheringId=%s",
			model.ErrGatheringConversationAlreadyBound,
			conv.GatheringId,
		)
	}
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

func (s *MongoChatStore) FindConversationsByIDs(
	ctx context.Context,
	ids []string,
) ([]model.Conversation, error) {
	if len(ids) == 0 {
		return []model.Conversation{}, nil
	}
	cur, err := s.conversations.Find(ctx, bson.M{
		"_id": bson.M{"$in": ids},
	})
	if err != nil {
		return nil, err
	}
	defer cur.Close(ctx)

	var conversations []model.Conversation
	if err := cur.All(ctx, &conversations); err != nil {
		return nil, err
	}
	return conversations, nil
}

func (s *MongoChatStore) FindConversationByCircleGroupID(
	ctx context.Context,
	circleGroupID string,
) (*model.Conversation, error) {
	circleGroupID = strings.TrimSpace(circleGroupID)
	if circleGroupID == "" {
		return nil, fmt.Errorf("%w: blank circle group", model.ErrConversationNotFound)
	}
	var conv model.Conversation
	err := s.conversations.FindOne(ctx, bson.M{"circleGroupId": circleGroupID}).Decode(&conv)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return nil, fmt.Errorf("%w: circleGroupId=%s", model.ErrConversationNotFound, circleGroupID)
	}
	if err != nil {
		return nil, fmt.Errorf("find conversation for circle group %s: %w", circleGroupID, err)
	}
	return &conv, nil
}

func (s *MongoChatStore) FindConversationByGatheringID(
	ctx context.Context,
	gatheringID string,
) (*model.Conversation, error) {
	gatheringID = strings.TrimSpace(gatheringID)
	if gatheringID == "" {
		return nil, fmt.Errorf("%w: blank Gathering", model.ErrConversationNotFound)
	}
	var conversation model.Conversation
	err := s.conversations.FindOne(ctx, bson.M{"gatheringId": gatheringID}).Decode(&conversation)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return nil, fmt.Errorf("%w: gatheringId=%s", model.ErrConversationNotFound, gatheringID)
	}
	if err != nil {
		return nil, fmt.Errorf("find conversation for Gathering %s: %w", gatheringID, err)
	}
	return &conversation, nil
}

func (s *MongoChatStore) ApplyGatheringConversationProjection(
	ctx context.Context,
	gatheringID string,
	expectedSourceVersion int64,
	conversation *model.Conversation,
) (bool, error) {
	if conversation == nil {
		return false, errors.New("Gathering conversation projection is required")
	}
	versionFilter := bson.M{"gatheringSourceVersion": expectedSourceVersion}
	if expectedSourceVersion == 0 {
		versionFilter = bson.M{"$or": bson.A{
			bson.M{"gatheringSourceVersion": 0},
			bson.M{"gatheringSourceVersion": bson.M{"$exists": false}},
		}}
	}
	filter := bson.M{
		"$and": bson.A{
			bson.M{"gatheringId": strings.TrimSpace(gatheringID)},
			versionFilter,
		},
	}
	conversation.UpdatedAt = time.Now().UTC()
	result, err := s.conversations.ReplaceOne(ctx, filter, conversation)
	if err != nil {
		return false, err
	}
	return result.MatchedCount == 1, nil
}

func (s *MongoChatStore) UpdateConversation(ctx context.Context, id string, conv *model.Conversation) error {
	conv.UpdatedAt = time.Now()
	_, err := s.conversations.ReplaceOne(ctx, bson.M{"_id": id}, conv)
	return err
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

// ── Receipts ─────────────────────────────────────────────────────────────────
