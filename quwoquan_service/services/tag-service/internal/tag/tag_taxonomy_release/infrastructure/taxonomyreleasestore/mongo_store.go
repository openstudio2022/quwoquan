// Package taxonomyreleasestore 是 TagTaxonomyRelease 的 Mongo AggregateStore。
package taxonomyreleasestore

import (
	"context"
	"errors"
	"strings"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/domain/taxonomyrelease/model"
	"quwoquan_service/services/tag-service/internal/tag/tag_taxonomy_release/domain/taxonomyrelease/ports"
)

const releasesCollection = "tag_taxonomy_releases"

type Store struct {
	releases *mongo.Collection
}

func NewStore(db *mongo.Database) *Store {
	return &Store{releases: db.Collection(releasesCollection)}
}

// EnsureIndexes establishes the digest, query, and database-enforced single-active indexes.
func (s *Store) EnsureIndexes(ctx context.Context) error {
	_, err := s.releases.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "status", Value: 1}, {Key: "activatedAt", Value: -1}},
			Options: options.Index().SetName("idx_tag_taxonomy_release_status_activated"),
		},
		{
			Keys: bson.D{{Key: "status", Value: 1}},
			Options: options.Index().
				SetName("uq_tag_taxonomy_release_single_active").
				SetUnique(true).
				SetPartialFilterExpression(bson.D{{Key: "status", Value: model.StatusActive}}),
		},
		{
			Keys:    bson.D{{Key: "canonicalDigest", Value: 1}},
			Options: options.Index().SetName("idx_tag_taxonomy_release_digest").SetUnique(true),
		},
	})
	return err
}

func (s *Store) Load(ctx context.Context, releaseID string) (model.Release, bool, error) {
	var release model.Release
	err := s.releases.FindOne(ctx, bson.M{"_id": strings.TrimSpace(releaseID)}).Decode(&release)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return model.Release{}, false, nil
	}
	if err != nil {
		return model.Release{}, false, err
	}
	return release, true, nil
}

// BackfillReleaseKind upgrades a pre-releaseKind immutable record only when
// every pre-existing identity field matches the current release authority.
func (s *Store) BackfillReleaseKind(
	ctx context.Context,
	releaseID string,
	sourceOwner string,
	canonicalDigest string,
	nodeCount int,
	releaseKind model.ReleaseKind,
) error {
	existing, found, err := s.Load(ctx, releaseID)
	if err != nil || !found || existing.ReleaseKind != "" {
		return err
	}
	if existing.SourceOwner != strings.TrimSpace(sourceOwner) ||
		existing.CanonicalDigest != strings.TrimSpace(canonicalDigest) ||
		existing.NodeCount != nodeCount {
		return model.ErrDigestConflict
	}
	result, err := s.releases.UpdateOne(
		ctx,
		bson.M{
			"_id":         existing.ReleaseID,
			"releaseKind": bson.M{"$exists": false},
		},
		bson.M{"$set": bson.M{"releaseKind": releaseKind}},
	)
	if err != nil {
		return err
	}
	if result.MatchedCount != 1 {
		return model.ErrVersionConflict
	}
	return nil
}

func (s *Store) FindByDigest(ctx context.Context, canonicalDigest string) (model.Release, bool, error) {
	var release model.Release
	err := s.releases.FindOne(ctx, bson.M{"canonicalDigest": strings.TrimSpace(canonicalDigest)}).Decode(&release)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return model.Release{}, false, nil
	}
	if err != nil {
		return model.Release{}, false, err
	}
	return release, true, nil
}

func (s *Store) FindActive(ctx context.Context) (model.Release, bool, error) {
	cursor, err := s.releases.Find(
		ctx,
		bson.M{"status": model.StatusActive},
		options.Find().SetLimit(2),
	)
	if err != nil {
		return model.Release{}, false, err
	}
	defer cursor.Close(ctx)

	var active []model.Release
	if err := cursor.All(ctx, &active); err != nil {
		return model.Release{}, false, err
	}
	switch len(active) {
	case 0:
		return model.Release{}, false, nil
	case 1:
		return active[0], true, nil
	default:
		return model.Release{}, false, model.ErrActiveReleaseDrift
	}
}

// ActiveReleaseID is the release-scoped read boundary exposed to sibling objects.
func (s *Store) ActiveReleaseID(ctx context.Context) (string, bool, error) {
	release, found, err := s.FindActive(ctx)
	if err != nil || !found {
		return "", found, err
	}
	return release.ReleaseID, true, nil
}

func (s *Store) InsertStaged(ctx context.Context, release model.Release) error {
	_, err := s.releases.InsertOne(ctx, release)
	if err == nil {
		return nil
	}
	if mongo.IsDuplicateKeyError(err) {
		// 区分 digest 唯一索引冲突（幂等重放）与 releaseId 主键冲突。
		if _, found, findErr := s.FindByDigest(ctx, release.CanonicalDigest); findErr == nil && found {
			return model.ErrDigestConflict
		}
		return model.ErrVersionConflict
	}
	return err
}

func (s *Store) ActivateExclusive(ctx context.Context, target model.Release, previous *model.Release) error {
	session, err := s.releases.Database().Client().StartSession()
	if err != nil {
		return err
	}
	defer session.EndSession(ctx)

	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		if previous != nil {
			result, retireErr := s.releases.ReplaceOne(
				txCtx,
				bson.M{"_id": previous.ReleaseID, "version": previous.Version - 1},
				previous,
			)
			if retireErr != nil {
				return nil, retireErr
			}
			if result.MatchedCount != 1 {
				return nil, model.ErrVersionConflict
			}
		}
		result, activateErr := s.releases.ReplaceOne(
			txCtx,
			bson.M{"_id": target.ReleaseID, "version": target.Version - 1},
			target,
		)
		if activateErr != nil {
			return nil, activateErr
		}
		if result.MatchedCount != 1 {
			return nil, model.ErrVersionConflict
		}
		return nil, nil
	})
	return err
}

var _ ports.Store = (*Store)(nil)
