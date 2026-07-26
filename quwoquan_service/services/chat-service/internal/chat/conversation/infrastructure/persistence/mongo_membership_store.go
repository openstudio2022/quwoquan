// ConversationMembership 聚合的成员名册端口实现（MongoChatStore 分文件）。
package persistence

import (
	"context"
	"errors"
	"fmt"
	"regexp"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/chat-service/internal/chat/conversation/application"
	model "quwoquan_service/services/chat-service/internal/chat/conversation/domain/model"
)

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
	if search := strings.TrimSpace(query.Query); search != "" {
		literal := regexp.QuoteMeta(search)
		base["$or"] = []bson.M{
			{"displayName": bson.M{"$regex": literal, "$options": "i"}},
			{"userId": bson.M{"$regex": literal, "$options": "i"}},
		}
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

func (s *MongoChatStore) CountUserMembers(
	ctx context.Context,
	conversationId string,
) (int, error) {
	count, err := s.members.CountDocuments(ctx, bson.M{
		"conversationId": conversationId,
		"memberType":     "user",
	})
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
		if errors.Is(err, mongo.ErrNoDocuments) {
			return nil, fmt.Errorf(
				"%w: conversation=%s assistant",
				model.ErrMemberNotFound,
				conversationId,
			)
		}
		return nil, err
	}
	return &member, nil
}

// ── User State ───────────────────────────────────────────────────────────────
