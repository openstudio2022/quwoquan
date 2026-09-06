//go:build mongo_integration

// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016
package api_integration

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/releaseimport"
)

func legacyReleaseStateExpectation() LegacyReleaseStateMigrationExpectation {
	return LegacyReleaseStateMigrationExpectation{
		Environment: "alpha", SourceOwner: "qwq_data", ReleaseID: "release-research-legacy",
		ManifestDigest: "sha256:" + strings.Repeat("a", 64), ReleaseClass: "research",
		ProjectionVersion: 17, ActivatedAt: time.Date(2026, 9, 5, 8, 0, 0, 123000000, time.UTC),
		LegacyIndexSet: LegacyReleaseStateIndexSetV1, LegacyReceiptIndexSet: LegacyReleaseStageReceiptIndexSetV1,
		ExpectedReceiptCount: 5,
	}
}

func seedLegacyReleaseState(t *testing.T, db *mongo.Database, expectation LegacyReleaseStateMigrationExpectation) bson.M {
	t.Helper()
	ctx := context.Background()
	legacy := bson.M{
		"environment": expectation.Environment, "sourceOwner": expectation.SourceOwner,
		"releaseId": expectation.ReleaseID, "activeReleaseId": expectation.ReleaseID,
		"manifestDigest": expectation.ManifestDigest, "status": "active",
		"releaseClass": expectation.ReleaseClass, "projectionVersion": expectation.ProjectionVersion,
		"activatedAt": expectation.ActivatedAt, "createdAt": expectation.ActivatedAt.Add(-time.Minute),
		"updatedAt": expectation.ActivatedAt, "mode": "sync", "deletePolicy": "tombstone",
		"counts":   bson.M{"postsUpserted": 12},
		"readback": bson.M{"status": "content_imported", "checkedAt": expectation.ActivatedAt},
	}
	state := db.Collection("data_release_state")
	if _, err := state.InsertOne(ctx, legacy); err != nil {
		t.Fatalf("seed legacy release state: %v", err)
	}
	if _, err := state.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "environment", Value: 1}, {Key: "releaseId", Value: 1}, {Key: "manifestDigest", Value: 1}},
			Options: options.Index().SetName("uq_data_release_state_environment_candidate").SetUnique(true),
		},
		{
			Keys:    bson.D{{Key: "environment", Value: 1}, {Key: "status", Value: 1}, {Key: "activatedAt", Value: -1}},
			Options: options.Index().SetName("idx_data_release_state_active_pointer"),
		},
	}); err != nil {
		t.Fatalf("seed legacy release-state indexes: %v", err)
	}
	return legacy
}

func seedLegacyReleaseStageReceipts(t *testing.T, db *mongo.Database, expectation LegacyReleaseStateMigrationExpectation, releases int) []bson.Raw {
	t.Helper()
	ctx := context.Background()
	receipts := db.Collection("data_release_stage_receipts")
	stages := []struct {
		name       string
		checkpoint string
	}{
		{name: "prepared", checkpoint: "canonical-input-validated"},
		{name: "imported", checkpoint: "posts-materialized"},
		{name: "projected", checkpoint: "lifecycle-outbox-appended"},
		{name: "verified", checkpoint: "counts-and-readback-validated"},
		{name: "active", checkpoint: "active-pointer-committed"},
	}
	rows := make([]any, 0, releases*len(stages))
	for releaseIndex := range releases {
		releaseID := expectation.ReleaseID
		manifestDigest := expectation.ManifestDigest
		if releaseIndex != 0 {
			releaseID = "release-research-legacy-" + string(rune('a'+releaseIndex))
			manifestDigest = "sha256:" + strings.Repeat(string(rune('a'+releaseIndex)), 64)
		}
		for stageIndex, stage := range stages {
			recordedAt := expectation.ActivatedAt.Add(time.Duration(releaseIndex*10+stageIndex) * time.Second)
			rows = append(rows, bson.M{
				"environment": expectation.Environment, "releaseId": releaseID,
				"manifestDigest": manifestDigest, "stage": stage.name,
				"attemptId": expectation.Environment + ":" + releaseID + ":" + strconv.FormatInt(recordedAt.UnixNano(), 10),
				"status":    "passed", "recordedAt": recordedAt,
				"durationMs": int64(stageIndex), "attemptedCount": int64(3), "successCount": int64(3),
				"checkpoint": stage.checkpoint,
			})
		}
	}
	if _, err := receipts.InsertMany(ctx, rows); err != nil {
		t.Fatalf("seed legacy release-stage receipts: %v", err)
	}
	if _, err := receipts.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "environment", Value: 1}, {Key: "releaseId", Value: 1}, {Key: "manifestDigest", Value: 1}, {Key: "stage", Value: 1}, {Key: "attemptId", Value: 1}},
			Options: options.Index().SetName("uq_data_release_stage_receipt_attempt").SetUnique(true),
		},
		{
			Keys:    bson.D{{Key: "environment", Value: 1}, {Key: "releaseId", Value: 1}, {Key: "recordedAt", Value: 1}},
			Options: options.Index().SetName("idx_data_release_stage_receipt_timeline"),
		},
	}); err != nil {
		t.Fatalf("seed legacy release-stage receipt indexes: %v", err)
	}
	return rawDocumentClosure(t, receipts, bson.M{})
}

func setCurrentReleaseStateForReplay(t *testing.T, db *mongo.Database, expectation LegacyReleaseStateMigrationExpectation) {
	t.Helper()
	ctx := context.Background()
	if _, err := db.Collection("data_release_state").UpdateOne(ctx, bson.D{}, bson.M{"$set": bson.M{"kind": "active_pointer", "revision": int64(1)}}); err != nil {
		t.Fatal(err)
	}
	if err := db.Collection("data_release_state").Indexes().DropOne(ctx, "idx_data_release_state_active_pointer"); err != nil {
		t.Fatal(err)
	}
	if err := db.Collection("data_release_state").Indexes().DropOne(ctx, "uq_data_release_state_environment_candidate"); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Collection("data_release_state").Indexes().CreateMany(ctx, []mongo.IndexModel{
		{Keys: bson.D{{Key: "environment", Value: 1}, {Key: "sourceOwner", Value: 1}, {Key: "kind", Value: 1}}, Options: options.Index().SetName("uq_data_release_state_active_pointer").SetUnique(true).SetPartialFilterExpression(bson.D{{Key: "kind", Value: "active_pointer"}})},
		{Keys: bson.D{{Key: "environment", Value: 1}, {Key: "sourceOwner", Value: 1}, {Key: "kind", Value: 1}, {Key: "releaseId", Value: 1}, {Key: "manifestDigest", Value: 1}}, Options: options.Index().SetName("uq_data_release_state_environment_candidate").SetUnique(true).SetPartialFilterExpression(bson.D{{Key: "kind", Value: "candidate"}})},
	}); err != nil {
		t.Fatal(err)
	}
}

func TestMongoLegacyReleaseStateMigrationPreservesFactsRebuildsIndexesAndReplays(t *testing.T) {
	db, cleanup := testDB(t)
	defer cleanup()
	ctx := context.Background()
	expectation := legacyReleaseStateExpectation()
	expectation.ExpectedReceiptCount = 15
	legacy := seedLegacyReleaseState(t, db, expectation)
	legacyReceipts := seedLegacyReleaseStageReceipts(t, db, expectation, 3)

	result, err := MigrateLegacyContentReleaseState(ctx, db, expectation)
	if err != nil {
		t.Fatalf("migrate legacy release state: %v", err)
	}
	if result.Status != "migrated" || result.ReceiptCount != 15 ||
		result.BeforeIndexSetDigest != LegacyReleaseStateExpectedIndexDigest() ||
		result.AfterIndexSetDigest != CurrentReleaseStateExpectedIndexDigest() ||
		result.BeforeReceiptIndexSetDigest != LegacyReleaseStageReceiptExpectedIndexDigest() ||
		result.AfterReceiptIndexSetDigest != CurrentReleaseStageReceiptExpectedIndexDigest() ||
		result.BeforeReceiptRowSetDigest == result.AfterReceiptRowSetDigest {
		t.Fatalf("migration result drifted: %+v", result)
	}
	var current bson.M
	if err := db.Collection("data_release_state").FindOne(ctx, bson.D{}).Decode(&current); err != nil {
		t.Fatal(err)
	}
	if current["kind"] != "active_pointer" || numericInt64(current["revision"]) != 1 ||
		current["releaseId"] != legacy["releaseId"] || current["activeReleaseId"] != legacy["activeReleaseId"] ||
		current["manifestDigest"] != legacy["manifestDigest"] || current["releaseClass"] != legacy["releaseClass"] ||
		numericInt64(current["projectionVersion"]) != numericInt64(legacy["projectionVersion"]) {
		t.Fatalf("migrated release-state identity drifted: %#v", current)
	}
	for _, field := range []string{"activatedAt", "createdAt", "updatedAt", "mode", "deletePolicy", "counts", "readback", "status"} {
		if !bsonValueEquivalent(current[field], legacy[field]) {
			t.Fatalf("migrated field %s changed: got=%#v want=%#v", field, current[field], legacy[field])
		}
	}
	assertReleaseStateIndexNames(t, db, []string{"_id_", "uq_data_release_state_active_pointer", "uq_data_release_state_environment_candidate"})
	assertReleaseStageReceiptMigration(t, db, legacyReceipts, expectation, 15)

	expectation.AllowReplay = true
	replay, err := MigrateLegacyContentReleaseState(ctx, db, expectation)
	if err != nil {
		t.Fatalf("replay release-state migration: %v", err)
	}
	if replay.Status != "replayed" || len(replay.Steps) != 0 || replay.ReceiptCount != 15 ||
		replay.AfterIndexSetDigest != CurrentReleaseStateExpectedIndexDigest() ||
		replay.AfterReceiptIndexSetDigest != CurrentReleaseStageReceiptExpectedIndexDigest() {
		t.Fatalf("migration replay was not a no-op: %+v", replay)
	}
	if _, err := MigrateLegacyContentReleaseState(ctx, db, LegacyReleaseStateMigrationExpectation{
		Environment: expectation.Environment, SourceOwner: expectation.SourceOwner, ReleaseID: expectation.ReleaseID,
		ManifestDigest: expectation.ManifestDigest, ReleaseClass: expectation.ReleaseClass,
		ProjectionVersion: expectation.ProjectionVersion, ActivatedAt: expectation.ActivatedAt,
		LegacyIndexSet: expectation.LegacyIndexSet, LegacyReceiptIndexSet: expectation.LegacyReceiptIndexSet,
		ExpectedReceiptCount: expectation.ExpectedReceiptCount,
	}); err == nil || !strings.Contains(err.Error(), "--allow-replay") {
		t.Fatalf("implicit replay was accepted: %v", err)
	}
}

func TestMongoLegacyReleaseStateMigrationCommandWritesCreateOnceRedactedReceipt(t *testing.T) {
	db, cleanup := testDB(t)
	defer cleanup()
	expectation := legacyReleaseStateExpectation()
	seedLegacyReleaseState(t, db, expectation)
	seedLegacyReleaseStageReceipts(t, db, expectation, 1)
	directory := t.TempDir()
	report := filepath.Join(directory, "migration.json")
	t.Setenv("QWQ_STORAGE_MIGRATION_MODE", QuiescedAtomicStorageMigrationMode)
	t.Setenv("QWQ_CONTENT_RELEASE_STATE_QUIESCED", ContentReleaseStateQuiescedConfirmation)
	args := []string{
		"--mongo-uri", testMongoURI, "--database", db.Name(),
		"--env", expectation.Environment, "--source-owner", expectation.SourceOwner,
		"--expected-release-id", expectation.ReleaseID,
		"--expected-manifest-digest", expectation.ManifestDigest,
		"--expected-release-class", expectation.ReleaseClass,
		"--expected-projection-version", "17",
		"--expected-activated-at", expectation.ActivatedAt.Format(time.RFC3339Nano),
		"--expected-legacy-index-set", LegacyReleaseStateIndexSetV1,
		"--expected-legacy-receipt-index-set", LegacyReleaseStageReceiptIndexSetV1,
		"--expected-receipt-count", "5",
		"--report", report,
	}
	if err := RunLegacyReleaseStateMigration(context.Background(), args); err != nil {
		t.Fatalf("run migration command: %v", err)
	}
	raw, err := os.ReadFile(report)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(raw), testMongoURI) || strings.Contains(string(raw), "mongo-uri") {
		t.Fatalf("migration receipt leaked Mongo URI: %s", raw)
	}
	var receipt ContentLegacyReleaseStateMigrationReceipt
	if err := json.Unmarshal(raw, &receipt); err != nil {
		t.Fatal(err)
	}
	if receipt.Schema != ContentLegacyReleaseStateMigrationReceiptSchema || receipt.Status != "migrated" ||
		receipt.Database != db.Name() || receipt.ReleaseID != expectation.ReleaseID || receipt.Revision != 1 ||
		receipt.LegacyIndexSetDigest != LegacyReleaseStateExpectedIndexDigest() ||
		receipt.AfterIndexSetDigest != CurrentReleaseStateExpectedIndexDigest() ||
		receipt.LegacyReceiptIndexSetDigest != LegacyReleaseStageReceiptExpectedIndexDigest() ||
		receipt.AfterReceiptIndexSetDigest != CurrentReleaseStageReceiptExpectedIndexDigest() ||
		receipt.ReceiptCount != 5 || receipt.BeforeReceiptRowSetDigest == receipt.AfterReceiptRowSetDigest ||
		receipt.CandidateCollections != "empty" {
		t.Fatalf("migration receipt drifted: %+v", receipt)
	}
	args = append(args, "--allow-replay")
	if err := RunLegacyReleaseStateMigration(context.Background(), args); err == nil || !strings.Contains(err.Error(), "already exists") {
		t.Fatalf("existing create-once receipt was not rejected before replay: %v", err)
	}
	replayReport := filepath.Join(directory, "replay.json")
	for index := range args {
		if args[index] == "--report" {
			args[index+1] = replayReport
		}
	}
	if err := RunLegacyReleaseStateMigration(context.Background(), args); err != nil {
		t.Fatalf("run explicit migration replay: %v", err)
	}
	var replay ContentLegacyReleaseStateMigrationReceipt
	replayRaw, err := os.ReadFile(replayReport)
	if err != nil || json.Unmarshal(replayRaw, &replay) != nil || replay.Status != "replayed" || len(replay.Steps) != 0 {
		t.Fatalf("migration replay receipt=%s err=%v", replayRaw, err)
	}
}

func TestMongoLegacyReleaseStateMigrationRejectsCandidateAmbiguityAndDriftWithoutMutation(t *testing.T) {
	tests := []struct {
		name   string
		mutate func(*testing.T, *mongo.Database, LegacyReleaseStateMigrationExpectation)
		want   string
	}{
		{
			name: "candidate collection is non-empty",
			mutate: func(t *testing.T, db *mongo.Database, expectation LegacyReleaseStateMigrationExpectation) {
				if _, err := db.Collection("data_release_candidate_posts").InsertOne(context.Background(), bson.M{
					"environment": expectation.Environment, "releaseId": "candidate",
				}); err != nil {
					t.Fatal(err)
				}
			},
			want: "requires empty candidate collections",
		},
		{
			name: "second state row",
			mutate: func(t *testing.T, db *mongo.Database, expectation LegacyReleaseStateMigrationExpectation) {
				if _, err := db.Collection("data_release_state").InsertOne(context.Background(), bson.M{
					"environment": "beta", "sourceOwner": "qwq_data", "releaseId": "other",
					"activeReleaseId": "other", "manifestDigest": "sha256:" + strings.Repeat("b", 64),
					"status": "active", "releaseClass": "research", "projectionVersion": 1,
					"activatedAt": expectation.ActivatedAt,
				}); err != nil {
					t.Fatal(err)
				}
			},
			want: "exactly one data_release_state document",
		},
		{
			name: "unexpected document field",
			mutate: func(t *testing.T, db *mongo.Database, _ LegacyReleaseStateMigrationExpectation) {
				if _, err := db.Collection("data_release_state").UpdateOne(context.Background(), bson.D{}, bson.M{"$set": bson.M{"surprise": true}}); err != nil {
					t.Fatal(err)
				}
			},
			want: "unexpected field",
		},
		{
			name: "expected current drift",
			mutate: func(t *testing.T, db *mongo.Database, _ LegacyReleaseStateMigrationExpectation) {
				if _, err := db.Collection("data_release_state").UpdateOne(context.Background(), bson.D{}, bson.M{"$set": bson.M{"projectionVersion": int64(18)}}); err != nil {
					t.Fatal(err)
				}
			},
			want: "differs from exact expected current binding",
		},
		{
			name: "index definition drift",
			mutate: func(t *testing.T, db *mongo.Database, _ LegacyReleaseStateMigrationExpectation) {
				ctx := context.Background()
				if err := db.Collection("data_release_state").Indexes().DropOne(ctx, "idx_data_release_state_active_pointer"); err != nil {
					t.Fatal(err)
				}
				if _, err := db.Collection("data_release_state").Indexes().CreateOne(ctx, mongo.IndexModel{
					Keys:    bson.D{{Key: "environment", Value: 1}},
					Options: options.Index().SetName("idx_data_release_state_active_pointer"),
				}); err != nil {
					t.Fatal(err)
				}
			},
			want: "index definition drifted",
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			db, cleanup := testDB(t)
			defer cleanup()
			expectation := legacyReleaseStateExpectation()
			seedLegacyReleaseState(t, db, expectation)
			seedLegacyReleaseStageReceipts(t, db, expectation, 1)
			test.mutate(t, db, expectation)
			_, err := MigrateLegacyContentReleaseState(context.Background(), db, expectation)
			if err == nil || !strings.Contains(err.Error(), test.want) {
				t.Fatalf("migration error=%v want substring %q", err, test.want)
			}
			var unchanged bson.M
			if err := db.Collection("data_release_state").FindOne(context.Background(), bson.M{"releaseId": expectation.ReleaseID}).Decode(&unchanged); err != nil {
				t.Fatal(err)
			}
			if _, hasKind := unchanged["kind"]; hasKind {
				t.Fatalf("rejected migration changed legacy row: %#v", unchanged)
			}
		})
	}
}

func TestMongoLegacyReleaseStateMigrationResumesAfterStateOnlyCrash(t *testing.T) {
	db, cleanup := testDB(t)
	defer cleanup()
	ctx := context.Background()
	expectation := legacyReleaseStateExpectation()
	expectation.ExpectedReceiptCount = 15
	seedLegacyReleaseState(t, db, expectation)
	legacyReceipts := seedLegacyReleaseStageReceipts(t, db, expectation, 3)

	if _, err := db.Collection("data_release_state").UpdateOne(ctx, bson.D{}, bson.M{"$set": bson.M{"kind": "active_pointer", "revision": int64(1)}}); err != nil {
		t.Fatal(err)
	}
	state := db.Collection("data_release_state")
	if _, err := state.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{{Key: "environment", Value: 1}, {Key: "sourceOwner", Value: 1}, {Key: "kind", Value: 1}},
		Options: options.Index().SetName("uq_data_release_state_active_pointer").SetUnique(true).
			SetPartialFilterExpression(bson.D{{Key: "kind", Value: "active_pointer"}}),
	}); err != nil {
		t.Fatal(err)
	}
	if err := state.Indexes().DropOne(ctx, "idx_data_release_state_active_pointer"); err != nil {
		t.Fatal(err)
	}
	if err := state.Indexes().DropOne(ctx, "uq_data_release_state_environment_candidate"); err != nil {
		t.Fatal(err)
	}
	if _, err := state.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{{Key: "environment", Value: 1}, {Key: "sourceOwner", Value: 1}, {Key: "kind", Value: 1}, {Key: "releaseId", Value: 1}, {Key: "manifestDigest", Value: 1}},
		Options: options.Index().SetName("uq_data_release_state_environment_candidate").SetUnique(true).
			SetPartialFilterExpression(bson.D{{Key: "kind", Value: "candidate"}}),
	}); err != nil {
		t.Fatal(err)
	}

	expectation.AllowReplay = true
	result, err := MigrateLegacyContentReleaseState(ctx, db, expectation)
	if err != nil {
		t.Fatalf("resume state-only crash: %v", err)
	}
	if result.Status != "resumed" || result.ReceiptCount != 15 || result.BeforeIndexSetDigest != CurrentReleaseStateExpectedIndexDigest() ||
		result.BeforeReceiptIndexSetDigest != LegacyReleaseStageReceiptExpectedIndexDigest() {
		t.Fatalf("state-only resume result=%+v", result)
	}
	assertReleaseStageReceiptMigration(t, db, legacyReceipts, expectation, 15)
}

func TestMongoLegacyReleaseStateMigrationRejectsReceiptDriftWithoutMutation(t *testing.T) {
	tests := []struct {
		name   string
		mutate func(*testing.T, *mongo.Database, LegacyReleaseStateMigrationExpectation)
		want   string
	}{
		{name: "unexpected environment", mutate: func(t *testing.T, db *mongo.Database, _ LegacyReleaseStateMigrationExpectation) {
			if _, err := db.Collection("data_release_stage_receipts").UpdateOne(context.Background(), bson.D{}, bson.M{"$set": bson.M{"environment": "beta"}}); err != nil {
				t.Fatal(err)
			}
		}, want: "environment differs"},
		{name: "mixed owner", mutate: func(t *testing.T, db *mongo.Database, _ LegacyReleaseStateMigrationExpectation) {
			if _, err := db.Collection("data_release_stage_receipts").UpdateOne(context.Background(), bson.D{}, bson.M{"$set": bson.M{"sourceOwner": "other_owner"}}); err != nil {
				t.Fatal(err)
			}
		}, want: "mixed owner"},
		{name: "ambiguous release tuple", mutate: func(t *testing.T, db *mongo.Database, _ LegacyReleaseStateMigrationExpectation) {
			var row bson.M
			if err := db.Collection("data_release_stage_receipts").FindOne(context.Background(), bson.M{"stage": "active"}).Decode(&row); err != nil {
				t.Fatal(err)
			}
			delete(row, "_id")
			row["manifestDigest"] = "sha256:" + strings.Repeat("f", 64)
			row["attemptId"] = row["environment"].(string) + ":" + row["releaseId"].(string) + ":" + strconv.FormatInt(time.Now().UnixNano(), 10)
			if _, err := db.Collection("data_release_stage_receipts").InsertOne(context.Background(), row); err != nil {
				t.Fatal(err)
			}
		}, want: "tuple is ambiguous"},
		{name: "unexpected shape", mutate: func(t *testing.T, db *mongo.Database, _ LegacyReleaseStateMigrationExpectation) {
			if _, err := db.Collection("data_release_stage_receipts").UpdateOne(context.Background(), bson.D{}, bson.M{"$set": bson.M{"surprise": true}}); err != nil {
				t.Fatal(err)
			}
		}, want: "unexpected field"},
		{name: "owner binding collision", mutate: func(t *testing.T, db *mongo.Database, expectation LegacyReleaseStateMigrationExpectation) {
			receipts := db.Collection("data_release_stage_receipts")
			if err := receipts.Indexes().DropOne(context.Background(), "uq_data_release_stage_receipt_attempt"); err != nil {
				t.Fatal(err)
			}
			var row bson.M
			if err := receipts.FindOne(context.Background(), bson.D{}).Decode(&row); err != nil {
				t.Fatal(err)
			}
			delete(row, "_id")
			row["sourceOwner"] = expectation.SourceOwner
			if _, err := receipts.InsertOne(context.Background(), row); err != nil {
				t.Fatal(err)
			}
			expectation.ExpectedReceiptCount++
		}, want: "would collide"},
		{name: "row count drift", mutate: func(t *testing.T, db *mongo.Database, _ LegacyReleaseStateMigrationExpectation) {
			if _, err := db.Collection("data_release_stage_receipts").DeleteOne(context.Background(), bson.D{}); err != nil {
				t.Fatal(err)
			}
		}, want: "row count differs"},
		{name: "index drift", mutate: func(t *testing.T, db *mongo.Database, _ LegacyReleaseStateMigrationExpectation) {
			ctx := context.Background()
			receipts := db.Collection("data_release_stage_receipts")
			if err := receipts.Indexes().DropOne(ctx, "idx_data_release_stage_receipt_timeline"); err != nil {
				t.Fatal(err)
			}
			if _, err := receipts.Indexes().CreateOne(ctx, mongo.IndexModel{Keys: bson.D{{Key: "environment", Value: 1}}, Options: options.Index().SetName("idx_data_release_stage_receipt_timeline")}); err != nil {
				t.Fatal(err)
			}
		}, want: "timeline index definition drifted"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			db, cleanup := testDB(t)
			defer cleanup()
			expectation := legacyReleaseStateExpectation()
			seedLegacyReleaseState(t, db, expectation)
			seedLegacyReleaseStageReceipts(t, db, expectation, 1)
			test.mutate(t, db, expectation)
			if test.name == "owner binding collision" {
				expectation.ExpectedReceiptCount++
			}
			stateBefore := rawDocumentClosure(t, db.Collection("data_release_state"), bson.M{})
			receiptsBefore := rawDocumentClosure(t, db.Collection("data_release_stage_receipts"), bson.M{})
			stateIndexesBefore := rawIndexClosure(t, db.Collection("data_release_state"))
			receiptIndexesBefore := rawIndexClosure(t, db.Collection("data_release_stage_receipts"))
			_, err := MigrateLegacyContentReleaseState(context.Background(), db, expectation)
			if err == nil || !strings.Contains(err.Error(), test.want) {
				t.Fatalf("migration error=%v want=%q", err, test.want)
			}
			if !equalRawDocuments(stateBefore, rawDocumentClosure(t, db.Collection("data_release_state"), bson.M{})) ||
				!equalRawDocuments(receiptsBefore, rawDocumentClosure(t, db.Collection("data_release_stage_receipts"), bson.M{})) ||
				!equalRawDocuments(stateIndexesBefore, rawIndexClosure(t, db.Collection("data_release_state"))) ||
				!equalRawDocuments(receiptIndexesBefore, rawIndexClosure(t, db.Collection("data_release_stage_receipts"))) {
				t.Fatal("receipt drift rejection mutated documents or indexes")
			}
		})
	}
}

func TestMongoLegacyReleaseStateMigrationResumesReceiptDDL(t *testing.T) {
	db, cleanup := testDB(t)
	defer cleanup()
	ctx := context.Background()
	expectation := legacyReleaseStateExpectation()
	seedLegacyReleaseState(t, db, expectation)
	seedLegacyReleaseStageReceipts(t, db, expectation, 1)

	if _, err := db.Collection("data_release_state").UpdateOne(ctx, bson.D{}, bson.M{"$set": bson.M{"kind": "active_pointer", "revision": int64(1)}}); err != nil {
		t.Fatal(err)
	}
	state := db.Collection("data_release_state")
	if _, err := state.Indexes().CreateOne(ctx, mongo.IndexModel{Keys: bson.D{{Key: "environment", Value: 1}, {Key: "sourceOwner", Value: 1}, {Key: "kind", Value: 1}}, Options: options.Index().SetName("uq_data_release_state_active_pointer").SetUnique(true).SetPartialFilterExpression(bson.D{{Key: "kind", Value: "active_pointer"}})}); err != nil {
		t.Fatal(err)
	}
	if err := state.Indexes().DropOne(ctx, "idx_data_release_state_active_pointer"); err != nil {
		t.Fatal(err)
	}
	if err := state.Indexes().DropOne(ctx, "uq_data_release_state_environment_candidate"); err != nil {
		t.Fatal(err)
	}
	if _, err := state.Indexes().CreateOne(ctx, mongo.IndexModel{Keys: bson.D{{Key: "environment", Value: 1}, {Key: "sourceOwner", Value: 1}, {Key: "kind", Value: 1}, {Key: "releaseId", Value: 1}, {Key: "manifestDigest", Value: 1}}, Options: options.Index().SetName("uq_data_release_state_environment_candidate").SetUnique(true).SetPartialFilterExpression(bson.D{{Key: "kind", Value: "candidate"}})}); err != nil {
		t.Fatal(err)
	}
	receipts := db.Collection("data_release_stage_receipts")
	if _, err := receipts.UpdateMany(ctx, bson.M{"sourceOwner": bson.M{"$exists": false}}, bson.M{"$set": bson.M{"sourceOwner": expectation.SourceOwner}}); err != nil {
		t.Fatal(err)
	}
	if _, err := receipts.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "environment", Value: 1}, {Key: "sourceOwner", Value: 1}, {Key: "releaseId", Value: 1}, {Key: "manifestDigest", Value: 1}, {Key: "stage", Value: 1}, {Key: "attemptId", Value: 1}, {Key: "_id", Value: 1}},
		Options: options.Index().SetName("uq_data_release_stage_receipt_attempt__source_owner_migration"),
	}); err != nil {
		t.Fatal(err)
	}

	expectation.AllowReplay = true
	result, err := MigrateLegacyContentReleaseState(ctx, db, expectation)
	if err != nil {
		t.Fatalf("resume receipt DDL: %v", err)
	}
	if result.Status != "resumed" || result.ReceiptCount != 5 || result.AfterReceiptIndexSetDigest != CurrentReleaseStageReceiptExpectedIndexDigest() {
		t.Fatalf("receipt DDL resume=%+v", result)
	}
	assertReleaseStageReceiptIndexNames(t, db, []string{"_id_", "idx_data_release_stage_receipt_timeline", "uq_data_release_stage_receipt_attempt"})
}

func TestMongoLegacyReleaseStateMigrationResumesRecognizedDDLPhases(t *testing.T) {
	db, cleanup := testDB(t)
	defer cleanup()
	ctx := context.Background()
	expectation := legacyReleaseStateExpectation()
	seedLegacyReleaseState(t, db, expectation)
	seedLegacyReleaseStageReceipts(t, db, expectation, 1)
	if _, err := db.Collection("data_release_state").UpdateOne(ctx, bson.D{}, bson.M{"$set": bson.M{"kind": "active_pointer", "revision": int64(1)}}); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Collection("data_release_stage_receipts").UpdateOne(ctx, bson.D{}, bson.M{"$set": bson.M{"sourceOwner": expectation.SourceOwner}}); err != nil {
		t.Fatal(err)
	}
	if _, err := db.Collection("data_release_stage_receipts").Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "environment", Value: 1}, {Key: "sourceOwner", Value: 1}, {Key: "releaseId", Value: 1}, {Key: "manifestDigest", Value: 1}, {Key: "stage", Value: 1}, {Key: "attemptId", Value: 1}, {Key: "_id", Value: 1}},
		Options: options.Index().SetName("uq_data_release_stage_receipt_attempt__source_owner_migration"),
	}); err != nil {
		t.Fatal(err)
	}
	expectation.AllowReplay = true
	result, err := MigrateLegacyContentReleaseState(ctx, db, expectation)
	if err != nil {
		t.Fatalf("resume migration after document CAS: %v", err)
	}
	if result.Status != "resumed" || result.ReceiptCount != 5 {
		t.Fatalf("resume result=%+v", result)
	}
	assertReleaseStateIndexNames(t, db, []string{"_id_", "uq_data_release_state_active_pointer", "uq_data_release_state_environment_candidate"})
}

func rawIndexClosure(t *testing.T, collection *mongo.Collection) []bson.Raw {
	t.Helper()
	cursor, err := collection.Indexes().List(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	defer cursor.Close(context.Background())
	var indexes []bson.Raw
	if err := cursor.All(context.Background(), &indexes); err != nil {
		t.Fatal(err)
	}
	sort.Slice(indexes, func(left, right int) bool {
		return indexes[left].Lookup("name").StringValue() < indexes[right].Lookup("name").StringValue()
	})
	return indexes
}

func assertReleaseStageReceiptMigration(t *testing.T, db *mongo.Database, before []bson.Raw, expectation LegacyReleaseStateMigrationExpectation, count int64) {
	t.Helper()
	ctx := context.Background()
	receipts := db.Collection("data_release_stage_receipts")
	if got, err := receipts.CountDocuments(ctx, bson.M{"environment": expectation.Environment, "sourceOwner": expectation.SourceOwner}); err != nil || got != count {
		t.Fatalf("current release-stage receipt count=%d err=%v want=%d", got, err, count)
	}
	if got, err := receipts.CountDocuments(ctx, bson.M{"sourceOwner": bson.M{"$exists": false}}); err != nil || got != 0 {
		t.Fatalf("legacy release-stage receipts remain=%d err=%v", got, err)
	}
	assertReleaseStageReceiptIndexNames(t, db, []string{"_id_", "idx_data_release_stage_receipt_timeline", "uq_data_release_stage_receipt_attempt"})
	if len(before) != int(count) {
		t.Fatalf("seeded release-stage receipt count=%d want=%d", len(before), count)
	}
	for _, raw := range before {
		id := raw.Lookup("_id")
		var after bson.Raw
		if err := receipts.FindOne(ctx, bson.M{"_id": id}).Decode(&after); err != nil {
			t.Fatal(err)
		}
		if after.Lookup("sourceOwner").StringValue() != expectation.SourceOwner {
			t.Fatalf("receipt owner was not migrated: %s", after)
		}
	}
}

func assertReleaseStageReceiptIndexNames(t *testing.T, db *mongo.Database, want []string) {
	t.Helper()
	cursor, err := db.Collection("data_release_stage_receipts").Indexes().List(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	var indexes []struct {
		Name string `bson:"name"`
	}
	if err := cursor.All(context.Background(), &indexes); err != nil {
		t.Fatal(err)
	}
	got := make([]string, 0, len(indexes))
	for _, index := range indexes {
		got = append(got, index.Name)
	}
	sort.Strings(got)
	sort.Strings(want)
	if strings.Join(got, ",") != strings.Join(want, ",") {
		t.Fatalf("release receipt indexes=%v want=%v", got, want)
	}
}

func assertReleaseStateIndexNames(t *testing.T, db *mongo.Database, want []string) {
	t.Helper()
	cursor, err := db.Collection("data_release_state").Indexes().List(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	var indexes []struct {
		Name string `bson:"name"`
	}
	if err := cursor.All(context.Background(), &indexes); err != nil {
		t.Fatal(err)
	}
	got := make([]string, 0, len(indexes))
	for _, index := range indexes {
		got = append(got, index.Name)
	}
	if strings.Join(got, ",") != strings.Join(want, ",") {
		t.Fatalf("release state indexes=%v want=%v", got, want)
	}
}

func numericInt64(value any) int64 {
	switch typed := value.(type) {
	case int32:
		return int64(typed)
	case int64:
		return typed
	case int:
		return int64(typed)
	default:
		return -1
	}
}

func bsonValueEquivalent(left, right any) bool {
	leftBytes, leftErr := bson.MarshalExtJSON(bson.M{"value": left}, true, false)
	rightBytes, rightErr := bson.MarshalExtJSON(bson.M{"value": right}, true, false)
	if leftErr != nil || rightErr != nil {
		return false
	}
	var leftValue, rightValue any
	if json.Unmarshal(leftBytes, &leftValue) != nil || json.Unmarshal(rightBytes, &rightValue) != nil {
		return false
	}
	return fmt.Sprint(leftValue) == fmt.Sprint(rightValue)
}
