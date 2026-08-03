package persistence

import (
	"context"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	creatorapp "quwoquan_service/services/user-service/internal/profile_projection/creator_runtime_profile/application"
	"quwoquan_service/services/user-service/internal/profile_projection/creator_runtime_profile/domain/model"
)

const creatorRuntimeActive = "active"

// CreatorRuntimeProfileReader is the projection's named reader and monotonic
// event store. Release import remains a separate object-local rebuild adapter.
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

func (r *CreatorRuntimeProfileReader) EnsureIndexes(ctx context.Context) error {
	if r == nil || r.collection == nil {
		return fmt.Errorf("CreatorRuntimeProfile Mongo store is unavailable")
	}
	_, err := r.collection.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "creatorId", Value: 1}}, Options: options.Index().SetName("idx_creator_runtime_creator_id_unique").SetUnique(true)},
		{Keys: bson.D{{Key: "personaId", Value: 1}, {Key: "status", Value: 1}}, Options: options.Index().SetName("idx_creator_runtime_persona")},
		{Keys: bson.D{{Key: "handle", Value: 1}, {Key: "status", Value: 1}}, Options: options.Index().SetName("idx_creator_runtime_handle")},
		{Keys: bson.D{{Key: "managedBy", Value: 1}, {Key: "status", Value: 1}}, Options: options.Index().SetName("idx_creator_runtime_managed_status")},
	})
	return err
}

func (r *CreatorRuntimeProfileReader) UpsertIfNewer(
	ctx context.Context,
	profile creatorapp.Profile,
) (bool, error) {
	result, err := r.collection.UpdateOne(ctx, bson.M{
		"creatorId": strings.TrimSpace(profile.CreatorID),
		"$or": bson.A{
			bson.M{"sourceVersion": bson.M{"$lt": profile.SourceVersion}},
			bson.M{"sourceVersion": bson.M{"$exists": false}},
		},
	}, bson.M{
		"$set": bson.M{
			"displayName": profile.DisplayName, "avatarUrl": profile.AvatarURL,
			"followerCount": profile.FollowerCount, "postCount": profile.PostCount,
			"sourceVersion": profile.SourceVersion, "status": creatorRuntimeActive,
			"updatedAt": profile.UpdatedAt.UTC(),
		},
		"$setOnInsert": bson.M{"creatorId": strings.TrimSpace(profile.CreatorID)},
	}, options.UpdateOne().SetUpsert(true))
	if mongo.IsDuplicateKeyError(err) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	return result.ModifiedCount > 0 || result.UpsertedCount > 0, nil
}

func (r *CreatorRuntimeProfileReader) DeleteIfNotOlder(
	ctx context.Context,
	creatorID string,
	sourceVersion int64,
) (bool, error) {
	now := time.Now().UTC()
	result, err := r.collection.UpdateOne(ctx, bson.M{
		"creatorId": strings.TrimSpace(creatorID),
		"$or": bson.A{
			bson.M{"sourceVersion": bson.M{"$lte": sourceVersion}},
			bson.M{"sourceVersion": bson.M{"$exists": false}},
		},
	}, bson.M{"$set": bson.M{
		"sourceVersion": sourceVersion, "status": "tombstoned",
		"tombstonedAt": now, "updatedAt": now,
	}})
	if err != nil {
		return false, err
	}
	return result.ModifiedCount > 0, nil
}

func (r *CreatorRuntimeProfileReader) TombstoneForClosedSubjects(
	ctx context.Context,
	personaIDs []string,
	closedAt time.Time,
) error {
	if r == nil || r.collection == nil {
		return fmt.Errorf("CreatorRuntimeProfile Mongo store is unavailable")
	}
	_, err := r.collection.UpdateMany(
		ctx,
		bson.M{"$or": bson.A{
			bson.M{"personaId": bson.M{"$in": personaIDs}},
			bson.M{"creatorId": bson.M{"$in": personaIDs}},
		}},
		bson.M{
			"$set": bson.M{
				"status":       "tombstoned",
				"displayName":  "已注销用户",
				"tombstonedAt": closedAt.UTC(),
				"updatedAt":    closedAt.UTC(),
			},
			"$unset": creatorProfilePIIUnset(),
		},
	)
	if err != nil {
		return fmt.Errorf("tombstone closed CreatorRuntimeProfile projections: %w", err)
	}
	return nil
}

func creatorProfilePIIUnset() bson.M {
	return bson.M{
		"handle": "", "headline": "", "bio": "", "slogan": "",
		"avatarUrl": "", "avatarObjectKey": "", "avatarSha256": "",
		"coverUrl": "", "coverObjectKey": "", "coverSha256": "",
		"tagRefs": "", "publicProfileTagRefs": "", "roles": "", "verticals": "",
		"segment": "", "preferredContentTypes": "", "creatorArchetype": "",
		"carrierAffinity": "", "preferredBlueprintIds": "", "coverageScope": "",
		"claimPolicy": "", "expertiseClaims": "", "mustNotClaim": "",
		"disclosure": "", "entityRefs": "", "circleRefs": "", "sourceStatus": "",
		"works": "", "packageDigest": "", "releaseId": "", "managedBy": "",
		"importedAt": "", "preferredBlueprintVersion": "",
	}
}

func (r *CreatorRuntimeProfileReader) FindActiveByPublicIdentity(
	ctx context.Context,
	identity string,
) (*model.CreatorRuntimeProfile, bool, error) {
	identity = strings.TrimSpace(identity)
	if identity == "" || r == nil || r.collection == nil {
		return nil, false, nil
	}
	profiles, err := r.findProfiles(
		ctx,
		bson.M{
			"status": creatorRuntimeActive,
			"$or": bson.A{
				bson.M{"creatorId": identity},
				bson.M{"personaId": identity},
			},
		},
		2,
	)
	if err != nil {
		return nil, false, err
	}
	if len(profiles) > 1 {
		return nil, false, fmt.Errorf(
			"active creator public identity %q 不唯一",
			identity,
		)
	}
	if len(profiles) == 1 {
		return &profiles[0], true, nil
	}
	return nil, false, nil
}

func (r *CreatorRuntimeProfileReader) ListActiveWorks(
	ctx context.Context,
	identity string,
) ([]model.CreatorWorkRef, bool, error) {
	profile, found, err := r.FindActiveByPublicIdentity(ctx, identity)
	if err != nil || !found {
		return nil, found, err
	}
	return append([]model.CreatorWorkRef(nil), profile.Works...), true, nil
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

var _ creatorapp.Store = (*CreatorRuntimeProfileReader)(nil)
