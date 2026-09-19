package persistence

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/google/uuid"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

// Rollup publishes one immutable reader generation from live fixed buckets.
func (s *MongoReactionStatisticsStore) Rollup(ctx context.Context, freshFor time.Duration) (string, int64, error) {
	if freshFor <= 0 {
		freshFor = 5 * time.Second
	}
	generation := uuid.NewString()
	now := s.now().UTC()
	checkpointVector, err := s.statisticsCheckpointVector(ctx)
	if err != nil {
		return "", 0, err
	}
	checkpointText := formatStatisticsCheckpointVector(checkpointVector)
	pipeline := mongo.Pipeline{
		bson.D{{Key: "$match", Value: bson.M{"generation": "live"}}},
		bson.D{{Key: "$group", Value: bson.M{
			"_id":              bson.M{"dimension": "$dimension", "ownerKind": "$ownerKind", "ownerId": "$ownerId"},
			"likeCount":        bson.M{"$sum": bson.M{"$cond": bson.A{bson.M{"$eq": bson.A{"$contributionKind", "like"}}, "$value", 0}}},
			"dislikeCount":     bson.M{"$sum": bson.M{"$cond": bson.A{bson.M{"$eq": bson.A{"$contributionKind", "dislike"}}, "$value", 0}}},
			"statsVersion":     bson.M{"$max": "$maxSourceVersion"},
			"sourceCheckpoint": bson.M{"$max": "$maxCheckpoint"},
		}}},
	}
	cursor, err := s.buckets.Aggregate(ctx, pipeline)
	if err != nil {
		return "", 0, err
	}
	defer cursor.Close(ctx)
	// Publish an explicit initialized zero for every target observed in the
	// authority aggregate set, including targets whose only members currently
	// contribute none. This distinguishes a proven zero from a missing source.
	initializedTargets := make(map[string]struct{})
	targetCursor, targetErr := s.aggregates.Find(ctx, bson.M{}, options.Find().SetProjection(bson.M{"targetKind": 1, "targetId": 1}))
	if targetErr != nil {
		return "", 0, targetErr
	}
	for targetCursor.Next(ctx) {
		var target struct {
			TargetKind string `bson:"targetKind"`
			TargetID   string `bson:"targetId"`
		}
		if decodeErr := targetCursor.Decode(&target); decodeErr != nil {
			targetCursor.Close(ctx)
			return "", 0, decodeErr
		}
		initializedTargets[target.TargetKind+"\x1f"+target.TargetID] = struct{}{}
	}
	if targetErr := targetCursor.Err(); targetErr != nil {
		targetCursor.Close(ctx)
		return "", 0, targetErr
	}
	targetCursor.Close(ctx)
	type grouped struct {
		ID struct {
			Dimension string `bson:"dimension"`
			OwnerKind string `bson:"ownerKind"`
			OwnerID   string `bson:"ownerId"`
		} `bson:"_id"`
		LikeCount        int64 `bson:"likeCount"`
		DislikeCount     int64 `bson:"dislikeCount"`
		StatsVersion     int64 `bson:"statsVersion"`
		SourceCheckpoint int64 `bson:"sourceCheckpoint"`
	}
	documents := make([]any, 0)
	maxCheckpoint := int64(0)
	for cursor.Next(ctx) {
		var row grouped
		if err := cursor.Decode(&row); err != nil {
			return "", 0, err
		}
		if row.SourceCheckpoint > maxCheckpoint {
			maxCheckpoint = row.SourceCheckpoint
		}
		documents = append(documents, reactionStatisticsRollupDocument{
			ID:         statisticsRollupID(generation, row.ID.Dimension, row.ID.OwnerKind, row.ID.OwnerID),
			Generation: generation, Dimension: row.ID.Dimension, OwnerKind: row.ID.OwnerKind,
			OwnerID: row.ID.OwnerID, StatsVersion: row.StatsVersion,
			LikeCount: row.LikeCount, DislikeCount: row.DislikeCount,
			SourceCheckpoint: checkpointText, AsOf: now, ExpiresAt: now.Add(freshFor),
		})
	}
	if err := cursor.Err(); err != nil {
		return "", 0, err
	}
	for identity := range initializedTargets {
		parts := strings.SplitN(identity, "\x1f", 2)
		found := false
		for _, raw := range documents {
			row := raw.(reactionStatisticsRollupDocument)
			if row.Dimension == "target" && row.OwnerKind == parts[0] && row.OwnerID == parts[1] {
				found = true
				break
			}
		}
		if !found {
			documents = append(documents, reactionStatisticsRollupDocument{
				ID:         statisticsRollupID(generation, "target", parts[0], parts[1]),
				Generation: generation, Dimension: "target", OwnerKind: parts[0], OwnerID: parts[1],
				StatsVersion: 0, LikeCount: 0, DislikeCount: 0,
				SourceCheckpoint: checkpointText, AsOf: now, ExpiresAt: now.Add(freshFor),
			})
		}
	}
	session, err := s.db.Client().StartSession()
	if err != nil {
		return "", 0, err
	}
	defer session.EndSession(ctx)
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		if len(documents) > 0 {
			if _, insertErr := s.rollups.InsertMany(txCtx, documents); insertErr != nil {
				return nil, insertErr
			}
		}
		_, updateErr := s.generations.UpdateOne(txCtx, bson.M{"_id": "current"}, bson.M{"$set": reactionStatisticsGenerationDocument{
			ID: "current", Generation: generation, SourceCheckpoint: checkpointText, PublishedAt: now,
		}}, options.UpdateOne().SetUpsert(true))
		return nil, updateErr
	})
	if err != nil {
		return "", 0, fmt.Errorf("publish ContentReaction statistics generation: %w", err)
	}
	return generation, maxCheckpoint, nil
}
