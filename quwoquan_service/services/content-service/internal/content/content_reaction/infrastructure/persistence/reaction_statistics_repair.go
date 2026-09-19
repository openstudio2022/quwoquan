package persistence

import (
	"context"
	"errors"
	"fmt"
	"sort"
	"strings"
	"time"

	"github.com/google/uuid"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	reactionapp "quwoquan_service/services/content-service/internal/content/content_reaction/application/reaction"
	reactionports "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction/ports"
)

// Repair rebuilds a shadow generation from the authoritative aggregate
// snapshot, catches up nothing implicitly, verifies it against the current
// member ledger, and atomically replaces live members/buckets only when the
// snapshot checkpoint still matches the outbox tail.
func (s *MongoReactionStatisticsStore) Repair(ctx context.Context) (string, error) {
	generation := "repair-" + uuid.NewString()
	checkpointVector, err := s.outboxSequenceVector(ctx)
	if err != nil {
		return "", err
	}
	checkpointText := formatStatisticsCheckpointVector(checkpointVector)
	cursor, err := s.aggregates.Find(ctx, bson.M{}, options.Find().SetSort(bson.D{{Key: "_id", Value: 1}}))
	if err != nil {
		return "", err
	}
	defer cursor.Close(ctx)
	members := make([]any, 0)
	buckets := make(map[string]*reactionStatisticsBucketDocument)
	for cursor.Next(ctx) {
		var document contentReactionDocument
		if err := cursor.Decode(&document); err != nil {
			return "", err
		}
		payload := reactionapp.StatisticsFact{
			ReactionID: document.ID, Version: document.Version,
			TargetKind: document.TargetKind, TargetID: document.TargetID,
			ActorDimension: document.ActorDimension, ActorID: document.ActorID,
			Reaction: document.Reaction, OccurredAt: document.UpdatedAt,
		}
		for _, contribution := range statisticsContributions(payload) {
			memberID := statisticsMemberID(document.ID, contribution)
			bucket := statisticsBucket(memberID, s.bucketCount)
			digest := statisticsDigest("repair", []byte(fmt.Sprintf("%s:%d:%s", document.ID, document.Version, document.Reaction)))
			members = append(members, reactionStatisticsMemberDocument{
				ID: memberID, ReactionID: document.ID, Dimension: contribution.dimension,
				OwnerKind: contribution.ownerKind, OwnerID: contribution.ownerID,
				ContributionKind: contribution.contributionKind, Bucket: bucket,
				LastAppliedVersion: document.Version, CurrentContribution: contribution.value,
				PayloadDigest: digest, SourceEventID: "repair:" + generation,
				UpdatedAt: document.UpdatedAt,
			})
			if contribution.value == 0 {
				continue
			}
			key := statisticsBucketID(generation, contribution, bucket)
			row := buckets[key]
			if row == nil {
				row = &reactionStatisticsBucketDocument{
					ID: key, Generation: generation, Dimension: contribution.dimension,
					OwnerKind: contribution.ownerKind, OwnerID: contribution.ownerID,
					ContributionKind: contribution.contributionKind, Bucket: bucket,
					UpdatedAt:     s.now().UTC(),
					MaxCheckpoint: checkpointVector[reactionports.OutboxPartitionForKey(document.ID)],
				}
				buckets[key] = row
			}
			row.Value += contribution.value
			if document.Version > row.MaxSourceVersion {
				row.MaxSourceVersion = document.Version
			}
		}
	}
	if err := cursor.Err(); err != nil {
		return "", err
	}
	bucketDocs := make([]any, 0, len(buckets))
	for _, bucket := range buckets {
		bucketDocs = append(bucketDocs, bucket)
	}
	session, err := s.db.Client().StartSession()
	if err != nil {
		return "", err
	}
	defer session.EndSession(ctx)
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		currentVector, vectorErr := s.outboxSequenceVector(txCtx)
		if vectorErr != nil {
			return nil, vectorErr
		}
		if !equalStatisticsCheckpointVector(currentVector, checkpointVector) {
			return nil, errors.New("ContentReaction repair source checkpoint moved")
		}
		if _, deleteErr := s.members.DeleteMany(txCtx, bson.M{}); deleteErr != nil {
			return nil, deleteErr
		}
		if len(members) > 0 {
			if _, insertErr := s.members.InsertMany(txCtx, members); insertErr != nil {
				return nil, insertErr
			}
		}
		if _, deleteErr := s.buckets.DeleteMany(txCtx, bson.M{"generation": "live"}); deleteErr != nil {
			return nil, deleteErr
		}
		for _, raw := range bucketDocs {
			row := raw.(*reactionStatisticsBucketDocument)
			row.ID = strings.Replace(row.ID, generation+"\x1f", "live\x1f", 1)
			row.Generation = "live"
		}
		if len(bucketDocs) > 0 {
			if _, insertErr := s.buckets.InsertMany(txCtx, bucketDocs); insertErr != nil {
				return nil, insertErr
			}
		}
		return nil, nil
	})
	if err != nil {
		return "", fmt.Errorf("repair ContentReaction statistics: %w", err)
	}
	if _, _, err := s.Rollup(ctx, 5*time.Second); err != nil {
		return "", fmt.Errorf("publish repaired ContentReaction statistics generation %s at %s: %w", generation, checkpointText, err)
	}
	return generation, nil
}

func (s *MongoReactionStatisticsStore) statisticsCheckpointVector(ctx context.Context) (map[int]int64, error) {
	pipeline := mongo.Pipeline{bson.D{{Key: "$group", Value: bson.M{"_id": "$partitionId", "sequence": bson.M{"$max": "$checkpoint"}}}}}
	cursor, err := s.inbox.Aggregate(ctx, pipeline)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	vector := make(map[int]int64)
	for cursor.Next(ctx) {
		var row struct {
			PartitionID int   `bson:"_id"`
			Sequence    int64 `bson:"sequence"`
		}
		if err := cursor.Decode(&row); err != nil {
			return nil, err
		}
		vector[row.PartitionID] = row.Sequence
	}
	return vector, cursor.Err()
}

func (s *MongoReactionStatisticsStore) outboxSequenceVector(ctx context.Context) (map[int]int64, error) {
	cursor, err := s.db.Collection(contentReactionSequenceCollection).Find(ctx, bson.M{})
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	vector := make(map[int]int64)
	for cursor.Next(ctx) {
		var row struct {
			PartitionID int   `bson:"_id"`
			Value       int64 `bson:"value"`
		}
		if err := cursor.Decode(&row); err != nil {
			return nil, err
		}
		vector[row.PartitionID] = row.Value
	}
	return vector, cursor.Err()
}

func formatStatisticsCheckpointVector(vector map[int]int64) string {
	parts := make([]string, 0, len(vector))
	for partitionID, sequence := range vector {
		parts = append(parts, fmt.Sprintf("%d:%d", partitionID, sequence))
	}
	sort.Strings(parts)
	if len(parts) == 0 {
		return "empty"
	}
	return strings.Join(parts, ",")
}

func equalStatisticsCheckpointVector(left, right map[int]int64) bool {
	if len(left) != len(right) {
		return false
	}
	for partitionID, sequence := range left {
		if right[partitionID] != sequence {
			return false
		}
	}
	return true
}
