package persistence

import (
	"context"
	"fmt"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	model "quwoquan_service/services/chat-service/internal/domain/conversation/model"
)

// MongoChatStore implements ChatRepository backed by MongoDB.
type MongoChatStore struct {
	conversations *mongo.Collection
	messages      *mongo.Collection
	members       *mongo.Collection
	userStates    *mongo.Collection
	receipts      *mongo.Collection
}

func NewMongoChatStore(db *mongo.Database) *MongoChatStore {
	return &MongoChatStore{
		conversations: db.Collection("conversations"),
		messages:      db.Collection("messages"),
		members:       db.Collection("conversation_members"),
		userStates:    db.Collection("conversation_user_states"),
		receipts:      db.Collection("message_receipts"),
	}
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
		return nil, fmt.Errorf("conversation not found: %w", err)
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
			result = append(result, c)
		}
	}
	return result, nil
}

// ── Message ──────────────────────────────────────────────────────────────────

func (s *MongoChatStore) CreateMessage(ctx context.Context, msg *model.Message) error {
	_, err := s.messages.InsertOne(ctx, msg)
	return err
}

func (s *MongoChatStore) FindMessageByID(ctx context.Context, id string) (*model.Message, error) {
	var msg model.Message
	err := s.messages.FindOne(ctx, bson.M{"_id": id}).Decode(&msg)
	if err != nil {
		return nil, fmt.Errorf("message not found: %w", err)
	}
	return &msg, nil
}

func (s *MongoChatStore) FindMessageByClientMsgId(ctx context.Context, conversationId, clientMsgId string) (*model.Message, error) {
	var msg model.Message
	err := s.messages.FindOne(ctx, bson.M{
		"conversationId": conversationId,
		"clientMsgId":    clientMsgId,
	}).Decode(&msg)
	if err != nil {
		return nil, err
	}
	return &msg, nil
}

func (s *MongoChatStore) ListMessages(ctx context.Context, conversationId string, limit int, afterSeq, beforeSeq int64) ([]model.Message, error) {
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

	var msgs []model.Message
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
		return nil, err
	}
	return &member, nil
}

func (s *MongoChatStore) ListMembers(ctx context.Context, conversationId string, limit int, cursor, role string) ([]model.ConversationMember, error) {
	if limit <= 0 {
		limit = 20
	}

	filter := bson.M{"conversationId": conversationId}
	if role != "" {
		filter["role"] = role
	}
	if cursor != "" {
		filter["_id"] = bson.M{"$gt": cursor}
	}

	opts := options.Find().
		SetSort(bson.D{{Key: "joinedAt", Value: -1}}).
		SetLimit(int64(limit))

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

// ── Receipts ─────────────────────────────────────────────────────────────────

func (s *MongoChatStore) CreateReceipt(ctx context.Context, receipt *model.MessageReceipt) error {
	_, err := s.receipts.InsertOne(ctx, receipt)
	return err
}

func (s *MongoChatStore) ListReceiptsByMessage(ctx context.Context, messageId string) ([]model.MessageReceipt, error) {
	cur, err := s.receipts.Find(ctx, bson.M{"messageId": messageId})
	if err != nil {
		return nil, err
	}
	defer cur.Close(ctx)

	var receipts []model.MessageReceipt
	if err := cur.All(ctx, &receipts); err != nil {
		return nil, err
	}
	return receipts, nil
}
