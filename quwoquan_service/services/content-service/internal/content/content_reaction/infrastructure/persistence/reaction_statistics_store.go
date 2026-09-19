package persistence

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"strconv"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	reactionapp "quwoquan_service/services/content-service/internal/content/content_reaction/application/reaction"
	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
	reactionports "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction/ports"
)

const (
	contentReactionStatisticsInboxCollection      = "content_reaction_statistics_inbox"
	contentReactionStatisticsMemberCollection     = "content_reaction_statistics_members"
	contentReactionStatisticsBucketCollection     = "content_reaction_statistics_buckets"
	contentReactionStatisticsRollupCollection     = "content_reaction_statistics_rollups"
	contentReactionStatisticsGenerationCollection = "content_reaction_statistics_reader_generation"
	DefaultReactionStatisticsBuckets              = 64
)

type reactionStatisticsInboxDocument struct {
	ID               string    `bson:"_id"`
	AggregateID      string    `bson:"aggregateId"`
	AggregateVersion int64     `bson:"aggregateVersion"`
	PayloadDigest    string    `bson:"payloadDigest"`
	PartitionID      int       `bson:"partitionId"`
	Checkpoint       int64     `bson:"checkpoint"`
	AppliedAt        time.Time `bson:"appliedAt"`
}

type reactionStatisticsMemberDocument struct {
	ID                  string    `bson:"_id"`
	ReactionID          string    `bson:"reactionId"`
	Dimension           string    `bson:"dimension"`
	OwnerKind           string    `bson:"ownerKind"`
	OwnerID             string    `bson:"ownerId"`
	ContributionKind    string    `bson:"contributionKind"`
	Bucket              int       `bson:"bucket"`
	LastAppliedVersion  int64     `bson:"lastAppliedVersion"`
	CurrentContribution int64     `bson:"currentContribution"`
	PayloadDigest       string    `bson:"payloadDigest"`
	SourceEventID       string    `bson:"sourceEventId"`
	UpdatedAt           time.Time `bson:"updatedAt"`
}

type reactionStatisticsBucketDocument struct {
	ID               string    `bson:"_id"`
	Generation       string    `bson:"generation"`
	Dimension        string    `bson:"dimension"`
	OwnerKind        string    `bson:"ownerKind"`
	OwnerID          string    `bson:"ownerId"`
	ContributionKind string    `bson:"contributionKind"`
	Bucket           int       `bson:"bucket"`
	Value            int64     `bson:"value"`
	MaxSourceVersion int64     `bson:"maxSourceVersion"`
	MaxCheckpoint    int64     `bson:"maxCheckpoint"`
	UpdatedAt        time.Time `bson:"updatedAt"`
}

type reactionStatisticsRollupDocument struct {
	ID               string    `bson:"_id"`
	Generation       string    `bson:"generation"`
	Dimension        string    `bson:"dimension"`
	OwnerKind        string    `bson:"ownerKind"`
	OwnerID          string    `bson:"ownerId"`
	StatsVersion     int64     `bson:"statsVersion"`
	LikeCount        int64     `bson:"likeCount"`
	DislikeCount     int64     `bson:"dislikeCount"`
	SourceCheckpoint string    `bson:"sourceCheckpoint"`
	AsOf             time.Time `bson:"asOf"`
	ExpiresAt        time.Time `bson:"expiresAt"`
}

type reactionStatisticsGenerationDocument struct {
	ID               string    `bson:"_id"`
	Generation       string    `bson:"generation"`
	SourceCheckpoint string    `bson:"sourceCheckpoint"`
	PublishedAt      time.Time `bson:"publishedAt"`
}

// MongoReactionStatisticsStore owns the ContentReaction current-contribution
// ledger. It is intentionally separate from the aggregate store fields so
// repair and reader generations cannot become command authority.
type MongoReactionStatisticsStore struct {
	db          *mongo.Database
	inbox       *mongo.Collection
	members     *mongo.Collection
	buckets     *mongo.Collection
	rollups     *mongo.Collection
	generations *mongo.Collection
	aggregates  *mongo.Collection
	now         func() time.Time
	bucketCount int
}

func NewMongoReactionStatisticsStore(db *mongo.Database) *MongoReactionStatisticsStore {
	return &MongoReactionStatisticsStore{
		db:          db,
		inbox:       db.Collection(contentReactionStatisticsInboxCollection),
		members:     db.Collection(contentReactionStatisticsMemberCollection),
		buckets:     db.Collection(contentReactionStatisticsBucketCollection),
		rollups:     db.Collection(contentReactionStatisticsRollupCollection),
		generations: db.Collection(contentReactionStatisticsGenerationCollection),
		aggregates:  db.Collection(contentReactionAggregateCollection),
		now:         func() time.Time { return time.Now().UTC() },
		bucketCount: DefaultReactionStatisticsBuckets,
	}
}

func (s *MongoReactionStatisticsStore) WithClock(now func() time.Time) *MongoReactionStatisticsStore {
	if s != nil && now != nil {
		s.now = now
	}
	return s
}

func (s *MongoReactionStatisticsStore) EnsureIndexes(ctx context.Context) error {
	if s == nil || s.db == nil {
		return errors.New("ContentReaction statistics store is unavailable")
	}
	if _, err := s.members.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "reactionId", Value: 1}, {Key: "dimension", Value: 1}, {Key: "contributionKind", Value: 1}}, Options: options.Index().SetName("uq_content_reaction_statistics_member").SetUnique(true)},
		{Keys: bson.D{{Key: "ownerKind", Value: 1}, {Key: "ownerId", Value: 1}, {Key: "dimension", Value: 1}, {Key: "bucket", Value: 1}}, Options: options.Index().SetName("idx_content_reaction_statistics_member_owner")},
	}); err != nil {
		return err
	}
	if _, err := s.buckets.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "generation", Value: 1}, {Key: "ownerKind", Value: 1}, {Key: "ownerId", Value: 1}, {Key: "dimension", Value: 1}, {Key: "contributionKind", Value: 1}, {Key: "bucket", Value: 1}}, Options: options.Index().SetName("uq_content_reaction_statistics_bucket").SetUnique(true)},
		{Keys: bson.D{{Key: "generation", Value: 1}, {Key: "ownerKind", Value: 1}, {Key: "ownerId", Value: 1}}, Options: options.Index().SetName("idx_content_reaction_statistics_bucket_owner")},
	}); err != nil {
		return err
	}
	if _, err := s.rollups.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "generation", Value: 1}, {Key: "dimension", Value: 1}, {Key: "ownerKind", Value: 1}, {Key: "ownerId", Value: 1}}, Options: options.Index().SetName("uq_content_reaction_statistics_rollup").SetUnique(true)},
	}); err != nil {
		return err
	}
	return nil
}

func (s *MongoReactionStatisticsStore) Publish(ctx context.Context, fact reactionports.OutboxFact) error {
	payload, err := reactionapp.DecodeStatisticsFact(fact)
	if err != nil {
		return err
	}
	checkpoint := fact.PartitionSequence
	if checkpoint <= 0 {
		return errors.New("ContentReaction statistics fact requires a positive partition checkpoint")
	}
	digest := statisticsDigest(fact.EventType, fact.Payload)
	contributions := statisticsContributions(payload)
	session, err := s.db.Client().StartSession()
	if err != nil {
		return err
	}
	defer session.EndSession(ctx)
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		var existing reactionStatisticsInboxDocument
		inboxErr := s.inbox.FindOne(txCtx, bson.M{"_id": fact.EventID}).Decode(&existing)
		if inboxErr == nil {
			if existing.PayloadDigest != digest {
				return nil, errors.New("ContentReaction statistics event digest mismatch")
			}
			return nil, nil
		}
		if inboxErr != mongo.ErrNoDocuments {
			return nil, inboxErr
		}
		for _, contribution := range contributions {
			if applyErr := s.applyContribution(txCtx, fact, payload, contribution, checkpoint, digest); applyErr != nil {
				return nil, applyErr
			}
		}
		_, insertErr := s.inbox.InsertOne(txCtx, reactionStatisticsInboxDocument{
			ID: fact.EventID, AggregateID: fact.AggregateID,
			AggregateVersion: fact.AggregateVersion, PayloadDigest: digest,
			PartitionID: fact.PartitionID, Checkpoint: checkpoint, AppliedAt: s.now().UTC(),
		})
		return nil, insertErr
	})
	if err != nil {
		return fmt.Errorf("apply ContentReaction statistics contribution: %w", err)
	}
	return nil
}

type statisticsContribution struct {
	dimension        string
	ownerKind        string
	ownerID          string
	contributionKind string
	value            int64
}

func statisticsContributions(payload reactionapp.StatisticsFact) []statisticsContribution {
	like, dislike := int64(0), int64(0)
	if payload.Reaction == string(reactiondomain.ValueLike) {
		like = 1
	}
	if payload.Reaction == string(reactiondomain.ValueDislike) {
		dislike = 1
	}
	result := []statisticsContribution{
		{dimension: "target", ownerKind: payload.TargetKind, ownerID: payload.TargetID, contributionKind: "like", value: like},
		{dimension: "target", ownerKind: payload.TargetKind, ownerID: payload.TargetID, contributionKind: "dislike", value: dislike},
	}
	if payload.ActorDimension == string(reactiondomain.ActorDimensionPersona) && payload.TargetKind == string(reactiondomain.TargetKindPost) {
		result = append(result, statisticsContribution{
			dimension: "actor", ownerKind: "persona", ownerID: payload.ActorID,
			contributionKind: "like", value: like,
		})
	}
	return result
}

func (s *MongoReactionStatisticsStore) applyContribution(ctx context.Context, fact reactionports.OutboxFact, payload reactionapp.StatisticsFact, contribution statisticsContribution, checkpoint int64, digest string) error {
	memberID := statisticsMemberID(payload.ReactionID, contribution)
	var existing reactionStatisticsMemberDocument
	err := s.members.FindOne(ctx, bson.M{"_id": memberID}).Decode(&existing)
	oldValue := int64(0)
	if err == nil {
		if existing.LastAppliedVersion > payload.Version {
			return nil
		}
		if existing.LastAppliedVersion == payload.Version {
			if existing.PayloadDigest != digest {
				return errors.New("ContentReaction statistics member version digest mismatch")
			}
			return nil
		}
		oldValue = existing.CurrentContribution
	} else if err != mongo.ErrNoDocuments {
		return err
	}
	delta := contribution.value - oldValue
	bucket := statisticsBucket(memberID, s.bucketCount)
	_, err = s.members.UpdateOne(ctx, bson.M{"_id": memberID}, bson.M{"$set": reactionStatisticsMemberDocument{
		ID: memberID, ReactionID: payload.ReactionID, Dimension: contribution.dimension,
		OwnerKind: contribution.ownerKind, OwnerID: contribution.ownerID,
		ContributionKind: contribution.contributionKind, Bucket: bucket,
		LastAppliedVersion: payload.Version, CurrentContribution: contribution.value,
		PayloadDigest: digest, SourceEventID: fact.EventID, UpdatedAt: payload.OccurredAt,
	}}, options.UpdateOne().SetUpsert(true))
	if err != nil {
		return err
	}
	if delta == 0 {
		return nil
	}
	bucketID := statisticsBucketID("live", contribution, bucket)
	if delta > 0 {
		_, err = s.buckets.UpdateOne(ctx, bson.M{"_id": bucketID}, bson.M{
			"$setOnInsert": bson.M{
				"generation": "live", "dimension": contribution.dimension,
				"ownerKind": contribution.ownerKind, "ownerId": contribution.ownerID,
				"contributionKind": contribution.contributionKind, "bucket": bucket,
			},
			"$inc": bson.M{"value": delta},
			"$max": bson.M{"maxSourceVersion": payload.Version, "maxCheckpoint": checkpoint},
			"$set": bson.M{"updatedAt": s.now().UTC()},
		}, options.UpdateOne().SetUpsert(true))
	} else {
		var updated reactionStatisticsBucketDocument
		err = s.buckets.FindOneAndUpdate(ctx, bson.M{
			"_id": bucketID, "value": bson.M{"$gte": -delta},
		}, bson.M{
			"$inc": bson.M{"value": delta},
			"$max": bson.M{"maxSourceVersion": payload.Version, "maxCheckpoint": checkpoint},
			"$set": bson.M{"updatedAt": s.now().UTC()},
		}, options.FindOneAndUpdate().SetReturnDocument(options.After)).Decode(&updated)
		if err == nil && updated.Value < 0 {
			return errors.New("ContentReaction statistics bucket is negative")
		}
	}
	if err != nil {
		if err == mongo.ErrNoDocuments || mongo.IsDuplicateKeyError(err) {
			return errors.New("ContentReaction statistics contribution would make bucket negative")
		}
		return err
	}
	return nil
}

func statisticsMemberID(reactionID string, contribution statisticsContribution) string {
	return statisticsDigest("member", []byte(reactionID+"\x00"+contribution.dimension+"\x00"+contribution.contributionKind))
}

func statisticsBucketID(generation string, contribution statisticsContribution, bucket int) string {
	return strings.Join([]string{generation, contribution.dimension, contribution.ownerKind, contribution.ownerID, contribution.contributionKind, strconv.Itoa(bucket)}, "\x1f")
}

func statisticsBucket(identity string, count int) int {
	if count <= 0 {
		count = DefaultReactionStatisticsBuckets
	}
	sum := sha256.Sum256([]byte(identity))
	value := uint64(0)
	for _, part := range sum[:8] {
		value = value<<8 | uint64(part)
	}
	return int(value % uint64(count))
}

func statisticsDigest(prefix string, payload []byte) string {
	sum := sha256.Sum256(append(append([]byte(prefix), 0), payload...))
	return hex.EncodeToString(sum[:])
}

func statisticsCheckpoint(value string) (int64, error) {
	checkpoint, err := strconv.ParseInt(strings.TrimSpace(value), 10, 64)
	if err != nil || checkpoint <= 0 {
		return 0, errors.New("ContentReaction statistics fact requires a positive checkpoint")
	}
	return checkpoint, nil
}

func statisticsRollupID(generation, dimension, ownerKind, ownerID string) string {
	return strings.Join([]string{generation, dimension, ownerKind, ownerID}, "\x1f")
}

func (s *MongoReactionStatisticsStore) ReadStatistics(ctx context.Context, target reactiondomain.Target) (reactionapp.ContentReactionStatisticsSlice, error) {
	if err := target.Validate(); err != nil {
		return reactionapp.ContentReactionStatisticsSlice{}, err
	}
	return s.readSlice(ctx, "target", string(target.Kind), target.ID)
}

func (s *MongoReactionStatisticsStore) ReadPersonaLikes(ctx context.Context, personaID string) (reactionapp.ContentReactionStatisticsSlice, error) {
	personaID = strings.TrimSpace(personaID)
	if personaID == "" {
		return reactionapp.ContentReactionStatisticsSlice{}, errors.New("persona id is required")
	}
	return s.readSlice(ctx, "actor", "persona", personaID)
}

func (s *MongoReactionStatisticsStore) readSlice(ctx context.Context, dimension, ownerKind, ownerID string) (reactionapp.ContentReactionStatisticsSlice, error) {
	var current reactionStatisticsGenerationDocument
	if err := s.generations.FindOne(ctx, bson.M{"_id": "current"}).Decode(&current); err != nil {
		if err == mongo.ErrNoDocuments {
			return reactionapp.ContentReactionStatisticsSlice{OwnerKind: ownerKind, OwnerID: ownerID, State: reactionapp.StatisticsUnavailable}, nil
		}
		return reactionapp.ContentReactionStatisticsSlice{}, err
	}
	var row reactionStatisticsRollupDocument
	err := s.rollups.FindOne(ctx, bson.M{
		"generation": current.Generation, "dimension": dimension,
		"ownerKind": ownerKind, "ownerId": ownerID,
	}).Decode(&row)
	if err != nil {
		if err == mongo.ErrNoDocuments {
			return reactionapp.ContentReactionStatisticsSlice{OwnerKind: ownerKind, OwnerID: ownerID, State: reactionapp.StatisticsUnavailable}, nil
		}
		return reactionapp.ContentReactionStatisticsSlice{}, err
	}
	now := s.now().UTC()
	state := reactionapp.StatisticsAvailable
	if now.After(row.ExpiresAt) {
		state = reactionapp.StatisticsStale
	}
	if now.After(row.AsOf.Add(time.Minute)) {
		return reactionapp.ContentReactionStatisticsSlice{OwnerKind: ownerKind, OwnerID: ownerID, State: reactionapp.StatisticsUnavailable}, nil
	}
	return reactionapp.ContentReactionStatisticsSlice{
		OwnerKind: ownerKind, OwnerID: ownerID, State: state,
		Snapshot: &reactionapp.ContentReactionStatisticsSnapshot{
			Generation: row.Generation, StatsVersion: row.StatsVersion,
			LikeCount: row.LikeCount, DislikeCount: row.DislikeCount,
			SourceCheckpoint: row.SourceCheckpoint, AsOf: row.AsOf, ExpiresAt: row.ExpiresAt,
		},
	}, nil
}

var _ reactionports.OutboxPublisher = (*MongoReactionStatisticsStore)(nil)
