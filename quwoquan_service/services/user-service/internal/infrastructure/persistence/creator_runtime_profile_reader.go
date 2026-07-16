package persistence

import (
	"context"
	"errors"
	"fmt"
	"strings"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/user-service/internal/domain/user/model"
)

const creatorRuntimeActive = "active"

// CreatorRuntimeProfileReader is a named reader for the rebuildable
// CreatorRuntimeProfile projection. Projection writes are owned by the event
// pipeline; this adapter intentionally exposes no import/sync mutation API.
type CreatorRuntimeProfileReader struct {
	collection *mongo.Collection
}

func NewCreatorRuntimeProfileReader(database *mongo.Database) *CreatorRuntimeProfileReader {
	if database == nil {
		return &CreatorRuntimeProfileReader{}
	}
	return &CreatorRuntimeProfileReader{
		collection: database.Collection("creator_runtime_profiles"),
	}
}

func (r *CreatorRuntimeProfileReader) FindActiveByIdentity(
	ctx context.Context,
	identity string,
) (*model.CreatorRuntimeProfile, bool, error) {
	identity = strings.TrimSpace(identity)
	if identity == "" || r == nil || r.collection == nil {
		return nil, false, nil
	}
	if profile, found, err := r.findByCreatorID(ctx, identity); err != nil {
		return nil, false, err
	} else if found && profile.Status == creatorRuntimeActive {
		return profile, true, nil
	}
	for _, field := range []string{"subAccountId", "handle"} {
		profiles, err := r.findProfiles(
			ctx,
			bson.M{field: identity, "status": creatorRuntimeActive},
			2,
		)
		if err != nil {
			return nil, false, err
		}
		if len(profiles) > 1 {
			return nil, false, fmt.Errorf("active creator %s %q 不唯一", field, identity)
		}
		if len(profiles) == 1 {
			return &profiles[0], true, nil
		}
	}
	return nil, false, nil
}

func (r *CreatorRuntimeProfileReader) ListActiveWorks(
	ctx context.Context,
	identity string,
) ([]model.CreatorWorkRef, bool, error) {
	profile, found, err := r.FindActiveByIdentity(ctx, identity)
	if err != nil || !found {
		return nil, found, err
	}
	return append([]model.CreatorWorkRef(nil), profile.Works...), true, nil
}

func (r *CreatorRuntimeProfileReader) findByCreatorID(
	ctx context.Context,
	creatorID string,
) (*model.CreatorRuntimeProfile, bool, error) {
	var profile model.CreatorRuntimeProfile
	err := r.collection.FindOne(ctx, bson.M{"creatorId": creatorID}).Decode(&profile)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, err
	}
	return &profile, true, nil
}

func (r *CreatorRuntimeProfileReader) findProfiles(
	ctx context.Context,
	filter bson.M,
	limit int64,
) ([]model.CreatorRuntimeProfile, error) {
	cursor, err := r.collection.Find(ctx, filter, options.Find().SetLimit(limit))
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var profiles []model.CreatorRuntimeProfile
	if err := cursor.All(ctx, &profiles); err != nil {
		return nil, err
	}
	return profiles, nil
}
