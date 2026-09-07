package persistence

import (
	"context"
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
	applied, err := i.indexer.ApplyVersioned(ctx, es.VersionedChangeEvent{
		Op: es.OpUpsert, Doc: document, SourceVersion: item.SourceVersion,
	})
	if err != nil {
		return false, fmt.Errorf("upsert HomepageSearchItemView: %w", err)
	}
	if err := i.recordVersion(ctx, item.HomepageID, item.SourceVersion, false); err != nil {
		return applied, err
	}
	return applied, nil
}

func (i *ESIndex) DeleteIfNotOlder(
	ctx context.Context,
	homepageID string,
	sourceVersion int64,
) (bool, error) {
	applied, err := i.indexer.ApplyVersioned(ctx, es.VersionedChangeEvent{
		Op: es.OpDelete,
		Doc: rtsearch.Document{
			ObjectType: rtsearch.ObjectTypeEntityHomepage,
			ObjectID:   strings.TrimSpace(homepageID),
		},
		SourceVersion: sourceVersion,
	})
	if err != nil {
		return false, fmt.Errorf("delete HomepageSearchItemView: %w", err)
	}
	if err := i.recordVersion(ctx, homepageID, sourceVersion, true); err != nil {
		return applied, err
	}
	return applied, nil
}

// recordVersion is a progress/checkpoint record only; Elasticsearch external
// versioning is the mutation arbiter. The conditional update plus insert/retry
// path makes this record monotonic without an unsafe read-before-write upsert.
func (i *ESIndex) recordVersion(
	ctx context.Context,
	homepageID string,
	sourceVersion int64,
	tombstone bool,
) error {
	id := strings.TrimSpace(homepageID)
	update := bson.M{"$set": bson.M{
		"sourceVersion": sourceVersion,
		"tombstone":     tombstone,
		"updatedAt":     time.Now().UTC(),
	}}
	filter := bson.M{"_id": id, "sourceVersion": bson.M{"$lt": sourceVersion}}
	result, err := i.versions.UpdateOne(ctx, filter, update)
	if err != nil {
		return err
	}
	if result.MatchedCount > 0 {
		return nil
	}
	_, err = i.versions.InsertOne(ctx, bson.M{
		"_id": id, "sourceVersion": sourceVersion,
		"tombstone": tombstone, "updatedAt": time.Now().UTC(),
	})
	if err == nil {
		return nil
	}
	if !mongo.IsDuplicateKeyError(err) {
		return err
	}
	// A concurrent higher/equal checkpoint won the insert. Retry only the
	// strictly-newer conditional update; a lower/equal input remains a no-op.
	_, err = i.versions.UpdateOne(ctx, filter, update)
	return err
}

var _ searchitemapp.Index = (*ESIndex)(nil)
