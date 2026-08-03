package persistence

import (
	"context"
	"errors"
	"fmt"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	userstatemodel "quwoquan_service/services/chat-service/internal/chat/conversation_user_state/domain/model"
)

type MongoStore struct {
	states *mongo.Collection
}

func NewMongoStore(database *mongo.Database) *MongoStore {
	if database == nil {
		panic("conversation user-state database is required")
	}
	return &MongoStore{states: database.Collection("conversation_user_states")}
}

func (store *MongoStore) EnsureIndexes(ctx context.Context) error {
	_, err := store.states.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "userId", Value: 1}, {Key: "conversationId", Value: 1}}, Options: options.Index().SetName("uq_conversation_user_states_identity").SetUnique(true)},
		{Keys: bson.D{{Key: "userId", Value: 1}, {Key: "pinned", Value: -1}, {Key: "updatedAt", Value: -1}}, Options: options.Index().SetName("idx_conversation_user_states_inbox")},
	})
	if err != nil {
		return fmt.Errorf("ensure ConversationUserState indexes: %w", err)
	}
	return nil
}

func (store *MongoStore) UpsertUserState(ctx context.Context, state *userstatemodel.State) error {
	if state == nil {
		return errors.New("conversation user state is required")
	}
	if err := state.ValidateIdentity(); err != nil {
		return err
	}
	filter := bson.M{"userId": state.UserId, "conversationId": state.ConversationId}
	state.UpdatedAt = time.Now().UTC()
	_, err := store.states.ReplaceOne(ctx, filter, state, options.Replace().SetUpsert(true))
	return err
}

func (store *MongoStore) DeleteUserState(ctx context.Context, userID, conversationID string) error {
	_, err := store.states.DeleteOne(ctx, bson.M{"userId": userID, "conversationId": conversationID})
	return err
}

func (store *MongoStore) AdvanceInboxUnread(
	ctx context.Context,
	userID string,
	conversationID string,
	eventSeq int64,
	unreadDelta int,
	mentionDelta int,
	lastMessageAt time.Time,
) error {
	if eventSeq <= 0 {
		return errors.New("inbox projection event seq must be positive")
	}
	identity := bson.M{"userId": userID, "conversationId": conversationID}
	projectionBehind := bson.M{"$or": bson.A{
		bson.M{"inboxProjectedSeq": bson.M{"$lt": eventSeq}},
		bson.M{"inboxProjectedSeq": bson.M{"$exists": false}},
	}}
	readBehind := bson.M{"$or": bson.A{
		bson.M{"readSeq": bson.M{"$lt": eventSeq}},
		bson.M{"readSeq": bson.M{"$exists": false}},
	}}
	incrementResult, err := store.states.UpdateOne(
		ctx,
		bson.M{"$and": bson.A{identity, projectionBehind, readBehind}},
		bson.M{
			"$inc": bson.M{"unreadCount": unreadDelta, "mentionUnreadCount": mentionDelta},
			"$max": bson.M{"inboxProjectedSeq": eventSeq, "updatedAt": lastMessageAt.UTC()},
		},
	)
	if err != nil || incrementResult.MatchedCount > 0 {
		return err
	}
	watermarkResult, err := store.states.UpdateOne(
		ctx,
		bson.M{"$and": bson.A{identity, projectionBehind}},
		bson.M{"$max": bson.M{"inboxProjectedSeq": eventSeq, "updatedAt": lastMessageAt.UTC()}},
	)
	if err != nil || watermarkResult.MatchedCount > 0 {
		return err
	}
	if err := store.states.FindOne(ctx, identity).Err(); err != nil && !errors.Is(err, mongo.ErrNoDocuments) {
		return err
	}
	return nil
}

func (store *MongoStore) FindUserState(ctx context.Context, userID, conversationID string) (*userstatemodel.State, error) {
	var state userstatemodel.State
	err := store.states.FindOne(ctx, bson.M{"userId": userID, "conversationId": conversationID}).Decode(&state)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return nil, fmt.Errorf("%w: user=%s conversation=%s", userstatemodel.ErrNotFound, userID, conversationID)
	}
	return &state, err
}

func (store *MongoStore) ListUserStatePage(
	ctx context.Context,
	userID string,
	limit int,
	cursor string,
) (userstatemodel.Page, error) {
	if limit <= 0 {
		limit = 20
	}
	filter := bson.M{"userId": userID}
	if cursor != "" {
		after, err := userstatemodel.DecodeCursor(cursor)
		if err != nil {
			return userstatemodel.Page{}, err
		}
		afterPinned := bson.M{"pinned": after.Pinned, "updatedAt": bson.M{"$lt": after.UpdatedAt}}
		afterSameTimestamp := bson.M{
			"pinned": after.Pinned, "updatedAt": after.UpdatedAt,
			"conversationId": bson.M{"$gt": after.ConversationId},
		}
		pageFilter := bson.A{afterPinned, afterSameTimestamp}
		if after.Pinned {
			pageFilter = append(bson.A{bson.M{"pinned": false}}, pageFilter...)
		}
		filter["$or"] = pageFilter
	}
	cursorResult, err := store.states.Find(
		ctx,
		filter,
		options.Find().SetSort(bson.D{
			{Key: "pinned", Value: -1},
			{Key: "updatedAt", Value: -1},
			{Key: "conversationId", Value: 1},
		}).SetLimit(int64(limit+1)),
	)
	if err != nil {
		return userstatemodel.Page{}, err
	}
	defer cursorResult.Close(ctx)
	var states []userstatemodel.State
	if err := cursorResult.All(ctx, &states); err != nil {
		return userstatemodel.Page{}, err
	}
	page := userstatemodel.Page{Items: states}
	if len(states) > limit {
		page.Items = states[:limit]
		page.NextCursor = userstatemodel.EncodeCursor(page.Items[len(page.Items)-1])
	}
	return page, nil
}

func (store *MongoStore) ListUserStates(
	ctx context.Context,
	userID string,
	limit int,
	cursor string,
) ([]userstatemodel.State, error) {
	page, err := store.ListUserStatePage(ctx, userID, limit, cursor)
	return page.Items, err
}

func (store *MongoStore) ListUserStatesByConversationID(
	ctx context.Context,
	userID string,
	limit int,
	afterConversationID string,
) ([]userstatemodel.State, error) {
	if limit <= 0 {
		limit = 20
	}
	filter := bson.M{"userId": userID}
	if afterConversationID != "" {
		filter["conversationId"] = bson.M{"$gt": afterConversationID}
	}
	cursor, err := store.states.Find(
		ctx,
		filter,
		options.Find().SetSort(bson.D{{Key: "conversationId", Value: 1}}).SetLimit(int64(limit)),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var states []userstatemodel.State
	if err := cursor.All(ctx, &states); err != nil {
		return nil, err
	}
	return states, nil
}

// ListIdentities provides the stable object-local rebuild scan used by
// ChatInboxView. It exposes identities only; projection composition still reads
// the full state through FindUserState.
func (store *MongoStore) ListIdentities(
	ctx context.Context,
	afterID string,
	limit int,
) ([]userstatemodel.State, string, error) {
	if limit <= 0 {
		limit = 500
	}
	filter := bson.M{}
	if afterID != "" {
		filter["_id"] = bson.M{"$gt": afterID}
	}
	cursor, err := store.states.Find(
		ctx,
		filter,
		options.Find().SetProjection(bson.M{
			"_id": 1, "userId": 1, "conversationId": 1,
		}).SetSort(bson.D{{Key: "_id", Value: 1}}).SetLimit(int64(limit+1)),
	)
	if err != nil {
		return nil, "", err
	}
	defer cursor.Close(ctx)
	var states []userstatemodel.State
	if err := cursor.All(ctx, &states); err != nil {
		return nil, "", err
	}
	next := ""
	if len(states) > limit {
		states = states[:limit]
		next = states[len(states)-1].ID
	}
	return states, next, nil
}
