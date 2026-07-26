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

	"quwoquan_service/services/chat-service/internal/chat/conversation/application"
	model "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
	messagemodel "quwoquan_service/services/chat-service/internal/chat/message/domain/model"
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

// DeleteUserState removes the per-user inbox source after a member leaves or is
// removed. DeleteOne intentionally treats an already-absent state as a
// successful idempotent no-op.
func (s *MongoChatStore) DeleteUserState(
	ctx context.Context,
	userID string,
	conversationID string,
) error {
	_, err := s.userStates.DeleteOne(ctx, bson.M{
		"userId":         userID,
		"conversationId": conversationID,
	})
	return err
}

// AdvanceInboxUnread 由 inbox projector 消费 MessageSent 事件调用。
// inboxProjectedSeq 和 readSeq 同时参与原子过滤：重放不重复递增，
// 已读水位之前的迟到事件只推进投影水位。已离开会话而被删除的 user state
// 表示该用户不再拥有 ChatInbox 行，迟到事件必须 no-op，不能重建状态或阻塞投影。
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
			return nil
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

func (s *MongoChatStore) ListUserStatePage(
	ctx context.Context,
	userId string,
	limit int,
	cursor string,
) (model.ConversationUserStatePage, error) {
	if limit <= 0 {
		limit = 20
	}

	filter := bson.M{"userId": userId}
	if cursor != "" {
		after, err := model.DecodeInboxCursor(cursor)
		if err != nil {
			return model.ConversationUserStatePage{}, err
		}

		afterPinned := bson.M{
			"pinned":    after.Pinned,
			"updatedAt": bson.M{"$lt": after.UpdatedAt},
		}
		afterSameTimestamp := bson.M{
			"pinned":         after.Pinned,
			"updatedAt":      after.UpdatedAt,
			"conversationId": bson.M{"$gt": after.ConversationId},
		}
		pageFilter := bson.A{afterPinned, afterSameTimestamp}
		if after.Pinned {
			pageFilter = append(bson.A{bson.M{"pinned": false}}, pageFilter...)
		}
		filter["$or"] = pageFilter
	}

	opts := options.Find().
		SetSort(bson.D{
			{Key: "pinned", Value: -1},
			{Key: "updatedAt", Value: -1},
			{Key: "conversationId", Value: 1},
		}).
		SetLimit(int64(limit + 1))

	cur, err := s.userStates.Find(ctx, filter, opts)
	if err != nil {
		return model.ConversationUserStatePage{}, err
	}
	defer cur.Close(ctx)

	var states []model.ConversationUserState
	if err := cur.All(ctx, &states); err != nil {
		return model.ConversationUserStatePage{}, err
	}
	page := model.ConversationUserStatePage{Items: states}
	if len(states) > limit {
		page.Items = states[:limit]
		page.NextCursor = model.EncodeInboxCursor(page.Items[len(page.Items)-1])
	}
	return page, nil
}

func (s *MongoChatStore) ListUserStates(
	ctx context.Context,
	userId string,
	limit int,
	cursor string,
) ([]model.ConversationUserState, error) {
	page, err := s.ListUserStatePage(ctx, userId, limit, cursor)
	if err != nil {
		return nil, err
	}
	return page.Items, nil
}

func (s *MongoChatStore) ListUserStatesByConversationID(
	ctx context.Context,
	userID string,
	limit int,
	afterConversationID string,
) ([]model.ConversationUserState, error) {
	if limit <= 0 {
		limit = 20
	}
	filter := bson.M{"userId": userID}
	if afterConversationID != "" {
		filter["conversationId"] = bson.M{"$gt": afterConversationID}
	}
	cur, err := s.userStates.Find(
		ctx,
		filter,
		options.Find().
			SetSort(bson.D{{Key: "conversationId", Value: 1}}).
			SetLimit(int64(limit)),
	)
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

func (s *MongoChatStore) LoadCircleGroupMembershipProjection(
	ctx context.Context,
	circleGroupID string,
	userID string,
) (application.CircleGroupMembershipProjectionState, bool, error) {
	var document circleGroupMembershipProjectionDocument
	err := s.circleGroupProjections.FindOne(ctx, bson.M{
		"circleGroupId": circleGroupID,
		"userId":        userID,
	}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return application.CircleGroupMembershipProjectionState{}, false, nil
	}
	if err != nil {
		return application.CircleGroupMembershipProjectionState{}, false, err
	}
	return document.toApplication(), true, nil
}

func (s *MongoChatStore) SaveCircleGroupMembershipProjection(
	ctx context.Context,
	state application.CircleGroupMembershipProjectionState,
) error {
	document := circleGroupMembershipProjectionDocument{
		CircleGroupID:  state.CircleGroupID,
		ConversationID: state.ConversationID,
		UserID:         state.UserID,
		SourceVersion:  state.SourceVersion,
		State:          state.State,
		Role:           state.Role,
		LastEventID:    state.LastEventID,
		UpdatedAt:      state.UpdatedAt.UTC(),
	}
	_, err := s.circleGroupProjections.ReplaceOne(
		ctx,
		bson.M{"circleGroupId": document.CircleGroupID, "userId": document.UserID},
		document,
		options.Replace().SetUpsert(true),
	)
	return err
}

type circleGroupMembershipProjectionDocument struct {
	CircleGroupID  string    `bson:"circleGroupId"`
	ConversationID string    `bson:"conversationId"`
	UserID         string    `bson:"userId"`
	SourceVersion  int64     `bson:"sourceVersion"`
	State          string    `bson:"state"`
	Role           string    `bson:"role"`
	LastEventID    string    `bson:"lastEventId"`
	UpdatedAt      time.Time `bson:"updatedAt"`
}

func (document circleGroupMembershipProjectionDocument) toApplication() application.CircleGroupMembershipProjectionState {
	return application.CircleGroupMembershipProjectionState{
		CircleGroupID:  document.CircleGroupID,
		ConversationID: document.ConversationID,
		UserID:         document.UserID,
		SourceVersion:  document.SourceVersion,
		State:          document.State,
		Role:           document.Role,
		LastEventID:    document.LastEventID,
		UpdatedAt:      document.UpdatedAt.UTC(),
	}
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
