package releaseimport

import (
	"context"
	"fmt"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
)

const releaseStateBackfillReceiptName = "release-state-revision-source-version-v1"

type ReleaseStateBackfillResult struct {
	Environment   string
	SourceOwner   string
	ReleaseID     string
	Revision      int64
	SourceVersion int64
	Replayed      bool
}

type unversionedReleaseStateDocument struct {
	ID              any       `bson:"_id"`
	Environment     string    `bson:"environment"`
	SourceOwner     string    `bson:"sourceOwner"`
	Status          string    `bson:"status"`
	ReleaseID       string    `bson:"releaseId"`
	ActiveReleaseID string    `bson:"activeReleaseId"`
	ManifestDigest  string    `bson:"manifestDigest"`
	Revision        *int64    `bson:"revision,omitempty"`
	SourceVersion   *int64    `bson:"sourceVersion,omitempty"`
	ActivatedAt     time.Time `bson:"activatedAt"`
}

// BackfillUnversionedReleaseState performs the only supported migration for the
// pre-revision single active pointer. It never guesses identity, merges rows, or
// rewrites an already versioned pointer. The create-once receipt and pointer
// update commit atomically so interrupted operators can retry safely.
func BackfillUnversionedReleaseState(
	ctx context.Context,
	database *mongo.Database,
	environment string,
	sourceOwner string,
	now time.Time,
) (ReleaseStateBackfillResult, error) {
	if database == nil {
		return ReleaseStateBackfillResult{}, fmt.Errorf("release state backfill database is required")
	}
	environment = strings.TrimSpace(environment)
	sourceOwner = strings.TrimSpace(sourceOwner)
	if environment == "" || sourceOwner == "" {
		return ReleaseStateBackfillResult{}, fmt.Errorf("release state backfill environment/sourceOwner is required")
	}
	now = now.UTC().Truncate(time.Millisecond)
	if now.IsZero() {
		now = time.Now().UTC().Truncate(time.Millisecond)
	}
	state := database.Collection("data_release_state")
	receipts := database.Collection("data_release_state_migration_receipts")
	receiptID := fmt.Sprintf("%s:%s:%s", releaseStateBackfillReceiptName, environment, sourceOwner)
	session, err := database.Client().StartSession()
	if err != nil {
		return ReleaseStateBackfillResult{}, fmt.Errorf("start release state backfill session: %w", err)
	}
	defer session.EndSession(ctx)

	var result ReleaseStateBackfillResult
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		identity := bson.M{"environment": environment, "sourceOwner": sourceOwner}
		cursor, findErr := state.Find(txCtx, identity)
		if findErr != nil {
			return nil, fmt.Errorf("find unversioned release state: %w", findErr)
		}
		defer cursor.Close(txCtx)
		var documents []unversionedReleaseStateDocument
		if findErr = cursor.All(txCtx, &documents); findErr != nil {
			return nil, fmt.Errorf("decode unversioned release state: %w", findErr)
		}
		if len(documents) != 1 {
			return nil, fmt.Errorf(
				"GATE_BLOCK CONTENT.RELEASE.ACTIVE_POINTER_BACKFILL_CARDINALITY: environment=%q sourceOwner=%q documents=%d; exactly one pointer is required",
				environment, sourceOwner, len(documents),
			)
		}
		document := documents[0]
		releaseID := strings.TrimSpace(document.ActiveReleaseID)
		if releaseID == "" {
			releaseID = strings.TrimSpace(document.ReleaseID)
		}
		manifestDigest := strings.TrimSpace(document.ManifestDigest)
		if releaseID == "" || !sha256Pattern.MatchString(manifestDigest) ||
			strings.TrimSpace(document.Status) != "active" || document.ActivatedAt.IsZero() {
			return nil, fmt.Errorf(
				"GATE_BLOCK CONTENT.RELEASE.ACTIVE_POINTER_BACKFILL_IDENTITY_INVALID: pointer must have active releaseId, canonical manifestDigest, status=active, and activatedAt",
			)
		}

		if document.Revision != nil || document.SourceVersion != nil {
			if document.Revision == nil || document.SourceVersion == nil ||
				*document.Revision != 1 || *document.SourceVersion != document.ActivatedAt.UTC().UnixMilli() {
				return nil, fmt.Errorf("GATE_BLOCK CONTENT.RELEASE.ACTIVE_POINTER_BACKFILL_NOT_UNVERSIONED: pointer is partially or differently versioned")
			}
			var receipt struct {
				ReleaseID     string `bson:"releaseId"`
				Revision      int64  `bson:"revision"`
				SourceVersion int64  `bson:"sourceVersion"`
			}
			if receiptErr := receipts.FindOne(txCtx, bson.M{"_id": receiptID}).Decode(&receipt); receiptErr != nil {
				return nil, fmt.Errorf("GATE_BLOCK CONTENT.RELEASE.ACTIVE_POINTER_BACKFILL_RECEIPT_MISSING: versioned pointer has no matching migration receipt: %w", receiptErr)
			}
			if receipt.ReleaseID != releaseID || receipt.Revision != *document.Revision ||
				receipt.SourceVersion != *document.SourceVersion {
				return nil, fmt.Errorf("GATE_BLOCK CONTENT.RELEASE.ACTIVE_POINTER_BACKFILL_RECEIPT_DRIFT")
			}
			result = ReleaseStateBackfillResult{
				Environment: environment, SourceOwner: sourceOwner, ReleaseID: releaseID,
				Revision: receipt.Revision, SourceVersion: receipt.SourceVersion, Replayed: true,
			}
			return nil, nil
		}

		sourceVersion := document.ActivatedAt.UTC().UnixMilli()
		if sourceVersion <= 0 {
			return nil, fmt.Errorf("GATE_BLOCK CONTENT.RELEASE.ACTIVE_POINTER_BACKFILL_SOURCE_VERSION_INVALID")
		}
		updated, updateErr := state.UpdateOne(txCtx, bson.M{
			"_id":           document.ID,
			"revision":      bson.M{"$exists": false},
			"sourceVersion": bson.M{"$exists": false},
		}, bson.M{"$set": bson.M{
			"revision": int64(1), "sourceVersion": sourceVersion,
			"updatedAt": now,
		}})
		if updateErr != nil {
			return nil, fmt.Errorf("backfill unversioned release state: %w", updateErr)
		}
		if updated.MatchedCount != 1 {
			return nil, fmt.Errorf("GATE_BLOCK CONTENT.RELEASE.ACTIVE_POINTER_BACKFILL_RACE")
		}
		result = ReleaseStateBackfillResult{
			Environment: environment, SourceOwner: sourceOwner, ReleaseID: releaseID,
			Revision: 1, SourceVersion: sourceVersion,
		}
		if _, receiptErr := receipts.InsertOne(txCtx, bson.M{
			"_id": receiptID, "migration": releaseStateBackfillReceiptName,
			"environment": environment, "sourceOwner": sourceOwner,
			"releaseId": releaseID, "manifestDigest": manifestDigest,
			"revision": int64(1), "sourceVersion": sourceVersion,
			"status": "completed", "completedAt": now,
		}); receiptErr != nil {
			return nil, fmt.Errorf("create release state backfill receipt: %w", receiptErr)
		}
		return nil, nil
	})
	if err != nil {
		return ReleaseStateBackfillResult{}, err
	}
	return result, nil
}
