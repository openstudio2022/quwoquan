package persistence

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

const (
	circleGroupIndexLegacyName  = "idx_conv_circle_group"
	circleGroupIndexTargetName  = "uq_conv_circle_group"
	circleGroupIndexMigrationID = "chat.conversations.circle_group.unique.v1"

	circleGroupMigrationLeaseDuration = 2 * time.Minute
	circleGroupMigrationLeaseWait     = 30 * time.Second
	circleGroupMigrationLeaseRetry    = 100 * time.Millisecond
)

type circleGroupIndexMigrationLease struct {
	owner string
}

type circleGroupIndexMigrationRecord struct {
	State          string     `bson:"state"`
	LeaseOwner     string     `bson:"leaseOwner"`
	LeaseExpiresAt time.Time  `bson:"leaseExpiresAt"`
	Preflight      bson.M     `bson:"preflight"`
	CompletedAt    *time.Time `bson:"completedAt"`
	LastFailure    string     `bson:"lastFailure"`
	UpdatedAt      time.Time  `bson:"updatedAt"`
	StartedAt      time.Time  `bson:"startedAt"`
}

type circleGroupIndexPreflight struct {
	NullCount        int64
	BlankStringCount int64
	NonStringCount   int64
	DuplicateGroups  []circleGroupIndexDuplicate
}

type circleGroupIndexDuplicate struct {
	CircleGroupID string   `bson:"_id"`
	Count         int64    `bson:"count"`
	SampleIDs     []string `bson:"sampleIds"`
}

// migrateCircleGroupIndexToUnique upgrades the former sparse/non-unique
// circleGroupId index without relying on a reset of the Mongo volume. The
// durable lease serializes concurrent API starts, and every mutation is
// replay-safe after a process crash.
func (s *MongoChatStore) migrateCircleGroupIndexToUnique(ctx context.Context) (err error) {
	lease, acquired, err := s.acquireCircleGroupIndexMigrationLease(ctx)
	if err != nil {
		return err
	}
	if !acquired {
		return s.verifyCircleGroupTargetIndex(ctx)
	}
	completed := false
	defer func() {
		releaseCtx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		releaseErr := s.releaseCircleGroupIndexMigrationLease(
			releaseCtx,
			lease,
			completed,
			err,
		)
		if err == nil && releaseErr != nil {
			err = releaseErr
		}
	}()

	preflight, err := s.inspectCircleGroupIndexPreflight(ctx)
	if err != nil {
		return err
	}
	if err := s.recordCircleGroupIndexPreflight(ctx, lease, preflight); err != nil {
		return err
	}
	if preflight.NonStringCount > 0 {
		return fmt.Errorf(
			"circleGroupId index migration blocked by %d non-string legacy values",
			preflight.NonStringCount,
		)
	}
	if len(preflight.DuplicateGroups) > 0 {
		return fmt.Errorf(
			"circleGroupId index migration blocked by duplicate non-empty circleGroupId values: %s",
			summarizeCircleGroupDuplicates(preflight.DuplicateGroups),
		)
	}

	if err := s.normalizeLegacyBlankCircleGroupIDs(ctx); err != nil {
		return err
	}
	postNormalization, err := s.inspectCircleGroupIndexPreflight(ctx)
	if err != nil {
		return err
	}
	if postNormalization.NullCount != 0 ||
		postNormalization.BlankStringCount != 0 ||
		postNormalization.NonStringCount != 0 ||
		len(postNormalization.DuplicateGroups) != 0 {
		return fmt.Errorf(
			"circleGroupId index migration normalization did not converge: %s",
			summarizeCircleGroupPreflight(postNormalization),
		)
	}

	if err := s.reconcileCircleGroupIndex(ctx); err != nil {
		return err
	}
	if err := s.verifyCircleGroupTargetIndex(ctx); err != nil {
		return err
	}
	completed = true
	return nil
}

func (s *MongoChatStore) acquireCircleGroupIndexMigrationLease(
	ctx context.Context,
) (circleGroupIndexMigrationLease, bool, error) {
	owner, err := newCircleGroupMigrationLeaseOwner()
	if err != nil {
		return circleGroupIndexMigrationLease{}, false, err
	}
	deadline := time.Now().Add(circleGroupMigrationLeaseWait)
	ledger := s.db.Collection("chat_schema_migrations")
	for {
		var current circleGroupIndexMigrationRecord
		err := ledger.FindOne(ctx, bson.M{"_id": circleGroupIndexMigrationID}).Decode(&current)
		switch {
		case err == nil && current.State == "completed":
			return circleGroupIndexMigrationLease{}, false, nil
		case err != nil && !errors.Is(err, mongo.ErrNoDocuments):
			return circleGroupIndexMigrationLease{}, false, fmt.Errorf(
				"read circleGroupId index migration ledger: %w",
				err,
			)
		}

		now := time.Now().UTC()
		var updated circleGroupIndexMigrationRecord
		updateErr := ledger.FindOneAndUpdate(
			ctx,
			bson.M{
				"_id": circleGroupIndexMigrationID,
				"$or": bson.A{
					bson.M{"state": "pending"},
					bson.M{
						"state": "running",
						"$or": bson.A{
							bson.M{"leaseExpiresAt": bson.M{"$exists": false}},
							bson.M{"leaseExpiresAt": bson.M{"$lte": now}},
						},
					},
				},
			},
			bson.M{
				"$set": bson.M{
					"state":          "running",
					"leaseOwner":     owner,
					"leaseExpiresAt": now.Add(circleGroupMigrationLeaseDuration),
					"updatedAt":      now,
					"lastFailure":    "",
				},
				"$setOnInsert": bson.M{
					"startedAt": now,
				},
			},
			options.FindOneAndUpdate().
				SetUpsert(true).
				SetReturnDocument(options.After),
		).Decode(&updated)
		if updateErr == nil && updated.LeaseOwner == owner {
			return circleGroupIndexMigrationLease{owner: owner}, true, nil
		}
		if updateErr != nil &&
			!mongo.IsDuplicateKeyError(updateErr) &&
			!errors.Is(updateErr, mongo.ErrNoDocuments) {
			return circleGroupIndexMigrationLease{}, false, fmt.Errorf(
				"acquire circleGroupId index migration lease: %w",
				updateErr,
			)
		}
		if time.Now().After(deadline) {
			return circleGroupIndexMigrationLease{}, false, fmt.Errorf(
				"timed out waiting for circleGroupId index migration lease",
			)
		}
		select {
		case <-ctx.Done():
			return circleGroupIndexMigrationLease{}, false, ctx.Err()
		case <-time.After(circleGroupMigrationLeaseRetry):
		}
	}
}

func (s *MongoChatStore) releaseCircleGroupIndexMigrationLease(
	ctx context.Context,
	lease circleGroupIndexMigrationLease,
	completed bool,
	cause error,
) error {
	now := time.Now().UTC()
	update := bson.M{
		"$set": bson.M{
			"updatedAt": now,
		},
		"$unset": bson.M{
			"leaseOwner":     "",
			"leaseExpiresAt": "",
		},
	}
	if completed {
		update["$set"].(bson.M)["state"] = "completed"
		update["$set"].(bson.M)["completedAt"] = now
		update["$set"].(bson.M)["lastFailure"] = ""
	} else {
		update["$set"].(bson.M)["state"] = "pending"
		update["$set"].(bson.M)["lastFailure"] = migrationFailureSummary(cause)
	}
	_, err := s.db.Collection("chat_schema_migrations").UpdateOne(
		ctx,
		bson.M{
			"_id":        circleGroupIndexMigrationID,
			"leaseOwner": lease.owner,
		},
		update,
	)
	if err != nil {
		return fmt.Errorf("release circleGroupId index migration lease: %w", err)
	}
	return nil
}

func (s *MongoChatStore) recordCircleGroupIndexPreflight(
	ctx context.Context,
	lease circleGroupIndexMigrationLease,
	preflight circleGroupIndexPreflight,
) error {
	_, err := s.db.Collection("chat_schema_migrations").UpdateOne(
		ctx,
		bson.M{
			"_id":        circleGroupIndexMigrationID,
			"leaseOwner": lease.owner,
		},
		bson.M{
			"$set": bson.M{
				"preflight": preflight.asBSON(),
				"updatedAt": time.Now().UTC(),
			},
		},
	)
	if err != nil {
		return fmt.Errorf("record circleGroupId index migration preflight: %w", err)
	}
	return nil
}

func (s *MongoChatStore) inspectCircleGroupIndexPreflight(
	ctx context.Context,
) (circleGroupIndexPreflight, error) {
	nullCount, err := s.conversations.CountDocuments(
		ctx,
		bson.M{"circleGroupId": bson.M{"$type": "null"}},
	)
	if err != nil {
		return circleGroupIndexPreflight{}, fmt.Errorf(
			"count null circleGroupId values: %w",
			err,
		)
	}
	blankCount, err := s.conversations.CountDocuments(
		ctx,
		bson.M{
			"circleGroupId": bson.M{"$type": "string"},
			"$expr": bson.M{
				"$eq": bson.A{
					bson.M{"$trim": bson.M{"input": "$circleGroupId"}},
					"",
				},
			},
		},
	)
	if err != nil {
		return circleGroupIndexPreflight{}, fmt.Errorf(
			"count blank circleGroupId values: %w",
			err,
		)
	}
	nonStringCount, err := s.countNonStringCircleGroupIDs(ctx)
	if err != nil {
		return circleGroupIndexPreflight{}, err
	}
	duplicates, err := s.findDuplicateCircleGroupIDs(ctx)
	if err != nil {
		return circleGroupIndexPreflight{}, err
	}
	return circleGroupIndexPreflight{
		NullCount:        nullCount,
		BlankStringCount: blankCount,
		NonStringCount:   nonStringCount,
		DuplicateGroups:  duplicates,
	}, nil
}

func (s *MongoChatStore) countNonStringCircleGroupIDs(ctx context.Context) (int64, error) {
	count, err := s.conversations.CountDocuments(
		ctx,
		bson.M{
			"circleGroupId": bson.M{"$exists": true},
			"$expr": bson.M{
				"$and": bson.A{
					bson.M{
						"$ne": bson.A{
							bson.M{"$type": "$circleGroupId"},
							"string",
						},
					},
					bson.M{
						"$ne": bson.A{
							bson.M{"$type": "$circleGroupId"},
							"null",
						},
					},
				},
			},
		},
	)
	if err != nil {
		return 0, fmt.Errorf("count non-string circleGroupId values: %w", err)
	}
	return count, nil
}

func (s *MongoChatStore) findDuplicateCircleGroupIDs(
	ctx context.Context,
) ([]circleGroupIndexDuplicate, error) {
	cursor, err := s.conversations.Aggregate(ctx, mongo.Pipeline{
		{{Key: "$match", Value: bson.M{
			"circleGroupId": bson.M{"$type": "string"},
			"$expr": bson.M{
				"$ne": bson.A{
					bson.M{"$trim": bson.M{"input": "$circleGroupId"}},
					"",
				},
			},
		}}},
		{{Key: "$group", Value: bson.M{
			"_id":       "$circleGroupId",
			"count":     bson.M{"$sum": 1},
			"sampleIds": bson.M{"$push": "$_id"},
		}}},
		{{Key: "$match", Value: bson.M{"count": bson.M{"$gt": 1}}}},
		{{Key: "$project", Value: bson.M{
			"count":     1,
			"sampleIds": bson.M{"$slice": bson.A{"$sampleIds", 5}},
		}}},
		{{Key: "$limit", Value: 5}},
	})
	if err != nil {
		return nil, fmt.Errorf("inspect duplicate circleGroupId values: %w", err)
	}
	defer cursor.Close(ctx)
	var duplicates []circleGroupIndexDuplicate
	if err := cursor.All(ctx, &duplicates); err != nil {
		return nil, fmt.Errorf("decode duplicate circleGroupId values: %w", err)
	}
	return duplicates, nil
}

func (s *MongoChatStore) normalizeLegacyBlankCircleGroupIDs(ctx context.Context) error {
	if _, err := s.conversations.UpdateMany(
		ctx,
		bson.M{"circleGroupId": bson.M{"$type": "null"}},
		bson.M{"$unset": bson.M{"circleGroupId": ""}},
	); err != nil {
		return fmt.Errorf("unset null circleGroupId values: %w", err)
	}
	if _, err := s.conversations.UpdateMany(
		ctx,
		bson.M{"circleGroupId": bson.M{"$type": "string"}},
		mongo.Pipeline{
			{{Key: "$set", Value: bson.M{
				"circleGroupId": bson.M{
					"$cond": bson.A{
						bson.M{
							"$eq": bson.A{
								bson.M{"$trim": bson.M{"input": "$circleGroupId"}},
								"",
							},
						},
						"$$REMOVE",
						"$circleGroupId",
					},
				},
			}}},
		},
	); err != nil {
		return fmt.Errorf("normalize blank circleGroupId values: %w", err)
	}
	return nil
}

func (s *MongoChatStore) reconcileCircleGroupIndex(ctx context.Context) error {
	indexes, err := s.listCircleGroupIndexes(ctx)
	if err != nil {
		return err
	}
	if indexes.targetFound && indexes.legacyFound {
		if err := s.conversations.Indexes().DropOne(ctx, circleGroupIndexLegacyName); err != nil {
			return fmt.Errorf("drop legacy circleGroupId index: %w", err)
		}
		return nil
	}
	if indexes.targetFound {
		return nil
	}
	if indexes.legacyFound {
		if err := s.conversations.Indexes().DropOne(ctx, circleGroupIndexLegacyName); err != nil {
			return fmt.Errorf("drop legacy circleGroupId index: %w", err)
		}
	}
	_, err = s.conversations.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "circleGroupId", Value: 1}},
		Options: options.Index().SetName(circleGroupIndexTargetName).SetSparse(true).SetUnique(true),
	})
	if err != nil {
		return fmt.Errorf("create unique circleGroupId index: %w", err)
	}
	return nil
}

type circleGroupIndexSet struct {
	targetFound bool
	legacyFound bool
}

func (s *MongoChatStore) verifyCircleGroupTargetIndex(ctx context.Context) error {
	indexes, err := s.listCircleGroupIndexes(ctx)
	if err != nil {
		return err
	}
	if !indexes.targetFound || indexes.legacyFound {
		return fmt.Errorf("circleGroupId index migration did not reach unique sparse target")
	}
	return nil
}

func (s *MongoChatStore) listCircleGroupIndexes(
	ctx context.Context,
) (circleGroupIndexSet, error) {
	cursor, err := s.conversations.Indexes().List(ctx)
	if err != nil {
		return circleGroupIndexSet{}, fmt.Errorf("list conversation indexes: %w", err)
	}
	defer cursor.Close(ctx)
	var documents []bson.M
	if err := cursor.All(ctx, &documents); err != nil {
		return circleGroupIndexSet{}, fmt.Errorf("decode conversation indexes: %w", err)
	}
	result := circleGroupIndexSet{}
	for _, index := range documents {
		if !isCircleGroupIndexKey(index["key"]) {
			continue
		}
		name, _ := index["name"].(string)
		unique, _ := index["unique"].(bool)
		sparse, _ := index["sparse"].(bool)
		switch name {
		case circleGroupIndexTargetName:
			if !unique || !sparse {
				return circleGroupIndexSet{}, fmt.Errorf(
					"circleGroupId target index has unsupported options: %#v",
					index,
				)
			}
			result.targetFound = true
		case circleGroupIndexLegacyName:
			if unique || !sparse {
				return circleGroupIndexSet{}, fmt.Errorf(
					"circleGroupId legacy index has unsupported options: %#v",
					index,
				)
			}
			result.legacyFound = true
		default:
			return circleGroupIndexSet{}, fmt.Errorf(
				"unexpected circleGroupId index blocks migration: %#v",
				index,
			)
		}
	}
	return result, nil
}

func isCircleGroupIndexKey(raw any) bool {
	switch key := raw.(type) {
	case bson.D:
		return len(key) == 1 && key[0].Key == "circleGroupId" && key[0].Value == int32(1)
	case bson.M:
		value, found := key["circleGroupId"]
		return len(key) == 1 && found && isAscendingIndexValue(value)
	case map[string]any:
		value, found := key["circleGroupId"]
		return len(key) == 1 && found && isAscendingIndexValue(value)
	default:
		return false
	}
}

func isAscendingIndexValue(value any) bool {
	switch number := value.(type) {
	case int32:
		return number == 1
	case int64:
		return number == 1
	case int:
		return number == 1
	case float64:
		return number == 1
	default:
		return false
	}
}

func (preflight circleGroupIndexPreflight) asBSON() bson.M {
	duplicates := make([]bson.M, 0, len(preflight.DuplicateGroups))
	for _, duplicate := range preflight.DuplicateGroups {
		duplicates = append(duplicates, bson.M{
			"circleGroupId": duplicate.CircleGroupID,
			"count":         duplicate.Count,
			"sampleIds":     duplicate.SampleIDs,
		})
	}
	return bson.M{
		"nullCount":        preflight.NullCount,
		"blankStringCount": preflight.BlankStringCount,
		"nonStringCount":   preflight.NonStringCount,
		"duplicateGroups":  duplicates,
	}
}

func summarizeCircleGroupDuplicates(duplicates []circleGroupIndexDuplicate) string {
	parts := make([]string, 0, len(duplicates))
	for _, duplicate := range duplicates {
		parts = append(parts, fmt.Sprintf(
			"%s(count=%d,samples=%s)",
			duplicate.CircleGroupID,
			duplicate.Count,
			strings.Join(duplicate.SampleIDs, ","),
		))
	}
	return strings.Join(parts, ";")
}

func summarizeCircleGroupPreflight(preflight circleGroupIndexPreflight) string {
	return fmt.Sprintf(
		"null=%d blank=%d nonString=%d duplicateGroups=%d",
		preflight.NullCount,
		preflight.BlankStringCount,
		preflight.NonStringCount,
		len(preflight.DuplicateGroups),
	)
}

func migrationFailureSummary(cause error) string {
	if cause == nil {
		return "unknown migration failure"
	}
	return strings.TrimSpace(cause.Error())
}

func newCircleGroupMigrationLeaseOwner() (string, error) {
	var token [16]byte
	if _, err := rand.Read(token[:]); err != nil {
		return "", fmt.Errorf("generate circleGroupId index migration lease owner: %w", err)
	}
	return hex.EncodeToString(token[:]), nil
}
