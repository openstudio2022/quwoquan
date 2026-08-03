package persistence

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	inboxapp "quwoquan_service/services/chat-service/internal/chat/chat_inbox_view/application"
)

type MongoStore struct {
	views       *mongo.Collection
	checkpoints *mongo.Collection
}

func NewMongoStore(database *mongo.Database) *MongoStore {
	if database == nil {
		panic("ChatInboxView database is required")
	}
	return &MongoStore{
		views:       database.Collection("chat_inbox_views"),
		checkpoints: database.Collection("chat_inbox_view_checkpoints"),
	}
}

func (store *MongoStore) EnsureIndexes(ctx context.Context) error {
	if _, err := store.views.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "userId", Value: 1}, {Key: "conversationId", Value: 1}}, Options: options.Index().SetName("uq_chat_inbox_views_identity").SetUnique(true)},
		{Keys: bson.D{{Key: "userId", Value: 1}, {Key: "tombstoned", Value: 1}, {Key: "pinned", Value: -1}, {Key: "lastMessageTime", Value: -1}, {Key: "conversationId", Value: 1}}, Options: options.Index().SetName("idx_chat_inbox_views_page")},
	}); err != nil {
		return fmt.Errorf("ensure ChatInboxView indexes: %w", err)
	}
	return nil
}

func (store *MongoStore) UpsertIfNewer(
	ctx context.Context,
	item inboxapp.Item,
	source string,
	checkpoint int64,
	rebuildRunID string,
) (bool, error) {
	if err := validateWrite(item.UserID, item.ConversationID, source, checkpoint); err != nil {
		return false, err
	}
	id := identityKey(item.UserID, item.ConversationID)
	checkpointField := "sourceCheckpoints." + source
	set := bson.M{
		"userId": item.UserID, "conversationId": item.ConversationID,
		"type": item.Type, "title": item.Title, "avatarUrl": item.AvatarURL,
		"groupAvatarVersion": item.GroupAvatarVersion, "lastMessageId": item.LastMessageID,
		"lastMessagePreview": item.LastMessagePreview, "lastMessageType": item.LastMessageType,
		"lastMessageTime": item.LastMessageTime.UTC(), "lastSeq": item.LastSeq,
		"readSeq": item.ReadSeq, "inboxProjectedSeq": item.InboxProjectedSeq,
		"unreadCount": item.UnreadCount, "mentionUnreadCount": item.MentionUnreadCount,
		"muted": item.Muted, "pinned": item.Pinned, "circleId": item.CircleID,
		"conversationUpdatedAt": item.ConversationUpdated.UTC(),
		"stateUpdatedAt":        item.StateUpdated.UTC(), "lastReadAt": item.LastReadAt.UTC(),
		"tombstoned":    false,
		checkpointField: checkpoint, "updatedAt": time.Now().UTC(),
	}
	if rebuildRunID != "" {
		set["rebuildRunId"] = rebuildRunID
	}
	filter := newerSourceFilter(id, checkpointField, checkpoint)
	result, err := store.views.UpdateOne(ctx, filter, bson.M{"$set": set})
	if err != nil || result.MatchedCount > 0 {
		return result != nil && result.MatchedCount > 0, err
	}
	document := bson.M{"_id": id, "sourceCheckpoints": bson.M{source: checkpoint}}
	for key, value := range set {
		if key == checkpointField {
			continue
		}
		document[key] = value
	}
	if _, err := store.views.InsertOne(ctx, document); err != nil {
		if mongo.IsDuplicateKeyError(err) {
			return false, nil
		}
		return false, err
	}
	return true, nil
}

func (store *MongoStore) TombstoneIfNewer(
	ctx context.Context,
	identity inboxapp.Identity,
	source string,
	checkpoint int64,
) (bool, error) {
	if err := validateWrite(identity.UserID, identity.ConversationID, source, checkpoint); err != nil {
		return false, err
	}
	id := identityKey(identity.UserID, identity.ConversationID)
	checkpointField := "sourceCheckpoints." + source
	update := bson.M{
		"$set": bson.M{
			"userId": identity.UserID, "conversationId": identity.ConversationID,
			"tombstoned": true, checkpointField: checkpoint, "updatedAt": time.Now().UTC(),
		},
		"$unset": tombstoneUnset(),
	}
	result, err := store.views.UpdateOne(ctx, newerSourceFilter(id, checkpointField, checkpoint), update)
	if err != nil || result.MatchedCount > 0 {
		return result != nil && result.MatchedCount > 0, err
	}
	_, err = store.views.InsertOne(ctx, bson.M{
		"_id": id, "userId": identity.UserID, "conversationId": identity.ConversationID,
		"tombstoned": true, "sourceCheckpoints": bson.M{source: checkpoint},
		"updatedAt": time.Now().UTC(),
	})
	if mongo.IsDuplicateKeyError(err) {
		return false, nil
	}
	return err == nil, err
}

func (store *MongoStore) TombstoneConversationIfNewer(
	ctx context.Context,
	conversationID string,
	source string,
	checkpoint int64,
) (int64, error) {
	if err := validateWrite("conversation-scope", conversationID, source, checkpoint); err != nil {
		return 0, err
	}
	checkpointField := "sourceCheckpoints." + source
	filter := bson.M{
		"conversationId": conversationID,
		"$or": bson.A{
			bson.M{checkpointField: bson.M{"$lt": checkpoint}},
			bson.M{checkpointField: bson.M{"$exists": false}},
		},
	}
	result, err := store.views.UpdateMany(ctx, filter, bson.M{
		"$set":   bson.M{"tombstoned": true, checkpointField: checkpoint, "updatedAt": time.Now().UTC()},
		"$unset": tombstoneUnset(),
	})
	if err != nil {
		return 0, err
	}
	return result.ModifiedCount, nil
}

func (store *MongoStore) List(
	ctx context.Context,
	userID string,
	limit int,
	cursor string,
) (inboxapp.Page, error) {
	if limit <= 0 {
		limit = 50
	}
	filter := bson.M{"userId": userID, "tombstoned": bson.M{"$ne": true}}
	if cursor != "" {
		after, err := decodeCursor(cursor)
		if err != nil {
			return inboxapp.Page{}, err
		}
		pageFilter := bson.A{
			bson.M{"pinned": after.Pinned, "lastMessageTime": bson.M{"$lt": after.LastMessageTime}},
			bson.M{"pinned": after.Pinned, "lastMessageTime": after.LastMessageTime, "conversationId": bson.M{"$gt": after.ConversationID}},
		}
		if after.Pinned {
			pageFilter = append(bson.A{bson.M{"pinned": false}}, pageFilter...)
		}
		filter["$or"] = pageFilter
	}
	result, err := store.views.Find(
		ctx,
		filter,
		options.Find().SetSort(bson.D{
			{Key: "pinned", Value: -1}, {Key: "lastMessageTime", Value: -1},
			{Key: "conversationId", Value: 1},
		}).SetLimit(int64(limit+1)),
	)
	if err != nil {
		return inboxapp.Page{}, err
	}
	defer result.Close(ctx)
	var documents []viewDocument
	if err := result.All(ctx, &documents); err != nil {
		return inboxapp.Page{}, err
	}
	items := make([]inboxapp.Item, 0, len(documents))
	for _, document := range documents {
		items = append(items, document.item())
	}
	page := inboxapp.Page{Items: items}
	if len(items) > limit {
		page.Items = items[:limit]
		page.NextCursor = encodeCursor(page.Items[len(page.Items)-1])
	}
	return page, nil
}

func (store *MongoStore) CompleteRebuild(ctx context.Context, runID string) (int64, error) {
	result, err := store.views.UpdateMany(ctx, bson.M{
		"tombstoned": bson.M{"$ne": true}, "rebuildRunId": bson.M{"$ne": runID},
	}, bson.M{
		"$set":   bson.M{"tombstoned": true, "updatedAt": time.Now().UTC()},
		"$unset": tombstoneUnset(),
	})
	if err != nil {
		return 0, err
	}
	return result.ModifiedCount, nil
}

func (store *MongoStore) Load(ctx context.Context, consumer string) (string, error) {
	var document struct {
		Checkpoint string `bson:"checkpoint"`
	}
	err := store.checkpoints.FindOne(ctx, bson.M{"_id": consumer}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return "", nil
	}
	return document.Checkpoint, err
}

func (store *MongoStore) Save(ctx context.Context, consumer, checkpoint string) error {
	_, err := store.checkpoints.UpdateOne(
		ctx,
		bson.M{"_id": consumer},
		bson.M{"$set": bson.M{"checkpoint": checkpoint, "updatedAt": time.Now().UTC()}},
		options.UpdateOne().SetUpsert(true),
	)
	return err
}

type viewDocument struct {
	UserID              string    `bson:"userId"`
	ConversationID      string    `bson:"conversationId"`
	Type                string    `bson:"type"`
	Title               string    `bson:"title"`
	AvatarURL           string    `bson:"avatarUrl"`
	GroupAvatarVersion  int64     `bson:"groupAvatarVersion"`
	LastMessageID       string    `bson:"lastMessageId"`
	LastMessagePreview  string    `bson:"lastMessagePreview"`
	LastMessageType     string    `bson:"lastMessageType"`
	LastMessageTime     time.Time `bson:"lastMessageTime"`
	LastSeq             int64     `bson:"lastSeq"`
	ReadSeq             int64     `bson:"readSeq"`
	InboxProjectedSeq   int64     `bson:"inboxProjectedSeq"`
	UnreadCount         int       `bson:"unreadCount"`
	MentionUnreadCount  int       `bson:"mentionUnreadCount"`
	Muted               bool      `bson:"muted"`
	Pinned              bool      `bson:"pinned"`
	CircleID            string    `bson:"circleId"`
	ConversationUpdated time.Time `bson:"conversationUpdatedAt"`
	StateUpdated        time.Time `bson:"stateUpdatedAt"`
	LastReadAt          time.Time `bson:"lastReadAt"`
}

func (document viewDocument) item() inboxapp.Item {
	return inboxapp.Item{
		UserID: document.UserID, ConversationID: document.ConversationID,
		Type: document.Type, Title: document.Title, AvatarURL: document.AvatarURL,
		GroupAvatarVersion: document.GroupAvatarVersion, LastMessageID: document.LastMessageID,
		LastMessagePreview: document.LastMessagePreview, LastMessageType: document.LastMessageType,
		LastMessageTime: document.LastMessageTime, LastSeq: document.LastSeq,
		ReadSeq: document.ReadSeq, InboxProjectedSeq: document.InboxProjectedSeq,
		UnreadCount: document.UnreadCount, MentionUnreadCount: document.MentionUnreadCount,
		Muted: document.Muted, Pinned: document.Pinned, CircleID: document.CircleID,
		ConversationUpdated: document.ConversationUpdated, StateUpdated: document.StateUpdated,
		LastReadAt: document.LastReadAt,
	}
}

type cursorPayload struct {
	Pinned          bool   `json:"p"`
	LastMessageTime string `json:"t"`
	ConversationID  string `json:"c"`
}

func encodeCursor(item inboxapp.Item) string {
	raw, _ := json.Marshal(cursorPayload{
		Pinned: item.Pinned, LastMessageTime: item.LastMessageTime.UTC().Format(time.RFC3339Nano),
		ConversationID: item.ConversationID,
	})
	return base64.RawURLEncoding.EncodeToString(raw)
}

func decodeCursor(raw string) (inboxapp.Item, error) {
	decoded, err := base64.RawURLEncoding.DecodeString(strings.TrimSpace(raw))
	if err != nil {
		return inboxapp.Item{}, inboxapp.ErrInvalidCursor
	}
	var payload cursorPayload
	if err := json.Unmarshal(decoded, &payload); err != nil {
		return inboxapp.Item{}, inboxapp.ErrInvalidCursor
	}
	lastMessageTime, err := time.Parse(time.RFC3339Nano, payload.LastMessageTime)
	if err != nil || strings.TrimSpace(payload.ConversationID) == "" {
		return inboxapp.Item{}, inboxapp.ErrInvalidCursor
	}
	return inboxapp.Item{
		Pinned: payload.Pinned, LastMessageTime: lastMessageTime.UTC(),
		ConversationID: payload.ConversationID,
	}, nil
}

func validateWrite(userID, conversationID, source string, checkpoint int64) error {
	if strings.TrimSpace(userID) == "" || strings.TrimSpace(conversationID) == "" ||
		strings.TrimSpace(source) == "" || checkpoint <= 0 {
		return errors.New("ChatInboxView identity, source and checkpoint are required")
	}
	return nil
}

func identityKey(userID, conversationID string) string {
	return strings.TrimSpace(userID) + "\x00" + strings.TrimSpace(conversationID)
}

func newerSourceFilter(id, checkpointField string, checkpoint int64) bson.M {
	return bson.M{
		"_id": id,
		"$or": bson.A{
			bson.M{checkpointField: bson.M{"$lt": checkpoint}},
			bson.M{checkpointField: bson.M{"$exists": false}},
		},
	}
}

func tombstoneUnset() bson.M {
	return bson.M{
		"type": "", "title": "", "avatarUrl": "", "groupAvatarVersion": "",
		"lastMessageId": "", "lastMessagePreview": "", "lastMessageType": "",
		"lastMessageTime": "", "lastSeq": "", "readSeq": "", "inboxProjectedSeq": "",
		"lastReadAt": "", "unreadCount": "",
		"mentionUnreadCount": "", "muted": "", "pinned": "", "circleId": "",
		"conversationUpdatedAt": "", "stateUpdatedAt": "", "rebuildRunId": "",
	}
}
