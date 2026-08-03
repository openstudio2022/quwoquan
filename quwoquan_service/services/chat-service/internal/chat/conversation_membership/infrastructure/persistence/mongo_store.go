package persistence

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"regexp"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	membershipapp "quwoquan_service/services/chat-service/internal/chat/conversation_membership/application"
	membershipmodel "quwoquan_service/services/chat-service/internal/chat/conversation_membership/domain/model"
)

type MongoStore struct {
	members              *mongo.Collection
	gatheringProjections *mongo.Collection
}

func NewMongoStore(database *mongo.Database) *MongoStore {
	if database == nil {
		panic("conversation membership database is required")
	}
	return &MongoStore{
		members:              database.Collection("conversation_memberships"),
		gatheringProjections: database.Collection("gathering_membership_projection_states"),
	}
}

func (store *MongoStore) EnsureIndexes(ctx context.Context) error {
	_, err := store.members.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "conversationId", Value: 1}, {Key: "userId", Value: 1}}, Options: options.Index().SetName("uq_conversation_memberships_identity").SetUnique(true)},
		{Keys: bson.D{{Key: "conversationId", Value: 1}, {Key: "role", Value: 1}, {Key: "joinedAt", Value: 1}}, Options: options.Index().SetName("idx_conversation_memberships_role_joined")},
		{Keys: bson.D{{Key: "conversationId", Value: 1}, {Key: "displayName", Value: 1}, {Key: "userId", Value: 1}}, Options: options.Index().SetName("idx_conversation_memberships_display_name")},
	})
	if err != nil {
		return fmt.Errorf("ensure ConversationMembership indexes: %w", err)
	}
	_, err = store.gatheringProjections.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "gatheringId", Value: 1}, {Key: "userId", Value: 1}}, Options: options.Index().SetName("uq_gathering_membership_projection_identity").SetUnique(true)},
		{Keys: bson.D{{Key: "conversationId", Value: 1}, {Key: "sourceVersion", Value: -1}}, Options: options.Index().SetName("idx_gathering_membership_projection_conversation")},
	})
	if err != nil {
		return fmt.Errorf("ensure Gathering membership projection indexes: %w", err)
	}
	return nil
}

func (store *MongoStore) LoadGatheringProjectionState(
	ctx context.Context,
	gatheringID string,
	personaID string,
) (membershipapp.GatheringProjectionState, bool, error) {
	var document struct {
		GatheringID    string    `bson:"gatheringId"`
		ConversationID string    `bson:"conversationId"`
		UserID         string    `bson:"userId"`
		SourceVersion  int64     `bson:"sourceVersion"`
		State          string    `bson:"state"`
		LastEventID    string    `bson:"lastEventId"`
		UpdatedAt      time.Time `bson:"updatedAt"`
	}
	err := store.gatheringProjections.FindOne(ctx, bson.M{
		"gatheringId": strings.TrimSpace(gatheringID), "userId": strings.TrimSpace(personaID),
	}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return membershipapp.GatheringProjectionState{}, false, nil
	}
	if err != nil {
		return membershipapp.GatheringProjectionState{}, false, err
	}
	return membershipapp.GatheringProjectionState{
		GatheringID: document.GatheringID, ConversationID: document.ConversationID,
		PersonaID: document.UserID, SourceVersion: document.SourceVersion,
		State: document.State, LastEventID: document.LastEventID, UpdatedAt: document.UpdatedAt,
	}, true, nil
}

func (store *MongoStore) SaveGatheringProjectionState(
	ctx context.Context,
	state membershipapp.GatheringProjectionState,
) error {
	_, err := store.gatheringProjections.ReplaceOne(
		ctx,
		bson.M{"gatheringId": state.GatheringID, "userId": state.PersonaID},
		bson.M{
			"gatheringId": state.GatheringID, "conversationId": state.ConversationID,
			"userId": state.PersonaID, "sourceVersion": state.SourceVersion,
			"state": state.State, "lastEventId": state.LastEventID, "updatedAt": state.UpdatedAt.UTC(),
		},
		options.Replace().SetUpsert(true),
	)
	return err
}

var _ membershipapp.GatheringProjectionStateStore = (*MongoStore)(nil)

func (store *MongoStore) CreateMember(ctx context.Context, member *membershipmodel.Member) error {
	if member == nil {
		return errors.New("conversation membership is required")
	}
	if err := member.Validate(); err != nil {
		return err
	}
	_, err := store.members.InsertOne(ctx, member)
	return err
}

func (store *MongoStore) DeleteMember(ctx context.Context, conversationID, userID string) error {
	_, err := store.members.DeleteOne(ctx, bson.M{"conversationId": conversationID, "userId": userID})
	return err
}

func (store *MongoStore) FindMember(ctx context.Context, conversationID, userID string) (*membershipmodel.Member, error) {
	var member membershipmodel.Member
	err := store.members.FindOne(ctx, bson.M{"conversationId": conversationID, "userId": userID}).Decode(&member)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return nil, fmt.Errorf("%w: conversation=%s persona=%s", membershipmodel.ErrNotFound, conversationID, userID)
	}
	return &member, err
}

func (store *MongoStore) UpdateMemberAvatarSnapshot(
	ctx context.Context,
	conversationID string,
	userID string,
	avatarURL string,
	avatarAssetID string,
	avatarVersion int64,
) error {
	_, err := store.members.UpdateOne(
		ctx,
		bson.M{"conversationId": conversationID, "userId": userID},
		bson.M{"$set": bson.M{
			"avatarUrl": avatarURL, "avatarAssetId": avatarAssetID, "avatarVersion": avatarVersion,
		}},
	)
	return err
}

func (store *MongoStore) UpdateMemberRole(ctx context.Context, conversationID, userID, role string) error {
	if role != "owner" && role != "admin" && role != "member" {
		return errors.New("conversation membership role is invalid")
	}
	_, err := store.members.UpdateOne(
		ctx,
		bson.M{"conversationId": conversationID, "userId": userID},
		bson.M{"$set": bson.M{"role": role}},
	)
	return err
}

func (store *MongoStore) ListMembers(
	ctx context.Context,
	conversationID string,
	query membershipmodel.ListQuery,
) ([]membershipmodel.Member, error) {
	if query.Limit <= 0 {
		query.Limit = 20
	}
	query.Sort = membershipmodel.NormalizeListSort(string(query.Sort))
	base := bson.M{
		"conversationId":    conversationID,
		"accountRestricted": bson.M{"$ne": true},
	}
	if query.Role != "" {
		base["role"] = query.Role
	}
	if search := strings.TrimSpace(query.Query); search != "" {
		literal := regexp.QuoteMeta(search)
		base["$or"] = []bson.M{
			{"displayName": bson.M{"$regex": literal, "$options": "i"}},
			{"userId": bson.M{"$regex": literal, "$options": "i"}},
		}
	}
	cursorFilter, err := listCursorFilter(query.Sort, query.Cursor)
	if err != nil {
		return nil, err
	}
	filter := base
	if cursorFilter != nil {
		filter = bson.M{"$and": []bson.M{base, cursorFilter}}
	}
	sortDocument := bson.D{{Key: "joinedAt", Value: 1}, {Key: "_id", Value: 1}}
	if query.Sort == membershipmodel.ListSortDisplayNameAsc {
		sortDocument = bson.D{{Key: "displayName", Value: 1}, {Key: "userId", Value: 1}}
	}
	cursor, err := store.members.Find(
		ctx, filter, options.Find().SetSort(sortDocument).SetLimit(int64(query.Limit)),
	)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var members []membershipmodel.Member
	if err := cursor.All(ctx, &members); err != nil {
		return nil, err
	}
	if members == nil {
		members = []membershipmodel.Member{}
	}
	return members, nil
}

func (store *MongoStore) CountMembers(ctx context.Context, conversationID string) (int, error) {
	count, err := store.members.CountDocuments(ctx, bson.M{"conversationId": conversationID})
	return int(count), err
}

func (store *MongoStore) CountUserMembers(ctx context.Context, conversationID string) (int, error) {
	count, err := store.members.CountDocuments(ctx, bson.M{
		"conversationId": conversationID, "memberType": "user",
	})
	return int(count), err
}

func (store *MongoStore) FindAssistantMember(ctx context.Context, conversationID string) (*membershipmodel.Member, error) {
	var member membershipmodel.Member
	err := store.members.FindOne(ctx, bson.M{
		"conversationId": conversationID, "memberType": "assistant",
	}).Decode(&member)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return nil, fmt.Errorf("%w: conversation=%s assistant", membershipmodel.ErrNotFound, conversationID)
	}
	return &member, err
}

func (store *MongoStore) ListSharedConversationIDs(
	ctx context.Context,
	memberA string,
	memberB string,
) ([]string, error) {
	memberA = strings.TrimSpace(memberA)
	memberB = strings.TrimSpace(memberB)
	if memberA == "" || memberB == "" {
		return nil, errors.New("conversation membership identities are required")
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
			"count":     2,
			"memberIds": bson.M{"$all": []string{memberA, memberB}},
		}}},
		{{Key: "$sort", Value: bson.D{{Key: "_id", Value: 1}}}},
	}
	cursor, err := store.members.Aggregate(ctx, pipeline)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var rows []struct {
		ID string `bson:"_id"`
	}
	if err := cursor.All(ctx, &rows); err != nil {
		return nil, err
	}
	ids := make([]string, 0, len(rows))
	for _, row := range rows {
		if id := strings.TrimSpace(row.ID); id != "" {
			ids = append(ids, id)
		}
	}
	return ids, nil
}

func listCursorFilter(sortMode membershipmodel.ListSort, encoded string) (bson.M, error) {
	if encoded == "" {
		return nil, nil
	}
	raw, err := base64.RawURLEncoding.DecodeString(encoded)
	if err != nil {
		return nil, fmt.Errorf("invalid cursor: %w", err)
	}
	if sortMode == membershipmodel.ListSortDisplayNameAsc {
		var cursor struct {
			DisplayName string `json:"d"`
			UserID      string `json:"u"`
		}
		if err := json.Unmarshal(raw, &cursor); err != nil {
			return nil, fmt.Errorf("invalid cursor: %w", err)
		}
		return bson.M{"$or": []bson.M{
			{"displayName": bson.M{"$gt": cursor.DisplayName}},
			{"$and": []bson.M{{"displayName": cursor.DisplayName}, {"userId": bson.M{"$gt": cursor.UserID}}}},
		}}, nil
	}
	var cursor struct {
		JoinedAtUnixNanos int64  `json:"t"`
		ID                string `json:"i"`
	}
	if err := json.Unmarshal(raw, &cursor); err != nil {
		return nil, fmt.Errorf("invalid cursor: %w", err)
	}
	joinedAt := time.Unix(0, cursor.JoinedAtUnixNanos).UTC()
	return bson.M{"$or": []bson.M{
		{"joinedAt": bson.M{"$gt": joinedAt}},
		{"$and": []bson.M{{"joinedAt": joinedAt}, {"_id": bson.M{"$gt": cursor.ID}}}},
	}}, nil
}
