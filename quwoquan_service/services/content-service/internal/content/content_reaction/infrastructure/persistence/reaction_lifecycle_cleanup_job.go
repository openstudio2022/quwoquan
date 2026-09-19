package persistence

import (
	"context"
	"errors"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	reactionapp "quwoquan_service/services/content-service/internal/content/content_reaction/application/reaction"
	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
)

type lifecycleCleanupJobDocument struct {
	ID             string    `bson:"_id"`
	Scope          string    `bson:"scope"`
	TargetKind     string    `bson:"targetKind,omitempty"`
	TargetID       string    `bson:"targetId,omitempty"`
	ActorDimension string    `bson:"actorDimension,omitempty"`
	ActorID        string    `bson:"actorId,omitempty"`
	Source         string    `bson:"source"`
	SourceEventID  string    `bson:"sourceEventId"`
	SourceVersion  int64     `bson:"sourceVersion"`
	Tombstone      string    `bson:"tombstone"`
	Cursor         string    `bson:"cursor"`
	Checkpoint     int64     `bson:"checkpoint"`
	Deadline       time.Time `bson:"deadline"`
	LeaseEpoch     int64     `bson:"leaseEpoch"`
	LeaseUntil     time.Time `bson:"leaseUntil"`
	Completed      bool      `bson:"completed"`
	UpdatedAt      time.Time `bson:"updatedAt"`
}

func (s *MongoContentReactionStore) Ensure(ctx context.Context, job reactionapp.LifecycleCleanupJob) (reactionapp.LifecycleCleanupJob, error) {
	now := s.now().UTC()
	document := lifecycleCleanupJobDocument{
		ID: job.ID, Scope: string(job.Scope), TargetKind: string(job.Target.Kind), TargetID: job.Target.ID,
		ActorDimension: string(job.Actor.Dimension), ActorID: job.Actor.ID,
		Source: job.Source, SourceEventID: job.SourceEventID, SourceVersion: job.SourceVersion,
		Tombstone: job.Tombstone, Cursor: job.Cursor,
	}
	_, err := s.cleanupJobs.UpdateOne(ctx, bson.M{"_id": job.ID}, bson.M{
		"$setOnInsert": bson.M{
			"scope": document.Scope, "targetKind": document.TargetKind, "targetId": document.TargetID,
			"actorDimension": document.ActorDimension, "actorId": document.ActorID,
			"source": document.Source, "sourceEventId": document.SourceEventID,
			"sourceVersion": document.SourceVersion, "tombstone": document.Tombstone,
			"cursor": document.Cursor, "checkpoint": int64(0), "leaseEpoch": int64(0), "completed": false,
		},
		"$set": bson.M{"deadline": job.Deadline.UTC(), "updatedAt": now},
	}, options.UpdateOne().SetUpsert(true))
	if err != nil {
		return reactionapp.LifecycleCleanupJob{}, err
	}
	var stored lifecycleCleanupJobDocument
	if err := s.cleanupJobs.FindOne(ctx, bson.M{"_id": job.ID}).Decode(&stored); err != nil {
		return reactionapp.LifecycleCleanupJob{}, err
	}
	if stored.Scope != document.Scope || stored.Source != document.Source || stored.SourceEventID != document.SourceEventID ||
		stored.SourceVersion != document.SourceVersion || stored.Tombstone != document.Tombstone ||
		stored.TargetKind != document.TargetKind || stored.TargetID != document.TargetID ||
		stored.ActorDimension != document.ActorDimension || stored.ActorID != document.ActorID {
		return reactionapp.LifecycleCleanupJob{}, errors.New("ContentReaction cleanup job identity was reused with different authority")
	}
	return cleanupJob(stored), nil
}

func (s *MongoContentReactionStore) Claim(ctx context.Context, id string, now time.Time, lease time.Duration) (reactionapp.LifecycleCleanupJob, bool, error) {
	var document lifecycleCleanupJobDocument
	err := s.cleanupJobs.FindOneAndUpdate(
		ctx,
		bson.M{"_id": id, "completed": false, "$or": []bson.M{{"leaseUntil": bson.M{"$lte": now}}, {"leaseUntil": bson.M{"$exists": false}}}},
		bson.M{"$inc": bson.M{"leaseEpoch": 1}, "$set": bson.M{"leaseUntil": now.Add(lease), "updatedAt": now}},
		options.FindOneAndUpdate().SetReturnDocument(options.After),
	).Decode(&document)
	if errors.Is(err, mongo.ErrNoDocuments) {
		return reactionapp.LifecycleCleanupJob{}, false, nil
	}
	return cleanupJob(document), err == nil, err
}

func (s *MongoContentReactionStore) Advance(ctx context.Context, id string, epoch int64, cursor string, checkpoint int64, done bool) error {
	now := s.now().UTC()
	result, err := s.cleanupJobs.UpdateOne(
		ctx,
		bson.M{"_id": id, "leaseEpoch": epoch, "completed": false},
		bson.M{"$set": bson.M{"cursor": cursor, "checkpoint": checkpoint, "completed": done, "leaseUntil": now, "updatedAt": now}},
	)
	if err != nil {
		return err
	}
	if result.MatchedCount != 1 {
		return errors.New("reaction cleanup lease epoch is stale")
	}
	return nil
}

func (s *MongoContentReactionStore) ListActiveReactionsForCleanup(ctx context.Context, job reactionapp.LifecycleCleanupJob, limit int) ([]reactiondomain.Identity, error) {
	if limit <= 0 || limit > 500 {
		limit = 500
	}
	filter := bson.M{"reaction": bson.M{"$ne": string(reactiondomain.ValueNone)}}
	switch job.Scope {
	case reactionapp.LifecycleCleanupScopeTarget:
		filter["targetKind"] = string(job.Target.Kind)
		filter["targetId"] = job.Target.ID
	case reactionapp.LifecycleCleanupScopeActor:
		filter["actorDimension"] = string(job.Actor.Dimension)
		filter["actorId"] = job.Actor.ID
	default:
		return nil, errors.New("unsupported ContentReaction cleanup scope")
	}
	if cursor := strings.TrimSpace(job.Cursor); cursor != "" {
		filter["_id"] = bson.M{"$gt": cursor}
	}
	cursor, err := s.aggregates.Find(ctx, filter, options.Find().SetProjection(bson.M{
		"targetKind": 1, "targetId": 1, "actorDimension": 1, "actorId": 1,
	}).SetSort(bson.D{{Key: "_id", Value: 1}}).SetLimit(int64(limit)))
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	var rows []struct {
		TargetKind     string `bson:"targetKind"`
		TargetID       string `bson:"targetId"`
		ActorDimension string `bson:"actorDimension"`
		ActorID        string `bson:"actorId"`
	}
	if err := cursor.All(ctx, &rows); err != nil {
		return nil, err
	}
	identities := make([]reactiondomain.Identity, 0, len(rows))
	for _, row := range rows {
		target, err := reactiondomain.NewTarget(reactiondomain.TargetKind(row.TargetKind), row.TargetID)
		if err != nil {
			return nil, err
		}
		actor, err := reactiondomain.NewActor(reactiondomain.ActorDimension(row.ActorDimension), row.ActorID)
		if err != nil {
			return nil, err
		}
		identity, err := reactiondomain.NewIdentity(target, actor)
		if err != nil {
			return nil, err
		}
		identities = append(identities, identity)
	}
	return identities, nil
}

func cleanupJob(document lifecycleCleanupJobDocument) reactionapp.LifecycleCleanupJob {
	return reactionapp.LifecycleCleanupJob{
		ID: document.ID, Scope: reactionapp.LifecycleCleanupScope(document.Scope),
		Target: reactiondomain.Target{Kind: reactiondomain.TargetKind(document.TargetKind), ID: document.TargetID},
		Actor:  reactiondomain.Actor{Dimension: reactiondomain.ActorDimension(document.ActorDimension), ID: document.ActorID},
		Source: document.Source, SourceEventID: document.SourceEventID, SourceVersion: document.SourceVersion,
		Tombstone: document.Tombstone, Cursor: document.Cursor, Checkpoint: document.Checkpoint,
		Deadline: document.Deadline, LeaseEpoch: document.LeaseEpoch, Completed: document.Completed,
	}
}
