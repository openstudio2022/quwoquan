package persistence

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
	searchitemapp "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_search_item_view/application"
)

const VersionCollection = "homepage_search_item_versions"

type ESIndex struct {
	indexer  *es.Indexer
	versions *mongo.Collection
}

func NewESIndex(indexer *es.Indexer, database *mongo.Database) *ESIndex {
	if indexer == nil || database == nil {
		panic("HomepageSearchItemView ES index requires indexer and Mongo version store")
	}
	return &ESIndex{indexer: indexer, versions: database.Collection(VersionCollection)}
}

func (i *ESIndex) EnsureIndexes(ctx context.Context) error {
	_, err := i.versions.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "sourceVersion", Value: 1}},
		Options: options.Index().SetName("idx_homepage_search_item_source_version"),
	})
	return err
}

func (i *ESIndex) UpsertIfNewer(
	ctx context.Context,
	item searchitemapp.SearchItem,
) (bool, error) {
	if current, found, err := i.currentVersion(ctx, item.HomepageID); err != nil {
		return false, err
	} else if found && current >= item.SourceVersion {
		return false, nil
	}
	document := rtsearch.Document{
		ObjectType: rtsearch.ObjectTypeEntityHomepage,
		ObjectID:   strings.TrimSpace(item.HomepageID), Title: strings.TrimSpace(item.DisplayName),
		Summary:      strings.TrimSpace(item.Summary),
		SourceDomain: "entity", ContentType: strings.TrimSpace(item.EntityType),
		Visibility: "public", BadgeLabel: "主页",
		Tags: append([]string(nil), item.Tags...), Entities: []string{strings.TrimSpace(item.EntityID)},
		Popularity: float64(item.RatingCount),
		Fields: map[string]string{
			"homepageId": strings.TrimSpace(item.HomepageID),
			"entityId":   strings.TrimSpace(item.EntityID),
			"entityType": strings.TrimSpace(item.EntityType),
			"placeName":  strings.TrimSpace(item.City),
			"address":    strings.TrimSpace(item.Address),
			"placeId":    strings.TrimSpace(item.SourcePlaceID),
		},
		Freshness: item.UpdatedAt.UTC(),
	}
	if item.Latitude != nil && item.Longitude != nil {
		document.Geo = &rtsearch.GeoPoint{Lat: *item.Latitude, Lng: *item.Longitude}
	}
	if err := i.indexer.Apply(ctx, es.ChangeEvent{Op: es.OpUpsert, Doc: document}); err != nil {
		return false, fmt.Errorf("upsert HomepageSearchItemView: %w", err)
	}
	return true, i.recordVersion(ctx, item.HomepageID, item.SourceVersion, false)
}

func (i *ESIndex) DeleteIfNotOlder(
	ctx context.Context,
	homepageID string,
	sourceVersion int64,
) (bool, error) {
	if current, found, err := i.currentVersion(ctx, homepageID); err != nil {
		return false, err
	} else if found && current >= sourceVersion {
		return false, nil
	}
	if err := i.indexer.Apply(ctx, es.ChangeEvent{
		Op:  es.OpDelete,
		Doc: rtsearch.Document{ObjectType: rtsearch.ObjectTypeEntityHomepage, ObjectID: strings.TrimSpace(homepageID)},
	}); err != nil {
		return false, fmt.Errorf("delete HomepageSearchItemView: %w", err)
	}
	return true, i.recordVersion(ctx, homepageID, sourceVersion, true)
}

func (i *ESIndex) currentVersion(ctx context.Context, homepageID string) (int64, bool, error) {
	var record struct {
		SourceVersion int64 `bson:"sourceVersion"`
	}
	err := i.versions.FindOne(ctx, bson.M{"_id": strings.TrimSpace(homepageID)}).Decode(&record)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return 0, false, nil
	}
	return record.SourceVersion, err == nil, err
}

func (i *ESIndex) recordVersion(
	ctx context.Context,
	homepageID string,
	sourceVersion int64,
	tombstone bool,
) error {
	_, err := i.versions.UpdateOne(
		ctx,
		bson.M{"_id": strings.TrimSpace(homepageID), "sourceVersion": bson.M{"$lte": sourceVersion}},
		bson.M{"$set": bson.M{
			"sourceVersion": sourceVersion, "tombstone": tombstone, "updatedAt": time.Now().UTC(),
		}},
		options.UpdateOne().SetUpsert(true),
	)
	if mongo.IsDuplicateKeyError(err) {
		return nil
	}
	return err
}

var _ searchitemapp.Index = (*ESIndex)(nil)
