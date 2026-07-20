// ConversationUserState 与 MessageReceiptFact 端口实现（MongoChatStore 分文件）。
package persistence

import (
	"context"
	"errors"
	"fmt"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	messagemodel "quwoquan_service/services/chat-service/internal/domain/chat/message/model"
	model "quwoquan_service/services/chat-service/internal/domain/conversation/model"
)

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

// AdvanceInboxUnread 由 inbox projector 消费 MessageSent 事件调用。
// inboxProjectedSeq 和 readSeq 同时参与原子过滤：重放不重复递增，
// 已读水位之前的迟到事件只推进投影水位。
func (s *MongoChatStore) AdvanceInboxUnread(
	ctx context.Context,
	userId string,
	conversationId string,
	eventSeq int64,
	unreadDelta int,
	mentionDelta int,
	lastMessageAt time.Time,
) error {
	if eventSeq <= 0 {
		return errors.New("inbox projection event seq must be positive")
	}
	identity := bson.M{"userId": userId, "conversationId": conversationId}
	projectionBehind := bson.M{"$or": bson.A{
		bson.M{"inboxProjectedSeq": bson.M{"$lt": eventSeq}},
		bson.M{"inboxProjectedSeq": bson.M{"$exists": false}},
	}}
	readBehind := bson.M{"$or": bson.A{
		bson.M{"readSeq": bson.M{"$lt": eventSeq}},
		bson.M{"readSeq": bson.M{"$exists": false}},
	}}
	incrementResult, err := s.userStates.UpdateOne(
		ctx,
		bson.M{"$and": bson.A{identity, projectionBehind, readBehind}},
		bson.M{
			"$inc": bson.M{
				"unreadCount":        unreadDelta,
				"mentionUnreadCount": mentionDelta,
			},
			"$max": bson.M{
				"inboxProjectedSeq": eventSeq,
				"updatedAt":         lastMessageAt.UTC(),
			},
		},
	)
	if err != nil {
		return err
	}
	if incrementResult.MatchedCount > 0 {
		return nil
	}

	watermarkResult, err := s.userStates.UpdateOne(
		ctx,
		bson.M{"$and": bson.A{identity, projectionBehind}},
		bson.M{"$max": bson.M{
			"inboxProjectedSeq": eventSeq,
			"updatedAt":         lastMessageAt.UTC(),
		}},
	)
	if err != nil {
		return err
	}
	if watermarkResult.MatchedCount > 0 {
		return nil
	}

	if err := s.userStates.FindOne(ctx, identity).Err(); err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return fmt.Errorf(
				"conversation user state missing for inbox projection user=%s conversation=%s",
				userId,
				conversationId,
			)
		}
		return err
	}
	return nil
}

func (s *MongoChatStore) FindUserState(ctx context.Context, userId, conversationId string) (*model.ConversationUserState, error) {
	var state model.ConversationUserState
	err := s.userStates.FindOne(ctx, bson.M{
		"userId":         userId,
		"conversationId": conversationId,
	}).Decode(&state)
	if err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return nil, fmt.Errorf(
				"%w: user=%s conversation=%s",
				model.ErrUserStateNotFound,
				userId,
				conversationId,
			)
		}
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

func (s *MongoChatStore) CreateReceipt(ctx context.Context, receipt *messagemodel.MessageReceipt) error {
	_, err := s.messageReceipts.InsertOne(ctx, receipt)
	if mongo.IsDuplicateKeyError(err) {
		return fmt.Errorf("%w: message=%s user=%s", messagemodel.ErrMessageReceiptAlreadyExists, receipt.MessageID, receipt.UserID)
	}
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
