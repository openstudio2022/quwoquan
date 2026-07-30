// Package persistence 实现 Homepage 对象专属 Mongo Store。
package persistence

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strconv"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/entity-service/generated/entity_homepage/homepage"
	homepagemodel "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/model"
	homepageports "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/ports"
)

const (
	homepageCollection           = "homepages"
	homepageReceiptsCollection   = "homepage_command_receipts"
	homepageOutboxCollection     = "homepage_outbox"
	homepageDetailsCollection    = "homepage_detail_views"
	homepageFollowersCollection  = "homepage_follower_projection"
	homepageCheckpointCollection = "homepage_projection_checkpoints"
)

type MongoHomepageStore struct {
	homepages   *mongo.Collection
	receipts    *mongo.Collection
	outbox      *mongo.Collection
	details     *mongo.Collection
	followers   *mongo.Collection
	checkpoints *mongo.Collection
	supportsTxn bool
}

func NewMongoHomepageStore(db *mongo.Database, supportsTransactions bool) *MongoHomepageStore {
	return &MongoHomepageStore{
		homepages:   db.Collection(homepageCollection),
		receipts:    db.Collection(homepageReceiptsCollection),
		outbox:      db.Collection(homepageOutboxCollection),
		details:     db.Collection(homepageDetailsCollection),
		followers:   db.Collection(homepageFollowersCollection),
		checkpoints: db.Collection(homepageCheckpointCollection),
		supportsTxn: supportsTransactions,
	}
}

var (
	_ homepageports.AggregateStore            = (*MongoHomepageStore)(nil)
	_ homepageports.Reader                    = (*MongoHomepageStore)(nil)
	_ homepageports.DetailProjectionStore     = (*MongoHomepageStore)(nil)
	_ homepageports.FollowerProjectionStore   = (*MongoHomepageStore)(nil)
	_ homepageports.OutboxReader              = (*MongoHomepageStore)(nil)
	_ homepageports.ProjectionCheckpointStore = (*MongoHomepageStore)(nil)
)

func (s *MongoHomepageStore) EnsureIndexes(ctx context.Context) error {
	if _, err := s.homepages.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "status", Value: 1}, {Key: "updatedAt", Value: -1}},
			Options: options.Index().SetName("idx_homepages_status_updated"),
		},
		{
			Keys:    bson.D{{Key: "homepageType", Value: 1}, {Key: "city", Value: 1}, {Key: "updatedAt", Value: -1}},
			Options: options.Index().SetName("idx_homepages_type_city").SetSparse(true),
		},
		{
			Keys:    bson.D{{Key: "canonicalEntityId", Value: 1}},
			Options: options.Index().SetName("idx_homepages_canonical_entity").SetUnique(true),
		},
		{
			Keys:    bson.D{{Key: "sourceOwner", Value: 1}, {Key: "sourceEntityRef", Value: 1}},
			Options: options.Index().SetName("idx_homepages_source").SetUnique(true).SetSparse(true),
		},
		{
			Keys:    bson.D{{Key: "lookupAliases", Value: 1}},
			Options: options.Index().SetName("idx_homepages_lookup_aliases").SetSparse(true),
		},
		{
			Keys:    bson.D{{Key: "objectPageTemplate", Value: 1}, {Key: "homepageType", Value: 1}, {Key: "updatedAt", Value: -1}},
			Options: options.Index().SetName("idx_homepages_template_type"),
		},
		{
			Keys:    bson.D{{Key: "location", Value: "2dsphere"}},
			Options: options.Index().SetName("idx_homepages_location").SetSparse(true),
		},
		{
			Keys:    bson.D{{Key: "_id", Value: 1}, {Key: "version", Value: 1}},
			Options: options.Index().SetName("idx_homepages_version").SetUnique(true),
		},
		{
			Keys: bson.D{
				{Key: "title", Value: "text"},
				{Key: "subtitle", Value: "text"},
				{Key: "address", Value: "text"},
				{Key: "city", Value: "text"},
			},
			Options: options.Index().SetName("search_homepages_text").SetWeights(bson.D{
				{Key: "title", Value: 10},
				{Key: "subtitle", Value: 5},
				{Key: "address", Value: 3},
				{Key: "city", Value: 2},
			}),
		},
	}); err != nil {
		return err
	}
	if _, err := s.receipts.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "aggregateId", Value: 1}, {Key: "aggregateVersion", Value: -1}},
			Options: options.Index().SetName("idx_homepage_command_receipts_aggregate"),
		},
		{
			Keys:    bson.D{{Key: "expiresAt", Value: 1}},
			Options: options.Index().SetName("idx_homepage_command_receipts_expire").SetExpireAfterSeconds(0),
		},
	}); err != nil {
		return err
	}
	if _, err := s.outbox.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "occurredAt", Value: 1}, {Key: "_id", Value: 1}},
			Options: options.Index().SetName("idx_homepage_outbox_replay"),
		},
		{
			Keys:    bson.D{{Key: "aggregateId", Value: 1}, {Key: "aggregateVersion", Value: 1}},
			Options: options.Index().SetName("idx_homepage_outbox_aggregate_version").SetUnique(true),
		},
	}); err != nil {
		return err
	}
	if _, err := s.details.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "updatedAt", Value: -1}},
		Options: options.Index().SetName("idx_homepage_detail_views_updated"),
	}); err != nil {
		return err
	}
	if _, err := s.followers.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "homepageId", Value: 1}, {Key: "personaId", Value: 1}},
			Options: options.Index().SetName("idx_homepage_follower_identity").SetUnique(true),
		},
		{
			Keys:    bson.D{{Key: "homepageId", Value: 1}, {Key: "following", Value: 1}},
			Options: options.Index().SetName("idx_homepage_follower_count"),
		},
		{
			Keys:    bson.D{{Key: "homepageId", Value: 1}, {Key: "personaId", Value: 1}, {Key: "sourceVersion", Value: -1}},
			Options: options.Index().SetName("idx_homepage_follower_source_version"),
		},
	}); err != nil {
		return err
	}
	// checkpoint consumer 以 Mongo 内建唯一 _id 索引实现。
	return nil
}

type homepageDocument struct {
	ID                   string                            `bson:"_id"`
	Version              int64                             `bson:"version"`
	Title                string                            `bson:"title"`
	Subtitle             string                            `bson:"subtitle,omitempty"`
	HomepageType         string                            `bson:"homepageType"`
	CanonicalEntityID    string                            `bson:"canonicalEntityId"`
	LookupAliases        []string                          `bson:"lookupAliases,omitempty"`
	ObjectPageTemplate   string                            `bson:"objectPageTemplate"`
	Status               string                            `bson:"status"`
	SourceType           string                            `bson:"sourceType"`
	SourceOwner          string                            `bson:"sourceOwner,omitempty"`
	SourceEntityRef      string                            `bson:"sourceEntityRef,omitempty"`
	SourceReleaseID      string                            `bson:"sourceReleaseId,omitempty"`
	ClaimStatus          string                            `bson:"claimStatus"`
	CategoryTags         []string                          `bson:"categoryTags,omitempty"`
	CoverURL             string                            `bson:"coverUrl,omitempty"`
	Address              string                            `bson:"address,omitempty"`
	City                 string                            `bson:"city,omitempty"`
	Location             *geoJSONPoint                     `bson:"location,omitempty"`
	OwnerUserID          string                            `bson:"ownerUserId,omitempty"`
	OwnerPersonaID       string                            `bson:"ownerPersonaId,omitempty"`
	Verified             bool                              `bson:"verified"`
	EstablishedYear      *int                              `bson:"establishedYear,omitempty"`
	IntroductionMarkdown string                            `bson:"introductionMarkdown,omitempty"`
	IntroductionAssets   []homepagemodel.IntroductionAsset `bson:"introductionAssets,omitempty"`
	StructuredFacts      *homepagemodel.StructuredFacts    `bson:"structuredFacts,omitempty"`
	PrimarySource        *homepagemodel.Source             `bson:"primarySource,omitempty"`
	SourceURLs           []string                          `bson:"sourceUrls,omitempty"`
	CreatedAt            time.Time                         `bson:"createdAt"`
	UpdatedAt            time.Time                         `bson:"updatedAt"`
	PublishedAt          *time.Time                        `bson:"publishedAt,omitempty"`
	OfflineAt            *time.Time                        `bson:"offlineAt,omitempty"`
}

// geoJSONPoint 是 location 的落库形状。idx_homepages_location 是 2dsphere 索引，
// 只接受 GeoJSON 或有序 legacy 坐标对；若直接落库 domain GeoPoint 的
// {latitude, longitude} 嵌套文档，Mongo 会把它读成 legacy [x=latitude, y=longitude]，
// 既交换了轴又会因纬度值超出 ±90 直接拒绝写入。因此存储层负责 GeoJSON 翻译，
// wire/domain 仍保持 latitude/longitude 命名（contracts fields.yaml 真相源不变）。
type geoJSONPoint struct {
	Type        string    `bson:"type"`
	Coordinates []float64 `bson:"coordinates"`
}

func geoJSONFromGeoPoint(point *homepagemodel.GeoPoint) *geoJSONPoint {
	if point == nil {
		return nil
	}
	return &geoJSONPoint{Type: "Point", Coordinates: []float64{point.Longitude, point.Latitude}}
}

func (p *geoJSONPoint) geoPoint() *homepagemodel.GeoPoint {
	if p == nil || len(p.Coordinates) != 2 {
		return nil
	}
	return &homepagemodel.GeoPoint{Latitude: p.Coordinates[1], Longitude: p.Coordinates[0]}
}

func documentFromSnapshot(snapshot homepagemodel.Snapshot) homepageDocument {
	return homepageDocument{
		ID:                   snapshot.ID,
		Version:              snapshot.Version,
		Title:                snapshot.Title,
		Subtitle:             snapshot.Subtitle,
		HomepageType:         snapshot.HomepageType,
		CanonicalEntityID:    snapshot.CanonicalEntityID,
		LookupAliases:        snapshot.LookupAliases,
		ObjectPageTemplate:   snapshot.ObjectPageTemplate,
		Status:               string(snapshot.Status),
		SourceType:           snapshot.SourceType,
		SourceOwner:          snapshot.SourceOwner,
		SourceEntityRef:      snapshot.SourceEntityRef,
		SourceReleaseID:      snapshot.SourceReleaseID,
		ClaimStatus:          snapshot.ClaimStatus,
		CategoryTags:         snapshot.CategoryTags,
		CoverURL:             snapshot.CoverURL,
		Address:              snapshot.Address,
		City:                 snapshot.City,
		Location:             geoJSONFromGeoPoint(snapshot.Location),
		OwnerUserID:          snapshot.OwnerUserID,
		OwnerPersonaID:       snapshot.OwnerPersonaID,
		Verified:             snapshot.Verified,
		EstablishedYear:      snapshot.EstablishedYear,
		IntroductionMarkdown: snapshot.IntroductionMarkdown,
		IntroductionAssets:   snapshot.IntroductionAssets,
		StructuredFacts:      snapshot.StructuredFacts,
		PrimarySource:        snapshot.PrimarySource,
		SourceURLs:           snapshot.SourceURLs,
		CreatedAt:            snapshot.CreatedAt.UTC(),
		UpdatedAt:            snapshot.UpdatedAt.UTC(),
		PublishedAt:          snapshot.PublishedAt,
		OfflineAt:            snapshot.OfflineAt,
	}
}

func (d homepageDocument) snapshot() homepagemodel.Snapshot {
	return homepagemodel.Snapshot{
		ID:                   d.ID,
		Version:              d.Version,
		Title:                d.Title,
		Subtitle:             d.Subtitle,
		HomepageType:         d.HomepageType,
		CanonicalEntityID:    d.CanonicalEntityID,
		LookupAliases:        d.LookupAliases,
		ObjectPageTemplate:   d.ObjectPageTemplate,
		Status:               homepagemodel.Status(d.Status),
		SourceType:           d.SourceType,
		SourceOwner:          d.SourceOwner,
		SourceEntityRef:      d.SourceEntityRef,
		SourceReleaseID:      d.SourceReleaseID,
		ClaimStatus:          d.ClaimStatus,
		CategoryTags:         d.CategoryTags,
		CoverURL:             d.CoverURL,
		Address:              d.Address,
		City:                 d.City,
		Location:             d.Location.geoPoint(),
		OwnerUserID:          d.OwnerUserID,
		OwnerPersonaID:       d.OwnerPersonaID,
		Verified:             d.Verified,
		EstablishedYear:      d.EstablishedYear,
		IntroductionMarkdown: d.IntroductionMarkdown,
		IntroductionAssets:   d.IntroductionAssets,
		StructuredFacts:      d.StructuredFacts,
		PrimarySource:        d.PrimarySource,
		SourceURLs:           d.SourceURLs,
		CreatedAt:            d.CreatedAt,
		UpdatedAt:            d.UpdatedAt,
		PublishedAt:          d.PublishedAt,
		OfflineAt:            d.OfflineAt,
	}
}

func (d homepageDocument) aggregate() (*homepagemodel.Homepage, error) {
	return homepagemodel.Restore(d.snapshot())
}

type homepageDetailDocument struct {
	ID               string                          `bson:"_id"`
	AverageRating    *float64                        `bson:"averageRating,omitempty"`
	RatingCount      int                             `bson:"ratingCount"`
	ReviewSummary    *homepagemodel.ReviewSummary    `bson:"reviewSummary,omitempty"`
	ContentPreview   []homepagemodel.ContentPreview  `bson:"contentPreview,omitempty"`
	QuestionPreview  []homepagemodel.QuestionPreview `bson:"questionPreview,omitempty"`
	RelatedGroups    []homepagemodel.RelatedGroup    `bson:"relatedGroups,omitempty"`
	RelationEdges    [][]byte                        `bson:"relationEdges,omitempty"`
	AssistantContext []byte                          `bson:"assistantContext,omitempty"`
	UpdatedAt        time.Time                       `bson:"updatedAt"`
}

func (d homepageDetailDocument) projection() homepageports.DetailProjection {
	return homepageports.DetailProjection{
		HomepageID:       d.ID,
		AverageRating:    d.AverageRating,
		RatingCount:      d.RatingCount,
		ReviewSummary:    d.ReviewSummary,
		ContentPreview:   append([]homepagemodel.ContentPreview{}, d.ContentPreview...),
		QuestionPreview:  append([]homepagemodel.QuestionPreview{}, d.QuestionPreview...),
		RelatedGroups:    append([]homepagemodel.RelatedGroup{}, d.RelatedGroups...),
		RelationEdges:    bytesToRawMessages(d.RelationEdges),
		AssistantContext: append(json.RawMessage(nil), d.AssistantContext...),
		UpdatedAt:        d.UpdatedAt,
	}
}

func (s *MongoHomepageStore) LoadDetailProjection(
	ctx context.Context,
	homepageID string,
) (homepageports.DetailProjection, bool, error) {
	var document homepageDetailDocument
	err := s.details.FindOne(ctx, bson.M{"_id": strings.TrimSpace(homepageID)}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return homepageports.DetailProjection{}, false, nil
	}
	if err != nil {
		return homepageports.DetailProjection{}, false, err
	}
	return document.projection(), true, nil
}

func (s *MongoHomepageStore) UpsertReviewSummary(
	ctx context.Context,
	homepageID string,
	averageRating *float64,
	ratingCount int,
	highlightTags []string,
	updatedAt time.Time,
) error {
	average := cloneFloat64(averageRating)
	summary := &homepagemodel.ReviewSummary{
		AverageRating: cloneFloat64(averageRating),
		RatingCount:   ratingCount,
		HighlightTags: append([]string(nil), highlightTags...),
	}
	_, err := s.details.UpdateOne(
		ctx,
		bson.M{"_id": strings.TrimSpace(homepageID)},
		bson.M{"$set": bson.M{
			"averageRating": average,
			"ratingCount":   ratingCount,
			"reviewSummary": summary,
			"updatedAt":     updatedAt.UTC(),
		}},
		options.UpdateOne().SetUpsert(true),
	)
	return err
}

type receiptDocument struct {
	ID               string           `bson:"_id"`
	ActorID          string           `bson:"actorId"`
	IdempotencyKey   string           `bson:"idempotencyKey"`
	AggregateID      string           `bson:"aggregateId"`
	AggregateVersion int64            `bson:"aggregateVersion"`
	CommandName      string           `bson:"commandName"`
	CommandDigest    string           `bson:"commandDigest"`
	Result           homepageDocument `bson:"result"`
	CreatedAt        time.Time        `bson:"createdAt"`
	ExpiresAt        time.Time        `bson:"expiresAt"`
}

type outboxDocument struct {
	ID               string    `bson:"_id"`
	EventType        string    `bson:"eventType"`
	AggregateID      string    `bson:"aggregateId"`
	AggregateVersion int64     `bson:"aggregateVersion"`
	Payload          []byte    `bson:"payload"`
	OccurredAt       time.Time `bson:"occurredAt"`
}

func (s *MongoHomepageStore) Load(
	ctx context.Context,
	homepageID string,
) (*homepagemodel.Homepage, bool, error) {
	var document homepageDocument
	err := s.homepages.FindOne(ctx, bson.M{"_id": strings.TrimSpace(homepageID)}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, err
	}
	aggregate, err := document.aggregate()
	return aggregate, err == nil, err
}

func (s *MongoHomepageStore) FindByCanonical(
	ctx context.Context,
	canonicalEntityID string,
) (*homepagemodel.Homepage, bool, error) {
	return s.findAggregate(ctx, bson.M{"canonicalEntityId": strings.TrimSpace(canonicalEntityID)})
}

func (s *MongoHomepageStore) FindBySource(
	ctx context.Context,
	sourceOwner string,
	sourceEntityRef string,
) (*homepagemodel.Homepage, bool, error) {
	return s.findAggregate(ctx, bson.M{
		"sourceOwner":     strings.TrimSpace(sourceOwner),
		"sourceEntityRef": strings.TrimSpace(sourceEntityRef),
	})
}

func (s *MongoHomepageStore) findAggregate(
	ctx context.Context,
	filter bson.M,
) (*homepagemodel.Homepage, bool, error) {
	var document homepageDocument
	err := s.homepages.FindOne(ctx, filter).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, err
	}
	aggregate, err := document.aggregate()
	return aggregate, err == nil, err
}

func (s *MongoHomepageStore) FindExact(
	ctx context.Context,
	lookup homepageports.ExactLookup,
) (homepagemodel.Snapshot, bool, error) {
	filters := bson.A{}
	if value := strings.TrimSpace(lookup.ID); value != "" {
		filters = append(filters, bson.M{"_id": value})
	}
	if value := strings.TrimSpace(lookup.CanonicalEntityID); value != "" {
		filters = append(filters, bson.M{"canonicalEntityId": value})
	}
	if value := homepagemodel.NormalizeLookupAlias(lookup.LookupAlias); value != "" {
		filters = append(filters, bson.M{"lookupAliases": value})
	}
	if strings.TrimSpace(lookup.SourceOwner) != "" && strings.TrimSpace(lookup.SourceEntityRef) != "" {
		filters = append(filters, bson.M{
			"sourceOwner":     strings.TrimSpace(lookup.SourceOwner),
			"sourceEntityRef": strings.TrimSpace(lookup.SourceEntityRef),
		})
	}
	if len(filters) == 0 {
		return homepagemodel.Snapshot{}, false, nil
	}
	var document homepageDocument
	err := s.homepages.FindOne(ctx, bson.M{"$or": filters}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return homepagemodel.Snapshot{}, false, nil
	}
	if err != nil {
		return homepagemodel.Snapshot{}, false, err
	}
	return document.snapshot(), true, nil
}

func (s *MongoHomepageStore) Search(
	ctx context.Context,
	query homepageports.SearchQuery,
) (homepageports.Page, error) {
	filter := bson.M{}
	if value := strings.TrimSpace(query.Query); value != "" {
		filter["$text"] = bson.M{"$search": value}
	}
	if value := strings.TrimSpace(query.HomepageType); value != "" {
		filter["homepageType"] = value
	}
	if value := strings.TrimSpace(query.City); value != "" {
		filter["city"] = value
	}
	if value := strings.TrimSpace(query.Status); value != "" {
		filter["status"] = value
	} else {
		filter["status"] = string(homepagemodel.StatusPublished)
	}
	return s.findPage(ctx, filter, query.Cursor, query.Limit)
}

func (s *MongoHomepageStore) ListBySourceOwner(
	ctx context.Context,
	sourceOwner string,
	cursor string,
	limit int,
) (homepageports.Page, error) {
	return s.findPage(ctx, bson.M{"sourceOwner": strings.TrimSpace(sourceOwner)}, cursor, limit)
}

func (s *MongoHomepageStore) findPage(
	ctx context.Context,
	filter bson.M,
	cursorValue string,
	limit int,
) (homepageports.Page, error) {
	limit = boundedLimit(limit, 20, 500)
	if strings.TrimSpace(cursorValue) != "" {
		updatedAt, id, err := decodePageCursor(cursorValue)
		if err != nil {
			return homepageports.Page{}, err
		}
		filter["$and"] = bson.A{bson.M{"$or": bson.A{
			bson.M{"updatedAt": bson.M{"$lt": updatedAt}},
			bson.M{"updatedAt": updatedAt, "_id": bson.M{"$lt": id}},
		}}}
	}
	cursor, err := s.homepages.Find(
		ctx,
		filter,
		options.Find().
			SetSort(bson.D{{Key: "updatedAt", Value: -1}, {Key: "_id", Value: -1}}).
			SetLimit(int64(limit+1)),
	)
	if err != nil {
		return homepageports.Page{}, err
	}
	defer func() { _ = cursor.Close(ctx) }()
	var documents []homepageDocument
	if err := cursor.All(ctx, &documents); err != nil {
		return homepageports.Page{}, err
	}
	return documentsPage(documents, limit), nil
}

func (s *MongoHomepageStore) Scan(
	ctx context.Context,
	cursorValue string,
	limit int,
) (homepageports.Page, error) {
	limit = boundedLimit(limit, 500, 2000)
	filter := bson.M{}
	if value := strings.TrimSpace(cursorValue); value != "" {
		filter["_id"] = bson.M{"$gt": value}
	}
	cursor, err := s.homepages.Find(
		ctx,
		filter,
		options.Find().SetSort(bson.D{{Key: "_id", Value: 1}}).SetLimit(int64(limit+1)),
	)
	if err != nil {
		return homepageports.Page{}, err
	}
	defer func() { _ = cursor.Close(ctx) }()
	var documents []homepageDocument
	if err := cursor.All(ctx, &documents); err != nil {
		return homepageports.Page{}, err
	}
	page := homepageports.Page{}
	for index, document := range documents {
		if index == limit {
			page.NextCursor = documents[limit-1].ID
			break
		}
		page.Items = append(page.Items, document.snapshot())
	}
	return page, nil
}

func (s *MongoHomepageStore) Count(ctx context.Context) (int64, error) {
	return s.homepages.CountDocuments(ctx, bson.M{})
}

func documentsPage(documents []homepageDocument, limit int) homepageports.Page {
	page := homepageports.Page{}
	for index, document := range documents {
		if index == limit {
			last := documents[limit-1]
			page.NextCursor = encodePageCursor(last.UpdatedAt, last.ID)
			break
		}
		page.Items = append(page.Items, document.snapshot())
	}
	return page
}

func (s *MongoHomepageStore) FindReceipt(
	ctx context.Context,
	actorID string,
	idempotencyKey string,
	commandName string,
	commandDigest string,
) (homepageports.CommitResult, bool, error) {
	receipt, found, err := s.findReceipt(ctx, actorID, idempotencyKey)
	if err != nil || !found {
		return homepageports.CommitResult{}, found, err
	}
	if !receipt.ExpiresAt.After(time.Now().UTC()) {
		if _, err := s.receipts.DeleteOne(ctx, bson.M{"_id": receipt.ID}); err != nil {
			return homepageports.CommitResult{}, false, err
		}
		return homepageports.CommitResult{}, false, nil
	}
	if receipt.CommandName != commandName || receipt.CommandDigest != commandDigest {
		return homepageports.CommitResult{}, false, generated.AppErrorFromIdempotencyConflict(
			"idempotency key was reused with a different homepage command",
		)
	}
	aggregate, err := receipt.Result.aggregate()
	if err != nil {
		return homepageports.CommitResult{}, false, err
	}
	return homepageports.CommitResult{Aggregate: aggregate, Replayed: true}, true, nil
}

func (s *MongoHomepageStore) findReceipt(
	ctx context.Context,
	actorID string,
	idempotencyKey string,
) (receiptDocument, bool, error) {
	var receipt receiptDocument
	err := s.receipts.FindOne(ctx, bson.M{"_id": receiptID(actorID, idempotencyKey)}).Decode(&receipt)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return receiptDocument{}, false, nil
	}
	return receipt, err == nil, err
}

func (s *MongoHomepageStore) RecordNoopReceipt(
	ctx context.Context,
	noop homepageports.NoopReceipt,
) (homepageports.CommitResult, error) {
	if noop.Aggregate == nil {
		return homepageports.CommitResult{}, generated.AppErrorFromVersionConflict("homepage no-op receipt requires aggregate")
	}
	if replayed, found, err := s.FindReceipt(
		ctx, noop.ActorID, noop.IdempotencyKey, noop.CommandName, noop.CommandDigest,
	); err != nil || found {
		return replayed, err
	}
	record := documentFromSnapshot(noop.Aggregate.Snapshot())
	_, err := s.receipts.InsertOne(ctx, receiptDocument{
		ID:               receiptID(noop.ActorID, noop.IdempotencyKey),
		ActorID:          strings.TrimSpace(noop.ActorID),
		IdempotencyKey:   strings.TrimSpace(noop.IdempotencyKey),
		AggregateID:      record.ID,
		AggregateVersion: record.Version,
		CommandName:      noop.CommandName,
		CommandDigest:    noop.CommandDigest,
		Result:           record,
		CreatedAt:        time.Now().UTC(),
		ExpiresAt:        normalizedExpiry(noop.ReceiptExpiresAt),
	})
	if err != nil {
		if mongo.IsDuplicateKeyError(err) {
			replayed, found, replayErr := s.FindReceipt(
				ctx, noop.ActorID, noop.IdempotencyKey, noop.CommandName, noop.CommandDigest,
			)
			if replayErr != nil {
				return homepageports.CommitResult{}, replayErr
			}
			if found {
				return replayed, nil
			}
		}
		return homepageports.CommitResult{}, err
	}
	aggregate, err := record.aggregate()
	return homepageports.CommitResult{Aggregate: aggregate}, err
}

func (s *MongoHomepageStore) Commit(
	ctx context.Context,
	commit homepageports.Commit,
) (homepageports.CommitResult, error) {
	if err := validateCommit(commit); err != nil {
		return homepageports.CommitResult{}, err
	}
	if !s.supportsTxn {
		return s.commitBody(ctx, commit)
	}
	session, err := s.homepages.Database().Client().StartSession()
	if err != nil {
		return homepageports.CommitResult{}, err
	}
	defer session.EndSession(ctx)
	var result homepageports.CommitResult
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		committed, commitErr := s.commitBody(txCtx, commit)
		result = committed
		return nil, commitErr
	})
	if err != nil {
		replayed, found, receiptErr := s.FindReceipt(
			ctx, commit.ActorID, commit.IdempotencyKey, commit.CommandName, commit.CommandDigest,
		)
		if receiptErr != nil {
			return homepageports.CommitResult{}, receiptErr
		}
		if found {
			return replayed, nil
		}
		return homepageports.CommitResult{}, err
	}
	return result, nil
}

// commitBody 在事务模式下原子提交；alpha 单节点降级沿用 Review packet 的固定顺序，
// state CAS 仍原子，命令可通过 actor-scoped receipt 重放收敛。
func (s *MongoHomepageStore) commitBody(
	ctx context.Context,
	commit homepageports.Commit,
) (homepageports.CommitResult, error) {
	if replayed, found, err := s.FindReceipt(
		ctx, commit.ActorID, commit.IdempotencyKey, commit.CommandName, commit.CommandDigest,
	); err != nil || found {
		return replayed, err
	}
	record := documentFromSnapshot(commit.Aggregate.Snapshot())
	if commit.ExpectedVersion == 0 {
		if _, err := s.homepages.InsertOne(ctx, record); err != nil {
			if mongo.IsDuplicateKeyError(err) {
				return homepageports.CommitResult{}, generated.AppErrorFromVersionConflict(
					"homepage canonical or source identity already exists",
				)
			}
			return homepageports.CommitResult{}, err
		}
	} else {
		result, err := s.homepages.ReplaceOne(
			ctx,
			bson.M{"_id": record.ID, "version": commit.ExpectedVersion},
			record,
		)
		if err != nil {
			if mongo.IsDuplicateKeyError(err) {
				return homepageports.CommitResult{}, generated.AppErrorFromVersionConflict(
					"homepage canonical or source identity already exists",
				)
			}
			return homepageports.CommitResult{}, err
		}
		if result.MatchedCount != 1 {
			return homepageports.CommitResult{}, generated.AppErrorFromVersionConflict(
				"homepage version changed before commit",
			)
		}
	}
	if _, err := s.outbox.InsertOne(ctx, outboxDocument{
		ID:               commit.Event.EventID,
		EventType:        commit.Event.EventType,
		AggregateID:      commit.Event.AggregateID,
		AggregateVersion: commit.Event.AggregateVersion,
		Payload:          append([]byte(nil), commit.Event.Payload...),
		OccurredAt:       commit.Event.OccurredAt.UTC(),
	}); err != nil {
		return homepageports.CommitResult{}, err
	}
	if _, err := s.receipts.InsertOne(ctx, receiptDocument{
		ID:               receiptID(commit.ActorID, commit.IdempotencyKey),
		ActorID:          strings.TrimSpace(commit.ActorID),
		IdempotencyKey:   strings.TrimSpace(commit.IdempotencyKey),
		AggregateID:      record.ID,
		AggregateVersion: record.Version,
		CommandName:      commit.CommandName,
		CommandDigest:    commit.CommandDigest,
		Result:           record,
		CreatedAt:        time.Now().UTC(),
		ExpiresAt:        normalizedExpiry(commit.ReceiptExpiresAt),
	}); err != nil {
		return homepageports.CommitResult{}, err
	}
	aggregate, err := record.aggregate()
	return homepageports.CommitResult{Aggregate: aggregate}, err
}

func validateCommit(commit homepageports.Commit) error {
	if commit.Aggregate == nil || commit.ExpectedVersion < 0 {
		return generated.AppErrorFromVersionConflict("homepage commit is incomplete")
	}
	if strings.TrimSpace(commit.ActorID) == "" || strings.TrimSpace(commit.IdempotencyKey) == "" ||
		strings.TrimSpace(commit.CommandName) == "" || strings.TrimSpace(commit.CommandDigest) == "" {
		return generated.AppErrorFromIdempotencyConflict("homepage command receipt is incomplete")
	}
	if commit.Aggregate.Version() != commit.ExpectedVersion+1 {
		return generated.AppErrorFromVersionConflict("homepage aggregate version does not follow expected version")
	}
	event := commit.Event
	if strings.TrimSpace(event.EventID) == "" || strings.TrimSpace(event.EventType) == "" ||
		event.AggregateID != commit.Aggregate.ID() ||
		event.AggregateVersion != commit.Aggregate.Version() ||
		event.OccurredAt.IsZero() {
		return generated.AppErrorFromVersionConflict("homepage outbox fact does not match aggregate commit")
	}
	return nil
}

type followerDocument struct {
	HomepageID    string    `bson:"homepageId"`
	PersonaID     string    `bson:"personaId"`
	Following     bool      `bson:"following"`
	SourceVersion int64     `bson:"sourceVersion"`
	UpdatedAt     time.Time `bson:"updatedAt"`
}

func (s *MongoHomepageStore) UpsertFollowerState(
	ctx context.Context,
	homepageID string,
	personaID string,
	following bool,
	sourceVersion int64,
	updatedAt time.Time,
) error {
	if strings.TrimSpace(homepageID) == "" || strings.TrimSpace(personaID) == "" {
		return nil
	}
	_, err := s.followers.UpdateOne(
		ctx,
		bson.M{
			"homepageId": strings.TrimSpace(homepageID),
			"personaId":  strings.TrimSpace(personaID),
			"$or": bson.A{
				bson.M{"sourceVersion": bson.M{"$lt": sourceVersion}},
				bson.M{"sourceVersion": bson.M{"$exists": false}},
			},
		},
		bson.M{"$set": followerDocument{
			HomepageID:    strings.TrimSpace(homepageID),
			PersonaID:     strings.TrimSpace(personaID),
			Following:     following,
			SourceVersion: sourceVersion,
			UpdatedAt:     updatedAt.UTC(),
		}},
		options.UpdateOne().SetUpsert(true),
	)
	if mongo.IsDuplicateKeyError(err) {
		// 旧/重复事件命中 identity 唯一键即安全忽略。
		return nil
	}
	return err
}

func (s *MongoHomepageStore) ResolveFollowerView(
	ctx context.Context,
	homepageID string,
	viewerPersonaID string,
) (homepageports.FollowerView, error) {
	homepageID = strings.TrimSpace(homepageID)
	count, err := s.followers.CountDocuments(ctx, bson.M{
		"homepageId": homepageID,
		"following":  true,
	})
	if err != nil {
		return homepageports.FollowerView{}, err
	}
	view := homepageports.FollowerView{Count: int(count)}
	if viewer := strings.TrimSpace(viewerPersonaID); viewer != "" {
		var document followerDocument
		err := s.followers.FindOne(ctx, bson.M{
			"homepageId": homepageID,
			"personaId":  viewer,
			"following":  true,
		}).Decode(&document)
		if err != nil && !errors.Is(err, mongo.ErrNoDocuments) {
			return homepageports.FollowerView{}, err
		}
		view.ViewerFollows = err == nil
	}
	return view, nil
}

func (s *MongoHomepageStore) ReadAfter(
	ctx context.Context,
	checkpoint string,
	limit int,
) ([]homepageports.OutboxEvent, error) {
	limit = boundedLimit(limit, 100, 1000)
	filter := bson.M{}
	if value := strings.TrimSpace(checkpoint); value != "" {
		filter["_id"] = bson.M{"$gt": value}
	}
	cursor, err := s.outbox.Find(
		ctx,
		filter,
		options.Find().SetSort(bson.D{{Key: "_id", Value: 1}}).SetLimit(int64(limit)),
	)
	if err != nil {
		return nil, err
	}
	defer func() { _ = cursor.Close(ctx) }()
	var documents []outboxDocument
	if err := cursor.All(ctx, &documents); err != nil {
		return nil, err
	}
	events := make([]homepageports.OutboxEvent, 0, len(documents))
	for _, document := range documents {
		events = append(events, homepageports.OutboxEvent{
			EventID:          document.ID,
			EventType:        document.EventType,
			AggregateID:      document.AggregateID,
			AggregateVersion: document.AggregateVersion,
			Payload:          append([]byte(nil), document.Payload...),
			OccurredAt:       document.OccurredAt,
		})
	}
	return events, nil
}

type checkpointDocument struct {
	ID         string    `bson:"_id"`
	Checkpoint string    `bson:"checkpoint"`
	UpdatedAt  time.Time `bson:"updatedAt"`
}

func (s *MongoHomepageStore) LoadCheckpoint(ctx context.Context, consumer string) (string, error) {
	var document checkpointDocument
	err := s.checkpoints.FindOne(ctx, bson.M{"_id": strings.TrimSpace(consumer)}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return "", nil
	}
	return document.Checkpoint, err
}

func (s *MongoHomepageStore) SaveCheckpoint(
	ctx context.Context,
	consumer string,
	checkpoint string,
) error {
	_, err := s.checkpoints.UpdateOne(
		ctx,
		bson.M{"_id": strings.TrimSpace(consumer)},
		bson.M{"$set": bson.M{
			"checkpoint": strings.TrimSpace(checkpoint),
			"updatedAt":  time.Now().UTC(),
		}},
		options.UpdateOne().SetUpsert(true),
	)
	return err
}

func receiptID(actorID, idempotencyKey string) string {
	sum := sha256.Sum256([]byte(strings.TrimSpace(actorID) + "\x00" + strings.TrimSpace(idempotencyKey)))
	return "hp-receipt-" + hex.EncodeToString(sum[:16])
}

func normalizedExpiry(value time.Time) time.Time {
	if value.IsZero() {
		return time.Now().UTC().Add(24 * time.Hour)
	}
	return value.UTC()
}

func boundedLimit(value, fallback, maximum int) int {
	if value <= 0 {
		return fallback
	}
	if value > maximum {
		return maximum
	}
	return value
}

func encodePageCursor(updatedAt time.Time, id string) string {
	return strconv.FormatInt(updatedAt.UTC().UnixNano(), 10) + "|" + id
}

func decodePageCursor(value string) (time.Time, string, error) {
	parts := strings.SplitN(strings.TrimSpace(value), "|", 2)
	if len(parts) != 2 {
		return time.Time{}, "", generated.AppErrorFromInvalidArgument("homepage cursor is malformed")
	}
	nanos, err := strconv.ParseInt(parts[0], 10, 64)
	if err != nil {
		return time.Time{}, "", generated.AppErrorFromInvalidArgument("homepage cursor timestamp is malformed")
	}
	return time.Unix(0, nanos).UTC(), parts[1], nil
}

func rawMessagesToBytes(values []json.RawMessage) [][]byte {
	result := make([][]byte, 0, len(values))
	for _, value := range values {
		result = append(result, append([]byte(nil), value...))
	}
	return result
}

func bytesToRawMessages(values [][]byte) []json.RawMessage {
	result := make([]json.RawMessage, 0, len(values))
	for _, value := range values {
		result = append(result, append(json.RawMessage(nil), value...))
	}
	return result
}

func cloneFloat64(value *float64) *float64 {
	if value == nil {
		return nil
	}
	result := *value
	return &result
}
