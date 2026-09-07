package releaseimport

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"sort"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	postgenerated "quwoquan_service/services/content-service/generated/content/post"
)

const (
	candidateCollectionName = "posts_candidate"
	// verified evidence 缺失是 activate 阶段编排错误，用 importer typed blocker；
	// 候选缺失/漂移则包装 content/post errors.yaml 声明的 worker-surface typed error。
	candidateVerificationRequired = "CONTENT.RELEASE.CANDIDATE_VERIFICATION_REQUIRED"
)

func candidateMissing(format string, args ...any) error {
	return fmt.Errorf("GATE_BLOCK %w: "+format, append([]any{postgenerated.ErrReleaseCandidateMissing}, args...)...)
}

func candidateDrift(format string, args ...any) error {
	return fmt.Errorf("GATE_BLOCK %w: "+format, append([]any{postgenerated.ErrReleaseCandidateDrift}, args...)...)
}

type ImportedReleaseStageResult struct {
	PostsStaged            int
	CandidateRevision      int64
	PreviousReleaseID      string
	PreviousManifestDigest string
	PreviousRevision       int64
}

type ImportedReleaseCandidateReadback struct {
	Environment       string
	SourceOwner       string
	ReleaseID         string
	ManifestDigest    string
	CandidateRevision int64
	PostIDs           []string
	SourceHashes      []string
	VerifiedAt        time.Time
}

func candidateDocumentID(environment string, opts ImportOptions, postID string) string {
	hash := sha256.Sum256([]byte(strings.Join([]string{
		strings.TrimSpace(environment), strings.TrimSpace(opts.SourceOwner),
		strings.TrimSpace(opts.ReleaseID), strings.TrimSpace(opts.ManifestDigest),
		strings.TrimSpace(postID),
	}, "\x00")))
	return "release_candidate_" + hex.EncodeToString(hash[:])
}

func ensureImportedCandidateIndexes(ctx context.Context, candidates *mongo.Collection) error {
	if candidates == nil {
		return fmt.Errorf("Content release candidate collection is required")
	}
	_, err := candidates.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "environment", Value: 1}, {Key: "sourceOwner", Value: 1},
				{Key: "releaseId", Value: 1}, {Key: "manifestDigest", Value: 1},
				{Key: "targetPostId", Value: 1},
			},
			Options: options.Index().SetName("uq_posts_candidate_release_post").SetUnique(true),
		},
		{
			Keys: bson.D{
				{Key: "environment", Value: 1}, {Key: "sourceOwner", Value: 1},
				{Key: "releaseId", Value: 1}, {Key: "manifestDigest", Value: 1},
				{Key: "candidateRevision", Value: 1},
			},
			Options: options.Index().SetName("idx_posts_candidate_readback"),
		},
	})
	if err != nil {
		return fmt.Errorf("ensure Content release candidate indexes: %w", err)
	}
	return nil
}

// StageImportedPostRelease materializes a private candidate closure. It never
// writes active Posts, lifecycle outbox facts, or the active pointer.
func StageImportedPostRelease(
	ctx context.Context,
	database *mongo.Database,
	environment string,
	posts []PostDoc,
	requestedAt time.Time,
	opts ImportOptions,
) (ImportedReleaseStageResult, error) {
	if database == nil {
		return ImportedReleaseStageResult{}, fmt.Errorf("content release stage database is required")
	}
	environment = strings.TrimSpace(environment)
	opts = NormalizeImportOptions(opts)
	if environment == "" || strings.TrimSpace(opts.ManifestDigest) == "" || opts.ProjectionVersion <= 0 {
		return ImportedReleaseStageResult{}, fmt.Errorf("content release candidate identity is incomplete")
	}
	requestedAt = requestedAt.UTC().Truncate(time.Millisecond)
	if requestedAt.IsZero() {
		requestedAt = time.Now().UTC().Truncate(time.Millisecond)
	}
	if err := EnsureImportedReleaseIndexes(ctx, database); err != nil {
		return ImportedReleaseStageResult{}, err
	}
	candidates := database.Collection(candidateCollectionName)
	if err := ensureImportedCandidateIndexes(ctx, candidates); err != nil {
		return ImportedReleaseStageResult{}, err
	}
	state := database.Collection("data_release_state")
	receipts := database.Collection("data_release_stage_receipts")
	attemptID := releaseAttemptID(environment, opts, requestedAt)
	started := time.Now()
	session, err := database.Client().StartSession()
	if err != nil {
		return ImportedReleaseStageResult{}, fmt.Errorf("start content release stage session: %w", err)
	}
	defer session.EndSession(ctx)

	result := ImportedReleaseStageResult{CandidateRevision: opts.ProjectionVersion}
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		var current importedReleaseState
		stateErr := state.FindOne(txCtx, bson.M{
			"environment": environment, "sourceOwner": opts.SourceOwner,
		}).Decode(&current)
		if stateErr != nil && stateErr != mongo.ErrNoDocuments {
			return nil, fmt.Errorf("read previous active Data release: %w", stateErr)
		}
		if stateErr == nil {
			if current.Revision <= 0 || current.SourceVersion <= 0 || current.Status != "active" {
				return nil, fmt.Errorf("GATE_BLOCK CONTENT.RELEASE.ACTIVE_POINTER_MIGRATION_REQUIRED")
			}
			result.PreviousReleaseID = strings.TrimSpace(current.ActiveReleaseID)
			result.PreviousManifestDigest = strings.TrimSpace(current.ManifestDigest)
			result.PreviousRevision = current.Revision
		}
		if err := appendReleaseStageReceipt(txCtx, receipts, releaseStageReceipt{
			Environment: environment, ReleaseID: opts.ReleaseID, ManifestDigest: opts.ManifestDigest,
			Stage: "prepared", AttemptID: attemptID, Status: "passed", RecordedAt: requestedAt,
			AttemptedCount: len(posts), SuccessCount: len(posts),
			Checkpoint: "canonical-input-validated", CandidateRevision: opts.ProjectionVersion,
		}); err != nil {
			return nil, err
		}
		for _, post := range posts {
			document, documentErr := importedPostDocument(post, requestedAt, opts, "candidate")
			if documentErr != nil {
				return nil, documentErr
			}
			postID := RuntimePostID(post.ContentID)
			document["_id"] = candidateDocumentID(environment, opts, postID)
			document["targetPostId"] = postID
			document["environment"] = environment
			document["candidateRevision"] = opts.ProjectionVersion
			document["stagedAt"] = requestedAt
			if _, updateErr := candidates.ReplaceOne(
				txCtx,
				bson.M{"_id": document["_id"]},
				document,
				options.Replace().SetUpsert(true),
			); updateErr != nil {
				return nil, fmt.Errorf("stage imported Post %s: %w", postID, updateErr)
			}
			result.PostsStaged++
		}
		for _, stage := range []struct{ name, checkpoint string }{
			{name: "imported", checkpoint: "posts-candidate-materialized"},
			{name: "projected", checkpoint: "candidate-readback-available"},
		} {
			if err := appendReleaseStageReceipt(txCtx, receipts, releaseStageReceipt{
				Environment: environment, ReleaseID: opts.ReleaseID, ManifestDigest: opts.ManifestDigest,
				Stage: stage.name, AttemptID: attemptID, Status: "passed", RecordedAt: requestedAt,
				DurationMs: releaseStageDurationMs(started), AttemptedCount: len(posts),
				SuccessCount: result.PostsStaged, Checkpoint: stage.checkpoint,
				CandidateRevision: opts.ProjectionVersion,
			}); err != nil {
				return nil, err
			}
		}
		return nil, nil
	})
	if err != nil {
		_ = appendReleaseStageReceipt(ctx, receipts, releaseStageReceipt{
			Environment: environment, ReleaseID: opts.ReleaseID, ManifestDigest: opts.ManifestDigest,
			Stage: "imported", AttemptID: attemptID, Status: "failed", RecordedAt: time.Now().UTC(),
			DurationMs: releaseStageDurationMs(started), AttemptedCount: len(posts),
			Checkpoint: "candidate-transaction-aborted", FirstTypedBlocker: releaseImportFailedBlocker,
			CandidateRevision: opts.ProjectionVersion,
		})
		return ImportedReleaseStageResult{}, err
	}
	return result, nil
}

func candidateFilter(environment string, opts ImportOptions, candidateRevision int64) bson.M {
	return bson.M{
		"environment": strings.TrimSpace(environment), "sourceOwner": opts.SourceOwner,
		"releaseId": opts.ReleaseID, "manifestDigest": opts.ManifestDigest,
		"candidateRevision": candidateRevision, "lifecycleStatus": "candidate",
	}
}

func readAndValidateImportedReleaseCandidate(
	ctx context.Context,
	candidates *mongo.Collection,
	environment string,
	posts []PostDoc,
	opts ImportOptions,
	candidateRevision int64,
) (ImportedReleaseCandidateReadback, []bson.M, error) {
	if candidateRevision <= 0 {
		return ImportedReleaseCandidateReadback{}, nil, candidateMissing("candidateRevision must be positive")
	}
	cursor, err := candidates.Find(ctx, candidateFilter(environment, opts, candidateRevision), options.Find().SetSort(bson.D{{Key: "targetPostId", Value: 1}}))
	if err != nil {
		return ImportedReleaseCandidateReadback{}, nil, err
	}
	defer cursor.Close(ctx)
	var documents []bson.M
	if err := cursor.All(ctx, &documents); err != nil {
		return ImportedReleaseCandidateReadback{}, nil, err
	}
	expected := make(map[string]string, len(posts))
	for _, post := range posts {
		expected[RuntimePostID(post.ContentID)] = sourceHash(post)
	}
	if len(documents) != len(expected) {
		return ImportedReleaseCandidateReadback{}, nil, candidateMissing("expected=%d actual=%d", len(expected), len(documents))
	}
	// 零候选的 EMPTY_BASELINE release 合法；切片必须序列化为 []，不能是 null。
	readback := ImportedReleaseCandidateReadback{
		Environment: strings.TrimSpace(environment), SourceOwner: opts.SourceOwner,
		ReleaseID: opts.ReleaseID, ManifestDigest: opts.ManifestDigest,
		CandidateRevision: candidateRevision,
		PostIDs:           []string{}, SourceHashes: []string{},
	}
	for _, document := range documents {
		postID := strings.TrimSpace(candidateStringValue(document["targetPostId"]))
		hash := strings.TrimSpace(candidateStringValue(document["sourceHash"]))
		want, exists := expected[postID]
		if !exists || want != hash {
			return ImportedReleaseCandidateReadback{}, nil, candidateDrift("postId=%q", postID)
		}
		readback.PostIDs = append(readback.PostIDs, postID)
		readback.SourceHashes = append(readback.SourceHashes, hash)
	}
	sort.Strings(readback.PostIDs)
	sort.Strings(readback.SourceHashes)
	return readback, documents, nil
}

// VerifyImportedPostReleaseCandidate performs storage readback against the
// private candidate identity and persists the evidence required by activate.
func VerifyImportedPostReleaseCandidate(
	ctx context.Context,
	database *mongo.Database,
	environment string,
	posts []PostDoc,
	requestedAt time.Time,
	opts ImportOptions,
	candidateRevision int64,
) (ImportedReleaseCandidateReadback, error) {
	if database == nil {
		return ImportedReleaseCandidateReadback{}, fmt.Errorf("content release verify database is required")
	}
	opts = NormalizeImportOptions(opts)
	requestedAt = requestedAt.UTC().Truncate(time.Millisecond)
	if requestedAt.IsZero() {
		requestedAt = time.Now().UTC().Truncate(time.Millisecond)
	}
	candidates := database.Collection(candidateCollectionName)
	if err := ensureImportedCandidateIndexes(ctx, candidates); err != nil {
		return ImportedReleaseCandidateReadback{}, err
	}
	readback, _, err := readAndValidateImportedReleaseCandidate(
		ctx, candidates, environment, posts, opts, candidateRevision,
	)
	if err != nil {
		return ImportedReleaseCandidateReadback{}, err
	}
	readback.VerifiedAt = requestedAt
	attemptID := fmt.Sprintf("%s:%s:verify:%d", strings.TrimSpace(environment), opts.ReleaseID, requestedAt.UnixNano())
	if err := appendReleaseStageReceipt(ctx, database.Collection("data_release_stage_receipts"), releaseStageReceipt{
		Environment: strings.TrimSpace(environment), ReleaseID: opts.ReleaseID,
		ManifestDigest: opts.ManifestDigest, Stage: "verified", AttemptID: attemptID,
		Status: "passed", RecordedAt: requestedAt, AttemptedCount: len(posts),
		SuccessCount: len(readback.PostIDs), Checkpoint: "candidate-identity-and-counts-validated",
		CandidateRevision: candidateRevision,
	}); err != nil {
		return ImportedReleaseCandidateReadback{}, err
	}
	return readback, nil
}

func requireVerifiedImportedReleaseCandidate(
	ctx context.Context,
	receipts *mongo.Collection,
	environment string,
	opts ImportOptions,
	candidateRevision int64,
) error {
	var receipt releaseStageReceipt
	err := receipts.FindOne(ctx, bson.M{
		"environment": strings.TrimSpace(environment), "releaseId": opts.ReleaseID,
		"manifestDigest": opts.ManifestDigest, "stage": "verified", "status": "passed",
		"candidateRevision": candidateRevision,
	}, options.FindOne().SetSort(bson.D{{Key: "recordedAt", Value: -1}})).Decode(&receipt)
	if err == mongo.ErrNoDocuments {
		return fmt.Errorf("GATE_BLOCK %s: release=%q candidateRevision=%d", candidateVerificationRequired, opts.ReleaseID, candidateRevision)
	}
	if err != nil {
		return fmt.Errorf("read verified Content release candidate evidence: %w", err)
	}
	return nil
}

func activateCandidatePosts(
	ctx context.Context,
	postsCollection *mongo.Collection,
	candidates []bson.M,
	expected []PostDoc,
	activatedAt time.Time,
	opts ImportOptions,
) (int, error) {
	for _, post := range expected {
		if err := migrateImportedPostIdentity(ctx, postsCollection, post.ContentID, post.PostRef, RuntimePostID(post.ContentID), opts); err != nil {
			return 0, err
		}
	}
	upserted := 0
	for _, candidate := range candidates {
		postID := strings.TrimSpace(candidateStringValue(candidate["targetPostId"]))
		if postID == "" {
			return upserted, candidateDrift("candidate targetPostId is empty")
		}
		document := bson.M{}
		for key, value := range candidate {
			switch key {
			case "_id", "targetPostId", "environment", "candidateRevision", "stagedAt":
				continue
			default:
				document[key] = value
			}
		}
		document["lifecycleStatus"] = "active"
		document["releaseUpdatedAt"] = activatedAt
		// 候选阶段的 version 是 candidateRevision；active Post 必须与本次激活写入
		// pointer/outbox 的 sourceVersion 完全一致，否则 replay closure 校验会漂移。
		document["version"] = opts.ProjectionVersion
		if _, err := postsCollection.UpdateOne(
			ctx, bson.M{"_id": postID},
			bson.M{"$set": document, "$setOnInsert": bson.M{"_id": postID}},
			options.UpdateOne().SetUpsert(true),
		); err != nil {
			return upserted, err
		}
		upserted++
	}
	return upserted, nil
}

// ActivateImportedPostRelease atomically promotes an exactly verified candidate
// closure into active Posts/outbox/pointer state.
func ActivateImportedPostRelease(
	ctx context.Context,
	database *mongo.Database,
	environment string,
	posts []PostDoc,
	requestedAt time.Time,
	opts ImportOptions,
	candidateRevision int64,
) (ImportedReleaseApplyResult, error) {
	if database == nil {
		return ImportedReleaseApplyResult{}, fmt.Errorf("content release activate database is required")
	}
	environment = strings.TrimSpace(environment)
	opts = NormalizeImportOptions(opts)
	if environment == "" || strings.TrimSpace(opts.ManifestDigest) == "" || opts.ExpectedRevision < 0 {
		return ImportedReleaseApplyResult{}, fmt.Errorf("content release activation identity or expectedRevision is incomplete")
	}
	requestedAt = requestedAt.UTC().Truncate(time.Millisecond)
	if requestedAt.IsZero() {
		requestedAt = time.Now().UTC().Truncate(time.Millisecond)
	}
	postsCollection := database.Collection("posts")
	outbox := database.Collection("content_outbox")
	sequences := database.Collection("content_outbox_sequences")
	state := database.Collection("data_release_state")
	receipts := database.Collection("data_release_stage_receipts")
	candidatesCollection := database.Collection(candidateCollectionName)
	if err := EnsureImportedReleaseIndexes(ctx, database); err != nil {
		return ImportedReleaseApplyResult{}, err
	}
	if err := ensureImportedCandidateIndexes(ctx, candidatesCollection); err != nil {
		return ImportedReleaseApplyResult{}, err
	}
	session, err := database.Client().StartSession()
	if err != nil {
		return ImportedReleaseApplyResult{}, fmt.Errorf("start content release activation session: %w", err)
	}
	defer session.EndSession(ctx)
	attemptID := fmt.Sprintf("%s:%s:activate:%d", environment, opts.ReleaseID, requestedAt.UnixNano())
	started := time.Now()
	var result ImportedReleaseApplyResult
	_, err = session.WithTransaction(ctx, func(txCtx context.Context) (any, error) {
		// 先判 pointer：已 active 的同一 release 其候选已在激活后清理，若先读候选会把
		// "已激活"误报成 candidate_missing，操作者就找不到 replay/repair 轨道。
		resolved, currentRevision, activatedAt, replayed, previousReleaseID, previousManifestDigest, err := resolveImportedProjectionVersion(txCtx, state, environment, opts, requestedAt)
		if err != nil {
			return nil, err
		}
		if replayed {
			return nil, fmt.Errorf("GATE_BLOCK CONTENT.RELEASE.CANDIDATE_ALREADY_ACTIVE: use the replay/repair rail")
		}
		if err := requireVerifiedImportedReleaseCandidate(txCtx, receipts, environment, opts, candidateRevision); err != nil {
			return nil, err
		}
		_, candidateDocuments, err := readAndValidateImportedReleaseCandidate(txCtx, candidatesCollection, environment, posts, opts, candidateRevision)
		if err != nil {
			return nil, err
		}
		opts.ProjectionVersion = resolved
		deletedPosts, err := MissingImportedPostSnapshots(txCtx, postsCollection, posts, opts, false, activatedAt)
		if err != nil {
			return nil, fmt.Errorf("resolve missing imported Posts: %w", err)
		}
		upserted, err := activateCandidatePosts(txCtx, postsCollection, candidateDocuments, posts, activatedAt, opts)
		if err != nil {
			return nil, fmt.Errorf("activate imported Post candidates: %w", err)
		}
		removed, err := ApplyMissingPostPolicy(txCtx, postsCollection, posts, activatedAt, opts)
		if err != nil {
			return nil, fmt.Errorf("apply imported Post removal policy: %w", err)
		}
		events, err := BuildImportedPostLifecycleEvents(posts, deletedPosts, opts, activatedAt)
		if err != nil {
			return nil, err
		}
		outboxResult, err := appendImportedPostOutbox(txCtx, outbox, sequences, events, opts, false)
		if err != nil {
			return nil, err
		}
		result = ImportedReleaseApplyResult{
			PostsUpserted: upserted, PostsRemoved: removed,
			PostDeletionEventsReady: len(deletedPosts), OutboxEventsReady: len(events),
			OutboxEventsAppended: outboxResult.Appended,
			OutboxEventsRepaired: len(outboxResult.Repairs), OutboxRepairAudits: outboxResult.Repairs,
			ProjectionVersion: resolved, Revision: currentRevision + 1,
			PreviousReleaseID: previousReleaseID, PreviousManifestDigest: previousManifestDigest,
		}
		if err := ValidateImportedReleaseApplyResult(result, len(posts)); err != nil {
			return nil, err
		}
		if err := UpsertReleaseState(txCtx, state, environment, opts, activatedAt, bson.M{
			"postsUpserted": upserted, "postsRemoved": removed,
		}); err != nil {
			return nil, fmt.Errorf("activate imported Data release: %w", err)
		}
		if err := appendReleaseStageReceipt(txCtx, receipts, releaseStageReceipt{
			Environment: environment, ReleaseID: opts.ReleaseID, ManifestDigest: opts.ManifestDigest,
			Stage: "active", AttemptID: attemptID, Status: "passed", RecordedAt: activatedAt,
			DurationMs: releaseStageDurationMs(started), AttemptedCount: len(posts),
			SuccessCount: upserted, Checkpoint: "candidate-posts-outbox-pointer-committed",
			CandidateRevision: candidateRevision,
		}); err != nil {
			return nil, err
		}
		return nil, nil
	})
	if err != nil {
		return ImportedReleaseApplyResult{}, err
	}
	// 候选只服务于本次激活；提交后按精确身份清理。清理失败不改变激活结果，
	// 残留候选也不会被任何读面消费，下次同身份 stage 会 ReplaceOne 覆盖。
	if _, cleanupErr := candidatesCollection.DeleteMany(
		ctx, candidateFilter(environment, opts, candidateRevision),
	); cleanupErr != nil {
		result.CandidateCleanupError = cleanupErr.Error()
	}
	return result, nil
}

func candidateStringValue(value any) string {
	text, _ := value.(string)
	return text
}
