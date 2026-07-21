package persistence

import (
	"context"
	"errors"
	"fmt"
	"regexp"
	"strings"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	groupmodel "quwoquan_service/services/circle-service/internal/domain/circle/circle_group/model"
	groupports "quwoquan_service/services/circle-service/internal/domain/circle/circle_group/ports"
)

type MongoReaders struct {
	circles           *mongo.Collection
	circleMemberships *mongo.Collection
	groupMemberships  *mongo.Collection
	groups            *mongo.Collection
}

func NewMongoReaders(database *mongo.Database) *MongoReaders {
	if database == nil {
		panic("CircleGroup MongoReaders requires database")
	}
	return &MongoReaders{
		circles: database.Collection("circles"), circleMemberships: database.Collection("circle_memberships"),
		groupMemberships: database.Collection("circle_group_memberships"), groups: database.Collection(groupCollection),
	}
}

func (readers *MongoReaders) ReadCirclePolicy(ctx context.Context, circleID string) (groupports.CirclePolicySlice, bool, error) {
	var document struct {
		ID    string `bson:"_id"`
		State string `bson:"status"`
	}
	err := readers.circles.FindOne(ctx, bson.M{"_id": strings.TrimSpace(circleID)}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return groupports.CirclePolicySlice{}, false, nil
	}
	if err != nil {
		return groupports.CirclePolicySlice{}, false, err
	}
	return groupports.CirclePolicySlice{CircleID: document.ID, State: document.State}, true, nil
}

func (readers *MongoReaders) ReadCircleMembership(ctx context.Context, circleID, personaID string) (groupports.CircleMembershipPolicySlice, bool, error) {
	var document struct {
		PersonaID string `bson:"personaId"`
		Role      string `bson:"role"`
		State     string `bson:"state"`
	}
	err := readers.circleMemberships.FindOne(ctx, bson.M{
		"circleId": strings.TrimSpace(circleID), "personaId": strings.TrimSpace(personaID),
	}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return groupports.CircleMembershipPolicySlice{}, false, nil
	}
	if err != nil {
		return groupports.CircleMembershipPolicySlice{}, false, err
	}
	return groupports.CircleMembershipPolicySlice{PersonaID: document.PersonaID, Role: document.Role, State: document.State}, true, nil
}

func (readers *MongoReaders) ReadGroupMembership(ctx context.Context, groupID, personaID string) (groupports.GroupMembershipPolicySlice, bool, error) {
	var document struct {
		PersonaID string `bson:"personaId"`
		Role      string `bson:"role"`
		State     string `bson:"state"`
	}
	err := readers.groupMemberships.FindOne(ctx, bson.M{
		"groupId": strings.TrimSpace(groupID), "personaId": strings.TrimSpace(personaID),
	}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return groupports.GroupMembershipPolicySlice{}, false, nil
	}
	if err != nil {
		return groupports.GroupMembershipPolicySlice{}, false, err
	}
	return groupports.GroupMembershipPolicySlice{PersonaID: document.PersonaID, Role: document.Role, State: document.State}, true, nil
}

func (readers *MongoReaders) ReadParent(ctx context.Context, circleID, groupID string) (groupmodel.CircleGroup, bool, error) {
	var group groupmodel.CircleGroup
	err := readers.groups.FindOne(ctx, bson.M{
		"_id": strings.TrimSpace(groupID), "circleId": strings.TrimSpace(circleID),
	}).Decode(&group)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return groupmodel.CircleGroup{}, false, nil
	}
	if err != nil {
		return groupmodel.CircleGroup{}, false, err
	}
	return group, true, nil
}

func (readers *MongoReaders) ParentChainContains(ctx context.Context, circleID, parentID, candidateID string) (bool, error) {
	seen := map[string]struct{}{}
	currentID := strings.TrimSpace(parentID)
	for depth := 0; depth < 64 && currentID != ""; depth++ {
		if currentID == strings.TrimSpace(candidateID) {
			return true, nil
		}
		if _, exists := seen[currentID]; exists {
			return true, nil
		}
		seen[currentID] = struct{}{}
		parent, found, err := readers.ReadParent(ctx, circleID, currentID)
		if err != nil {
			return false, err
		}
		if !found {
			return false, groupmodel.ErrParentInvalid
		}
		currentID = strings.TrimSpace(parent.ParentGroupID)
	}
	if currentID != "" {
		return false, groupmodel.ErrParentInvalid
	}
	return false, nil
}

func (readers *MongoReaders) ReadGroup(ctx context.Context, circleID, groupID string) (groupports.GroupReadSlice, bool, error) {
	var group groupmodel.CircleGroup
	err := readers.groups.FindOne(ctx, bson.M{
		"_id": strings.TrimSpace(groupID), "circleId": strings.TrimSpace(circleID),
	}).Decode(&group)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return groupports.GroupReadSlice{}, false, nil
	}
	if err != nil {
		return groupports.GroupReadSlice{}, false, err
	}
	counts, err := readers.memberCounts(ctx, []string{group.ID})
	if err != nil {
		return groupports.GroupReadSlice{}, false, err
	}
	return groupports.GroupReadSlice{Group: group, MemberCount: counts[group.ID]}, true, nil
}

func (readers *MongoReaders) ListGroups(ctx context.Context, query groupports.ListQuery) (groupports.GroupPageSlice, error) {
	filter := bson.M{"circleId": strings.TrimSpace(query.CircleID), "status": groupmodel.CircleGroupStatusActive}
	if query.GroupType != "" {
		filter["groupType"] = query.GroupType
	}
	if query.Visibility != "" {
		filter["visibility"] = query.Visibility
	}
	if query.ParentGroupID != "" {
		filter["parentGroupId"] = query.ParentGroupID
	}
	if query.NodeType != "" {
		filter["nodeType"] = query.NodeType
	}
	return readers.list(ctx, filter, query.Cursor, query.Limit)
}

func (readers *MongoReaders) SearchGroups(ctx context.Context, query groupports.SearchQuery) (groupports.GroupPageSlice, error) {
	pattern := regexp.QuoteMeta(strings.TrimSpace(query.Query))
	filter := bson.M{
		"circleId": strings.TrimSpace(query.CircleID), "status": groupmodel.CircleGroupStatusActive,
		"$or": bson.A{bson.M{"name": bson.M{"$regex": pattern, "$options": "i"}}, bson.M{"description": bson.M{"$regex": pattern, "$options": "i"}}},
	}
	if query.GroupType != "" {
		filter["groupType"] = query.GroupType
	}
	if query.Visibility != "" {
		filter["visibility"] = query.Visibility
	}
	return readers.list(ctx, filter, query.Cursor, query.Limit)
}

func (readers *MongoReaders) list(ctx context.Context, filter bson.M, cursor string, limit int) (groupports.GroupPageSlice, error) {
	if limit <= 0 {
		limit = 20
	}
	if limit > 100 {
		limit = 100
	}
	if cursor = strings.TrimSpace(cursor); cursor != "" {
		filter["_id"] = bson.M{"$gt": cursor}
	}
	rows, err := readers.groups.Find(ctx, filter,
		options.Find().SetSort(bson.D{{Key: "_id", Value: 1}}).SetLimit(int64(limit+1)))
	if err != nil {
		return groupports.GroupPageSlice{}, fmt.Errorf("list CircleGroups: %w", err)
	}
	defer rows.Close(ctx)
	var groups []groupmodel.CircleGroup
	if err := rows.All(ctx, &groups); err != nil {
		return groupports.GroupPageSlice{}, fmt.Errorf("decode CircleGroups: %w", err)
	}
	page := groupports.GroupPageSlice{Items: make([]groupports.GroupReadSlice, 0, min(limit, len(groups)))}
	visible := groups
	if len(visible) > limit {
		page.Cursor = visible[limit-1].ID
		visible = visible[:limit]
	}
	groupIDs := make([]string, 0, len(visible))
	for _, group := range visible {
		groupIDs = append(groupIDs, group.ID)
	}
	counts, err := readers.memberCounts(ctx, groupIDs)
	if err != nil {
		return groupports.GroupPageSlice{}, err
	}
	for _, group := range visible {
		page.Items = append(page.Items, groupports.GroupReadSlice{Group: group, MemberCount: counts[group.ID]})
	}
	return page, nil
}

func (readers *MongoReaders) memberCounts(ctx context.Context, groupIDs []string) (map[string]int64, error) {
	result := make(map[string]int64, len(groupIDs))
	if len(groupIDs) == 0 {
		return result, nil
	}
	rows, err := readers.groupMemberships.Aggregate(ctx, mongo.Pipeline{
		{{Key: "$match", Value: bson.M{"groupId": bson.M{"$in": groupIDs}, "state": "active"}}},
		{{Key: "$group", Value: bson.M{"_id": "$groupId", "count": bson.M{"$sum": 1}}}},
	})
	if err != nil {
		return nil, fmt.Errorf("count CircleGroup memberships: %w", err)
	}
	defer rows.Close(ctx)
	for rows.Next(ctx) {
		var item struct {
			GroupID string `bson:"_id"`
			Count   int64  `bson:"count"`
		}
		if err := rows.Decode(&item); err != nil {
			return nil, err
		}
		result[item.GroupID] = item.Count
	}
	return result, rows.Err()
}

var (
	_ groupports.PolicyReader = (*MongoReaders)(nil)
	_ groupports.GroupReader  = (*MongoReaders)(nil)
)
