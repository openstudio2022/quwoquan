package persistence

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	model "quwoquan_service/services/circle-service/internal/circle_management/circle_group_membership/domain/model"
	ports "quwoquan_service/services/circle-service/internal/circle_management/circle_group_membership/domain/ports"
)

type MongoReaders struct {
	groups            *mongo.Collection
	circleMemberships *mongo.Collection
	groupMemberships  *mongo.Collection
}

func NewMongoReaders(database *mongo.Database) *MongoReaders {
	if database == nil {
		panic("CircleGroupMembership MongoReaders requires database")
	}
	return &MongoReaders{
		groups: database.Collection("circle_groups"), circleMemberships: database.Collection("circle_memberships"),
		groupMemberships: database.Collection(membershipCollection),
	}
}

func (readers *MongoReaders) ReadGroupPolicy(ctx context.Context, circleID, groupID string) (ports.GroupPolicySlice, bool, error) {
	var document struct {
		ID                 string `bson:"_id"`
		CircleID           string `bson:"circleId"`
		JoinPolicy         string `bson:"joinPolicy"`
		Status             string `bson:"status"`
		CreatedByPersonaID string `bson:"createdByPersonaId"`
		ConversationID     string `bson:"conversationId"`
	}
	err := readers.groups.FindOne(ctx, bson.M{"_id": strings.TrimSpace(groupID), "circleId": strings.TrimSpace(circleID)}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return ports.GroupPolicySlice{}, false, nil
	}
	if err != nil {
		return ports.GroupPolicySlice{}, false, err
	}
	return ports.GroupPolicySlice{
		GroupID: document.ID, CircleID: document.CircleID, JoinPolicy: document.JoinPolicy,
		Status: document.Status, CreatedByPersonaID: document.CreatedByPersonaID, ConversationID: document.ConversationID,
	}, true, nil
}

func (readers *MongoReaders) IsActiveCircleMember(ctx context.Context, circleID, personaID string) (bool, error) {
	count, err := readers.circleMemberships.CountDocuments(ctx, bson.M{
		"circleId": strings.TrimSpace(circleID), "personaId": strings.TrimSpace(personaID), "state": "active",
	}, options.Count().SetLimit(1))
	return count == 1, err
}

func (readers *MongoReaders) ReadGroupMembership(ctx context.Context, groupID, personaID string) (model.CircleGroupMembership, bool, error) {
	var document membershipDocument
	err := readers.groupMemberships.FindOne(ctx, bson.M{
		"groupId": strings.TrimSpace(groupID), "personaId": strings.TrimSpace(personaID),
	}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return model.CircleGroupMembership{}, false, nil
	}
	if err != nil {
		return model.CircleGroupMembership{}, false, err
	}
	return document.toModel(), true, nil
}

func (readers *MongoReaders) ListGroupMemberships(ctx context.Context, groupID, state string, limit int, cursor string) (ports.MembershipPage, error) {
	if limit <= 0 {
		limit = 20
	}
	if limit > 100 {
		limit = 100
	}
	filter := bson.M{"groupId": strings.TrimSpace(groupID)}
	if state = strings.TrimSpace(state); state != "" {
		switch model.CircleGroupMembershipState(state) {
		case model.CircleGroupMembershipStatePending, model.CircleGroupMembershipStateActive,
			model.CircleGroupMembershipStateRejected, model.CircleGroupMembershipStateLeft, model.CircleGroupMembershipStateRemoved:
			filter["state"] = state
		default:
			return ports.MembershipPage{}, fmt.Errorf("invalid CircleGroupMembership state")
		}
	}
	if cursor = strings.TrimSpace(cursor); cursor != "" {
		filter["_id"] = bson.M{"$gt": cursor}
	}
	rows, err := readers.groupMemberships.Find(ctx, filter,
		options.Find().SetSort(bson.D{{Key: "_id", Value: 1}}).SetLimit(int64(limit+1)))
	if err != nil {
		return ports.MembershipPage{}, fmt.Errorf("list CircleGroupMemberships: %w", err)
	}
	defer rows.Close(ctx)
	var documents []membershipDocument
	if err := rows.All(ctx, &documents); err != nil {
		return ports.MembershipPage{}, err
	}
	result := ports.MembershipPage{Items: make([]model.CircleGroupMembership, 0, min(limit, len(documents)))}
	for index, document := range documents {
		if index >= limit {
			result.Cursor = documents[index-1].ID
			break
		}
		result.Items = append(result.Items, document.toModel())
	}
	return result, nil
}

var _ ports.GroupPolicyReader = (*MongoReaders)(nil)
var _ ports.CircleMembershipPolicyReader = (*MongoReaders)(nil)
var _ ports.MembershipReader = (*MongoReaders)(nil)
