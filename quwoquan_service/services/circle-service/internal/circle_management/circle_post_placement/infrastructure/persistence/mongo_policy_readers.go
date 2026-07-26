package persistence

import (
	"context"
	"errors"
	"strings"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	placementports "quwoquan_service/services/circle-service/internal/circle_management/circle_post_placement/domain/ports"
)

const postOwnerProjectionCollection = "circle_post_owner_views"

type MongoPolicyReaders struct {
	circles     *mongo.Collection
	groups      *mongo.Collection
	memberships *mongo.Collection
	posts       *mongo.Collection
}

var (
	_ placementports.CirclePolicyReader   = (*MongoPolicyReaders)(nil)
	_ placementports.GroupPolicyReader    = (*MongoPolicyReaders)(nil)
	_ placementports.PostOwnerReader      = (*MongoPolicyReaders)(nil)
	_ placementports.MembershipRoleReader = (*MongoPolicyReaders)(nil)
)

func NewMongoPolicyReaders(database *mongo.Database) *MongoPolicyReaders {
	if database == nil {
		panic("CirclePostPlacement MongoPolicyReaders requires database")
	}
	return &MongoPolicyReaders{
		circles: database.Collection("circles"), groups: database.Collection("circle_groups"),
		memberships: database.Collection("circle_memberships"),
		posts:       database.Collection(postOwnerProjectionCollection),
	}
}

func (readers *MongoPolicyReaders) EnsureIndexes(ctx context.Context) error {
	_, err := readers.posts.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{{Key: "ownerPersonaId", Value: 1}, {Key: "state", Value: 1}},
	})
	return err
}

func (readers *MongoPolicyReaders) ReadCirclePolicy(ctx context.Context, circleID string) (placementports.CirclePolicySlice, bool, error) {
	var document struct {
		ID      string `bson:"_id"`
		OwnerID string `bson:"ownerId"`
		Status  string `bson:"status"`
	}
	err := readers.circles.FindOne(ctx, bson.D{{Key: "_id", Value: strings.TrimSpace(circleID)}}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return placementports.CirclePolicySlice{}, false, nil
	}
	if err != nil {
		return placementports.CirclePolicySlice{}, false, err
	}
	return placementports.CirclePolicySlice{
		CircleID: document.ID, OwnerPersonaID: document.OwnerID, State: document.Status,
	}, true, nil
}

func (readers *MongoPolicyReaders) ReadGroupPolicy(ctx context.Context, groupID string) (placementports.GroupPolicySlice, bool, error) {
	var document struct {
		ID       string `bson:"_id"`
		CircleID string `bson:"circleId"`
		Status   string `bson:"status"`
	}
	err := readers.groups.FindOne(ctx, bson.D{{Key: "_id", Value: strings.TrimSpace(groupID)}}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return placementports.GroupPolicySlice{}, false, nil
	}
	if err != nil {
		return placementports.GroupPolicySlice{}, false, err
	}
	return placementports.GroupPolicySlice{GroupID: document.ID, CircleID: document.CircleID, State: document.Status}, true, nil
}

func (readers *MongoPolicyReaders) ReadPostOwner(ctx context.Context, postID string) (placementports.PostOwnerSlice, bool, error) {
	var document struct {
		ID             string `bson:"_id"`
		OwnerPersonaID string `bson:"ownerPersonaId"`
		State          string `bson:"state"`
	}
	err := readers.posts.FindOne(ctx, bson.D{{Key: "_id", Value: strings.TrimSpace(postID)}}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return placementports.PostOwnerSlice{}, false, nil
	}
	if err != nil {
		return placementports.PostOwnerSlice{}, false, err
	}
	return placementports.PostOwnerSlice{
		PostID: document.ID, OwnerPersonaID: document.OwnerPersonaID, State: document.State,
	}, true, nil
}

func (readers *MongoPolicyReaders) ReadMembershipRole(ctx context.Context, circleID, personaID string) (placementports.MembershipRoleSlice, bool, error) {
	var document struct {
		CircleID  string `bson:"circleId"`
		PersonaID string `bson:"personaId"`
		Role      string `bson:"role"`
		State     string `bson:"state"`
	}
	err := readers.memberships.FindOne(ctx, bson.D{
		{Key: "circleId", Value: strings.TrimSpace(circleID)},
		{Key: "personaId", Value: strings.TrimSpace(personaID)},
	}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return placementports.MembershipRoleSlice{}, false, nil
	}
	if err != nil {
		return placementports.MembershipRoleSlice{}, false, err
	}
	return placementports.MembershipRoleSlice{
		CircleID: document.CircleID, PersonaID: document.PersonaID,
		Role: document.Role, State: document.State,
	}, true, nil
}
