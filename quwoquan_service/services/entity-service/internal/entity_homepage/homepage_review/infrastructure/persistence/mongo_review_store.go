// Package persistence 实现 HomepageReview 对象专属 Mongo Store：
// state CAS + actor-scoped 幂等 receipt + 同事务 outbox。
package persistence

import (
	"context"
	"errors"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/entity-service/generated/entity_homepage/homepage"
	reviewmodel "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_review/domain/model"
	reviewports "quwoquan_service/services/entity-service/internal/entity_homepage/homepage_review/domain/ports"
)

const (
	reviewCollection           = "homepage_reviews"
	reviewReceiptsCollection   = "homepage_review_command_receipts"
	reviewOutboxCollection     = "homepage_review_outbox"
	reviewCheckpointCollection = "homepage_review_projection_checkpoints"
)

type MongoReviewStore struct {
	reviews     *mongo.Collection
	receipts    *mongo.Collection
	outbox      *mongo.Collection
	checkpoints *mongo.Collection
	supportsTxn bool
}

func NewMongoReviewStore(db *mongo.Database, supportsTransactions bool) *MongoReviewStore {
	return &MongoReviewStore{
		reviews:     db.Collection(reviewCollection),
		receipts:    db.Collection(reviewReceiptsCollection),
		outbox:      db.Collection(reviewOutboxCollection),
		checkpoints: db.Collection(reviewCheckpointCollection),
		supportsTxn: supportsTransactions,
	}
}

var (
	_ reviewports.AggregateStore            = (*MongoReviewStore)(nil)
	_ reviewports.PageReader                = (*MongoReviewStore)(nil)
	_ reviewports.OutboxReader              = (*MongoReviewStore)(nil)
	_ reviewports.ProjectionCheckpointStore = (*MongoReviewStore)(nil)
)

// EnsureIndexes 按 services/entity-service/contracts/entity_homepage/homepage_review/storage.yaml 建索引。
func (s *MongoReviewStore) EnsureIndexes(ctx context.Context) error {
	if _, err := s.reviews.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "homepageId", Value: 1}, {Key: "status", Value: 1}, {Key: "createdAt", Value: -1}},
			Options: options.Index().SetName("idx_homepage_review_homepage_status"),
		},
		{
			Keys:    bson.D{{Key: "authorPersonaId", Value: 1}, {Key: "homepageId", Value: 1}},
			Options: options.Index().SetName("idx_homepage_review_author_homepage").SetUnique(true),
		},
		{
			Keys:    bson.D{{Key: "_id", Value: 1}, {Key: "version", Value: 1}},
			Options: options.Index().SetName("idx_homepage_review_version").SetUnique(true),
		},
	}); err != nil {
		return err
	}
	if _, err := s.receipts.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "aggregateId", Value: 1}, {Key: "aggregateVersion", Value: -1}},
			Options: options.Index().SetName("idx_homepage_review_receipts_aggregate"),
		},
		{
			Keys:    bson.D{{Key: "expiresAt", Value: 1}},
			Options: options.Index().SetName("idx_homepage_review_receipts_expire").SetExpireAfterSeconds(0),
		},
	}); err != nil {
		return err
	}
	if _, err := s.outbox.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "occurredAt", Value: 1}, {Key: "_id", Value: 1}},
			Options: options.Index().SetName("idx_homepage_review_outbox_replay"),
		},
		{
			Keys:    bson.D{{Key: "aggregateId", Value: 1}, {Key: "aggregateVersion", Value: 1}},
			Options: options.Index().SetName("idx_homepage_review_outbox_aggregate_version").SetUnique(true),
		},
	}); err != nil {
		return err
	}
	return nil
}

type reviewDocument struct {
	ID                        string    `bson:"_id"`
	Version                   int64     `bson:"version"`
	HomepageID                string    `bson:"homepageId"`
	AuthorPersonaID           string    `bson:"authorPersonaId"`
	AuthorDisplayNameSnapshot string    `bson:"authorDisplayNameSnapshot,omitempty"`
	AuthorAvatarURLSnapshot   string    `bson:"authorAvatarUrlSnapshot,omitempty"`
	Rating                    int       `bson:"rating"`
	Body                      string    `bson:"body,omitempty"`
	TagRefs                   []string  `bson:"tagRefs,omitempty"`
	Status                    string    `bson:"status"`
	CreatedAt                 time.Time `bson:"createdAt"`
	UpdatedAt                 time.Time `bson:"updatedAt"`
}

func documentFromSnapshot(snapshot reviewmodel.Snapshot) reviewDocument {
	return reviewDocument{
		ID:                        snapshot.ID,
		Version:                   snapshot.Version,
		HomepageID:                snapshot.HomepageID,
		AuthorPersonaID:           snapshot.AuthorPersonaID,
		AuthorDisplayNameSnapshot: snapshot.AuthorDisplayNameSnapshot,
		AuthorAvatarURLSnapshot:   snapshot.AuthorAvatarURLSnapshot,
		Rating:                    snapshot.Rating,
		Body:                      snapshot.Body,
		TagRefs:                   snapshot.TagRefs,
		Status:                    string(snapshot.Status),
		CreatedAt:                 snapshot.CreatedAt.UTC(),
		UpdatedAt:                 snapshot.UpdatedAt.UTC(),
	}
}

func (d reviewDocument) snapshot() reviewmodel.Snapshot {
	return reviewmodel.Snapshot{
		ID:                        d.ID,
		Version:                   d.Version,
		HomepageID:                d.HomepageID,
		AuthorPersonaID:           d.AuthorPersonaID,
		AuthorDisplayNameSnapshot: d.AuthorDisplayNameSnapshot,
		AuthorAvatarURLSnapshot:   d.AuthorAvatarURLSnapshot,
		Rating:                    d.Rating,
		Body:                      d.Body,
		TagRefs:                   d.TagRefs,
		Status:                    reviewmodel.Status(d.Status),
		CreatedAt:                 d.CreatedAt,
		UpdatedAt:                 d.UpdatedAt,
	}
}

func (d reviewDocument) aggregate() (*reviewmodel.HomepageReview, error) {
	return reviewmodel.Restore(d.snapshot())
}

type reviewReceiptDocument struct {
	ID               string         `bson:"_id"`
	AggregateID      string         `bson:"aggregateId"`
	AggregateVersion int64          `bson:"aggregateVersion"`
	CommandName      string         `bson:"commandName"`
	CommandDigest    string         `bson:"commandDigest"`
	Result           reviewDocument `bson:"result"`
	CreatedAt        time.Time      `bson:"createdAt"`
	ExpiresAt        time.Time      `bson:"expiresAt"`
}

type reviewOutboxDocument struct {
	ID               string    `bson:"_id"`
	EventType        string    `bson:"eventType"`
	AggregateID      string    `bson:"aggregateId"`
	AggregateVersion int64     `bson:"aggregateVersion"`
	Payload          []byte    `bson:"payload"`
	OccurredAt       time.Time `bson:"occurredAt"`
}

func (s *MongoReviewStore) Load(
	ctx context.Context,
	reviewID string,
) (*reviewmodel.HomepageReview, bool, error) {
	var document reviewDocument
	err := s.reviews.FindOne(
		ctx,
		bson.M{"_id": strings.TrimSpace(reviewID)},
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, err
	}
	aggregate, err := document.aggregate()
	if err != nil {
		return nil, false, err
	}
	return aggregate, true, nil
}

func (s *MongoReviewStore) FindByAuthor(
	ctx context.Context,
	homepageID string,
	authorPersonaID string,
) (*reviewmodel.HomepageReview, bool, error) {
	var document reviewDocument
	err := s.reviews.FindOne(ctx, bson.M{
		"homepageId":      strings.TrimSpace(homepageID),
		"authorPersonaId": strings.TrimSpace(authorPersonaID),
	}).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return nil, false, nil
	}
	if err != nil {
		return nil, false, err
	}
	aggregate, err := document.aggregate()
	if err != nil {
		return nil, false, err
	}
	return aggregate, true, nil
}

func (s *MongoReviewStore) findReceipt(
	ctx context.Context,
	idempotencyKey string,
) (reviewReceiptDocument, bool, error) {
	var receipt reviewReceiptDocument
	err := s.receipts.FindOne(
		ctx,
		bson.M{"_id": strings.TrimSpace(idempotencyKey)},
	).Decode(&receipt)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return reviewReceiptDocument{}, false, nil
	}
	if err != nil {
		return reviewReceiptDocument{}, false, err
	}
	return receipt, true, nil
}

func (s *MongoReviewStore) FindReceipt(
	ctx context.Context,
	idempotencyKey string,
	commandName string,
	commandDigest string,
) (reviewports.CommitResult, bool, error) {
	receipt, found, err := s.findReceipt(ctx, idempotencyKey)
	if err != nil || !found {
		return reviewports.CommitResult{}, found, err
	}
	if !receipt.ExpiresAt.After(time.Now().UTC()) {
		if _, err := s.receipts.DeleteOne(ctx, bson.M{"_id": receipt.ID}); err != nil {
			return reviewports.CommitResult{}, false, err
		}
		return reviewports.CommitResult{}, false, nil
	}
	if receipt.CommandName != commandName || receipt.CommandDigest != commandDigest {
		return reviewports.CommitResult{}, false,
			generated.AppErrorFromIdempotencyConflict(
				"idempotency key was reused with a different homepage review command",
			)
	}
	aggregate, err := receipt.Result.aggregate()
	if err != nil {
		return reviewports.CommitResult{}, false, err
	}
	return reviewports.CommitResult{Aggregate: aggregate, Replayed: true}, true, nil
}

func (s *MongoReviewStore) RecordNoopReceipt(
	ctx context.Context,
	noop reviewports.NoopReceipt,
) (reviewports.CommitResult, error) {
	if noop.Aggregate == nil ||
		strings.TrimSpace(noop.IdempotencyKey) == "" ||
		strings.TrimSpace(noop.CommandName) == "" ||
		strings.TrimSpace(noop.CommandDigest) == "" {
		return reviewports.CommitResult{},
			generated.AppErrorFromVersionConflict(
				"homepage review no-op receipt is incomplete",
			)
	}
	if replayed, found, err := s.FindReceipt(
		ctx,
		noop.IdempotencyKey,
		noop.CommandName,
		noop.CommandDigest,
	); err != nil || found {
		return replayed, err
	}
	record := documentFromSnapshot(noop.Aggregate.Snapshot())
	expiresAt := noop.ReceiptExpiresAt.UTC()
	if expiresAt.IsZero() {
		expiresAt = time.Now().UTC().Add(24 * time.Hour)
	}
	_, err := s.receipts.InsertOne(ctx, reviewReceiptDocument{
		ID:               strings.TrimSpace(noop.IdempotencyKey),
		AggregateID:      record.ID,
		AggregateVersion: record.Version,
		CommandName:      strings.TrimSpace(noop.CommandName),
		CommandDigest:    strings.TrimSpace(noop.CommandDigest),
		Result:           record,
		CreatedAt:        time.Now().UTC(),
		ExpiresAt:        expiresAt,
	})
	if err != nil {
		if mongo.IsDuplicateKeyError(err) {
			replayed, found, replayErr := s.FindReceipt(
				ctx,
				noop.IdempotencyKey,
				noop.CommandName,
				noop.CommandDigest,
			)
			if replayErr != nil {
				return reviewports.CommitResult{}, replayErr
			}
			if found {
				return replayed, nil
			}
		}
		return reviewports.CommitResult{}, err
	}
	aggregate, err := record.aggregate()
	if err != nil {
		return reviewports.CommitResult{}, err
	}
	return reviewports.CommitResult{Aggregate: aggregate}, nil
}

func validateCommit(commit reviewports.Commit) error {
	if commit.Aggregate == nil || strings.TrimSpace(commit.Aggregate.ID()) == "" {
		return generated.AppErrorFromVersionConflict("homepage review commit requires aggregate")
	}
	if commit.ExpectedVersion < 0 {
		return generated.AppErrorFromVersionConflict("homepage review expected version must not be negative")
	}
	if strings.TrimSpace(commit.IdempotencyKey) == "" {
		return generated.AppErrorFromIdempotencyConflict(
			"homepage review command requires idempotency key",
		)
	}
	if strings.TrimSpace(commit.CommandName) == "" || strings.TrimSpace(commit.CommandDigest) == "" {
		return generated.AppErrorFromIdempotencyConflict(
			"homepage review command requires name and digest",
		)
	}
	if commit.Aggregate.Version() != commit.ExpectedVersion+1 {
		return generated.AppErrorFromVersionConflict(
			"homepage review aggregate version does not follow expected version",
		)
	}
	if len(commit.Events) == 0 {
		return generated.AppErrorFromVersionConflict(
			"homepage review aggregate commit requires an outbox fact",
		)
	}
	for _, event := range commit.Events {
		if strings.TrimSpace(event.EventID) == "" ||
			strings.TrimSpace(event.EventType) == "" ||
			event.AggregateID != commit.Aggregate.ID() ||
			event.AggregateVersion != commit.Aggregate.Version() ||
			event.OccurredAt.IsZero() {
			return generated.AppErrorFromVersionConflict(
				"homepage review outbox event does not match aggregate commit",
			)
		}
	}
	return nil
}

func (s *MongoReviewStore) Commit(
	ctx context.Context,
	commit reviewports.Commit,
) (reviewports.CommitResult, error) {
	if err := validateCommit(commit); err != nil {
		return reviewports.CommitResult{}, err
	}
	if !s.supportsTxn {
		return s.commitWithoutTransaction(ctx, commit)
	}
	session, err := s.reviews.Database().Client().StartSession()
	if err != nil {
		return reviewports.CommitResult{}, err
	}
	defer session.EndSession(ctx)

	var result reviewports.CommitResult
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		committed, txErr := s.commitBody(txCtx, commit)
		if txErr != nil {
			return nil, txErr
		}
		result = committed
		return nil, nil
	})
	if err != nil {
		replayed, found, receiptErr := s.FindReceipt(
			ctx,
			commit.IdempotencyKey,
			commit.CommandName,
			commit.CommandDigest,
		)
		if receiptErr != nil {
			return reviewports.CommitResult{}, receiptErr
		}
		if found {
			return replayed, nil
		}
		return reviewports.CommitResult{}, err
	}
	return result, nil
}

// commitWithoutTransaction 服务本地/单节点 Mongo（无副本集）时按固定顺序提交；
// state CAS 仍然原子，receipt/outbox 落盘失败由幂等重放收敛。
func (s *MongoReviewStore) commitWithoutTransaction(
	ctx context.Context,
	commit reviewports.Commit,
) (reviewports.CommitResult, error) {
	return s.commitBody(ctx, commit)
}

func (s *MongoReviewStore) commitBody(
	ctx context.Context,
	commit reviewports.Commit,
) (reviewports.CommitResult, error) {
	receipt, receiptFound, receiptErr := s.findReceipt(ctx, commit.IdempotencyKey)
	if receiptErr != nil {
		return reviewports.CommitResult{}, receiptErr
	}
	if receiptFound {
		if !receipt.ExpiresAt.After(time.Now().UTC()) {
			if _, err := s.receipts.DeleteOne(ctx, bson.M{"_id": receipt.ID}); err != nil {
				return reviewports.CommitResult{}, err
			}
		} else {
			if receipt.CommandName != commit.CommandName ||
				receipt.CommandDigest != commit.CommandDigest {
				return reviewports.CommitResult{}, generated.AppErrorFromIdempotencyConflict(
					"idempotency key was reused with a different homepage review command",
				)
			}
			replayed, err := receipt.Result.aggregate()
			if err != nil {
				return reviewports.CommitResult{}, err
			}
			return reviewports.CommitResult{Aggregate: replayed, Replayed: true}, nil
		}
	}

	record := documentFromSnapshot(commit.Aggregate.Snapshot())
	if commit.ExpectedVersion == 0 {
		if _, err := s.reviews.InsertOne(ctx, record); err != nil {
			if mongo.IsDuplicateKeyError(err) {
				return reviewports.CommitResult{}, generated.AppErrorFromVersionConflict(
					"homepage review already exists for this author",
				)
			}
			return reviewports.CommitResult{}, err
		}
	} else {
		replaceResult, err := s.reviews.ReplaceOne(
			ctx,
			bson.M{"_id": record.ID, "version": commit.ExpectedVersion},
			record,
		)
		if err != nil {
			return reviewports.CommitResult{}, err
		}
		if replaceResult.MatchedCount != 1 {
			return reviewports.CommitResult{}, generated.AppErrorFromVersionConflict(
				"homepage review version changed before commit",
			)
		}
	}

	for _, event := range commit.Events {
		if _, err := s.outbox.InsertOne(ctx, reviewOutboxDocument{
			ID:               event.EventID,
			EventType:        event.EventType,
			AggregateID:      event.AggregateID,
			AggregateVersion: event.AggregateVersion,
			Payload:          append([]byte(nil), event.Payload...),
			OccurredAt:       event.OccurredAt.UTC(),
		}); err != nil {
			return reviewports.CommitResult{}, err
		}
	}

	expiresAt := commit.ReceiptExpiresAt.UTC()
	if expiresAt.IsZero() {
		expiresAt = time.Now().UTC().Add(24 * time.Hour)
	}
	if _, err := s.receipts.InsertOne(ctx, reviewReceiptDocument{
		ID:               commit.IdempotencyKey,
		AggregateID:      record.ID,
		AggregateVersion: record.Version,
		CommandName:      commit.CommandName,
		CommandDigest:    commit.CommandDigest,
		Result:           record,
		CreatedAt:        time.Now().UTC(),
		ExpiresAt:        expiresAt,
	}); err != nil {
		return reviewports.CommitResult{}, err
	}
	aggregate, err := record.aggregate()
	if err != nil {
		return reviewports.CommitResult{}, err
	}
	return reviewports.CommitResult{Aggregate: aggregate}, nil
}

func (s *MongoReviewStore) ListByHomepage(
	ctx context.Context,
	homepageID string,
	request reviewports.PageRequest,
) (reviewports.Page, error) {
	limit := request.Limit
	if limit <= 0 {
		limit = 20
	}
	if limit > 100 {
		limit = 100
	}
	filter := bson.M{
		"homepageId": strings.TrimSpace(homepageID),
		"status":     string(reviewmodel.StatusActive),
	}
	if cursor := strings.TrimSpace(request.Cursor); cursor != "" {
		createdAt, id, err := decodeReviewCursor(cursor)
		if err != nil {
			return reviewports.Page{}, err
		}
		filter["$or"] = bson.A{
			bson.M{"createdAt": bson.M{"$lt": createdAt}},
			bson.M{"createdAt": createdAt, "_id": bson.M{"$lt": id}},
		}
	}
	findOptions := options.Find().
		SetSort(bson.D{{Key: "createdAt", Value: -1}, {Key: "_id", Value: -1}}).
		SetLimit(int64(limit + 1))
	cursor, err := s.reviews.Find(ctx, filter, findOptions)
	if err != nil {
		return reviewports.Page{}, err
	}
	defer func() { _ = cursor.Close(ctx) }()
	var documents []reviewDocument
	if err := cursor.All(ctx, &documents); err != nil {
		return reviewports.Page{}, err
	}
	page := reviewports.Page{}
	for index, document := range documents {
		if index == limit {
			last := documents[limit-1]
			page.NextCursor = encodeReviewCursor(last.CreatedAt, last.ID)
			break
		}
		page.Items = append(page.Items, document.snapshot())
	}
	return page, nil
}

func (s *MongoReviewStore) ReadAfter(
	ctx context.Context,
	checkpoint string,
	limit int,
) ([]reviewports.OutboxEvent, error) {
	if limit <= 0 {
		limit = 100
	}
	filter := bson.M{}
	if trimmed := strings.TrimSpace(checkpoint); trimmed != "" {
		filter["_id"] = bson.M{"$gt": trimmed}
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
	var documents []reviewOutboxDocument
	if err := cursor.All(ctx, &documents); err != nil {
		return nil, err
	}
	events := make([]reviewports.OutboxEvent, 0, len(documents))
	for _, document := range documents {
		events = append(events, reviewports.OutboxEvent{
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

type reviewCheckpointDocument struct {
	ID         string    `bson:"_id"`
	Checkpoint string    `bson:"checkpoint"`
	UpdatedAt  time.Time `bson:"updatedAt"`
}

func (s *MongoReviewStore) LoadCheckpoint(
	ctx context.Context,
	consumer string,
) (string, error) {
	var document reviewCheckpointDocument
	err := s.checkpoints.FindOne(
		ctx,
		bson.M{"_id": strings.TrimSpace(consumer)},
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return "", nil
	}
	if err != nil {
		return "", err
	}
	return document.Checkpoint, nil
}

func (s *MongoReviewStore) SaveCheckpoint(
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

// SummarizeByHomepage 对 active 评价做真实聚合：均分、计数与
// tagRefs 频次 TopN 亮点标签。无评价时返回空摘要（不伪造）。
func (s *MongoReviewStore) SummarizeByHomepage(
	ctx context.Context,
	homepageID string,
) (reviewports.Summary, error) {
	match := bson.M{
		"homepageId": strings.TrimSpace(homepageID),
		"status":     string(reviewmodel.StatusActive),
	}
	cursor, err := s.reviews.Aggregate(ctx, mongo.Pipeline{
		bson.D{{Key: "$match", Value: match}},
		bson.D{{Key: "$group", Value: bson.M{
			"_id":     nil,
			"count":   bson.M{"$sum": 1},
			"average": bson.M{"$avg": "$rating"},
		}}},
	})
	if err != nil {
		return reviewports.Summary{}, err
	}
	defer func() { _ = cursor.Close(ctx) }()
	var stats []struct {
		Count   int     `bson:"count"`
		Average float64 `bson:"average"`
	}
	if err := cursor.All(ctx, &stats); err != nil {
		return reviewports.Summary{}, err
	}
	summary := reviewports.Summary{HighlightTags: []string{}}
	if len(stats) == 0 || stats[0].Count == 0 {
		return summary, nil
	}
	average := stats[0].Average
	summary.AverageRating = &average
	summary.RatingCount = stats[0].Count

	tagCursor, err := s.reviews.Aggregate(ctx, mongo.Pipeline{
		bson.D{{Key: "$match", Value: match}},
		bson.D{{Key: "$unwind", Value: "$tagRefs"}},
		bson.D{{Key: "$group", Value: bson.M{
			"_id":   "$tagRefs",
			"count": bson.M{"$sum": 1},
		}}},
		bson.D{{Key: "$sort", Value: bson.D{
			{Key: "count", Value: -1},
			{Key: "_id", Value: 1},
		}}},
		bson.D{{Key: "$limit", Value: 3}},
	})
	if err != nil {
		return reviewports.Summary{}, err
	}
	defer func() { _ = tagCursor.Close(ctx) }()
	var tags []struct {
		Tag string `bson:"_id"`
	}
	if err := tagCursor.All(ctx, &tags); err != nil {
		return reviewports.Summary{}, err
	}
	for _, tag := range tags {
		if trimmed := strings.TrimSpace(tag.Tag); trimmed != "" {
			summary.HighlightTags = append(summary.HighlightTags, trimmed)
		}
	}
	return summary, nil
}

func encodeReviewCursor(createdAt time.Time, id string) string {
	return createdAt.UTC().Format(time.RFC3339Nano) + "|" + id
}

func decodeReviewCursor(cursor string) (time.Time, string, error) {
	parts := strings.SplitN(cursor, "|", 2)
	if len(parts) != 2 {
		return time.Time{}, "", generated.AppErrorFromInvalidArgument(
			"homepage review cursor is malformed",
		)
	}
	createdAt, err := time.Parse(time.RFC3339Nano, parts[0])
	if err != nil {
		return time.Time{}, "", generated.AppErrorFromInvalidArgument(
			"homepage review cursor timestamp is malformed",
		)
	}
	return createdAt.UTC(), parts[1], nil
}
