// Command import 按 immutable release desired state 把 canonical objects 灌入运行库。
//
// release payload 是对象事实与选择集的唯一不可变输入；禁止 canonical publish、
// sample bundle fallback 与不带 release 的全树导入。
//
// 用法:
//
//	go run ./services/content-service/cmd/import \
//	  --release-root ../.qwq_output/data/releases/<releaseId> \
//	  --mongo-uri mongodb://localhost:27017 --env gamma
package releaseimport

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"os"
	"sort"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	runtimemedia "quwoquan_service/runtime/media"
)

// importedModerationStatus is the service-visible review projection for a
// canonical data release. releaseimport accepts only objects that have passed
// the Data review gate, so a release is never materialized as an unreviewed
// online draft.
const importedModerationStatus = "approved"

func Run() {
	releaseRoot := flag.String("release-root", "", "immutable release root containing payload/desired_state.json (required)")
	mongoURI := flag.String("mongo-uri", "mongodb://localhost:27017", "mongo connection uri")
	mediaImageBaseURL := flag.String("media-image-base-url", "", "environment image media public base URL")
	mediaVideoBaseURL := flag.String("media-video-base-url", "", "environment video media public base URL")
	mediaAvatarBaseURL := flag.String("media-avatar-base-url", "", "environment avatar media public base URL")
	creatorReceipt := flag.String("creator-receipt", "", "user-service creator import receipt")
	postsDB := flag.String("posts-db", "quwoquan_content", "target db for posts")
	env := flag.String("env", "", "environment label (for logging)")
	dryRun := flag.Bool("dry-run", false, "load + report only, do not write mongo")
	activationMode := flag.String("activation-mode", "", "required release action: stage-only|activate")
	expectedActiveReleaseID := flag.String("expected-active-release-id", "", "activate CAS expected current release id; empty only with --expected-active-empty")
	expectedActiveManifestDigest := flag.String("expected-active-manifest-digest", "", "activate CAS expected current manifest digest")
	expectedActiveRevision := flag.Int64("expected-active-revision", -1, "activate CAS expected current pointer revision; use 0 with --expected-active-empty")
	expectedActiveEmpty := flag.Bool("expected-active-empty", false, "activate only when no active pointer exists")
	readActiveReport := flag.String("read-active-report", "", "read current Content active pointer as a typed JSON report and exit")
	mode := flag.String("mode", "upsert", "apply mode: upsert|sync")
	deletePolicy := flag.String("delete-policy", "none", "missing object policy: none|tombstone (deferred during candidate stage)")
	sourceOwner := flag.String("source-owner", "qwq_data", "source owner for imported documents")
	reportPath := flag.String("report", "", "optional machine-readable import report path")
	requireReplay := flag.Bool(
		"require-replay",
		false,
		"require the immutable release to match the active Content release",
	)
	replaySourceImportReport := flag.String(
		"replay-source-import-report",
		"",
		"canonical source import report whose postBindings own replay identity",
	)
	expectedOutboxRepairCount := flag.Int(
		"expected-outbox-repair-count",
		-1,
		"exact replay repair count; requires --require-replay",
	)
	flag.Parse()
	if strings.TrimSpace(*readActiveReport) != "" {
		if strings.TrimSpace(*env) == "" {
			log.Fatal("--read-active-report requires --env")
		}
		ctx := context.Background()
		client, err := mongo.Connect(options.Client().ApplyURI(*mongoURI))
		if err != nil {
			log.Fatalf("mongo connect for active pointer read: %v", err)
		}
		defer client.Disconnect(ctx)
		active, err := ReadActiveImportedPostRelease(
			ctx, client.Database(*postsDB), *env, strings.TrimSpace(*sourceOwner),
		)
		if err != nil {
			log.Fatalf("read active Content release pointer: %v", err)
		}
		if err := WriteActiveReleaseReport(*readActiveReport, active); err != nil {
			log.Fatalf("write active Content release report: %v", err)
		}
		return
	}
	if err := ValidateReplayRepairOptions(
		*requireReplay,
		*expectedOutboxRepairCount,
	); err != nil {
		log.Fatal(err)
	}
	if err := ValidateReplaySourceImportReportOption(
		*requireReplay,
		*replaySourceImportReport,
	); err != nil {
		log.Fatal(err)
	}
	if *activationMode != "stage-only" && *activationMode != "activate" {
		log.Fatal("--activation-mode is required and must be stage-only or activate")
	}
	if *mode != "upsert" && *mode != "sync" {
		log.Fatal("--mode must be upsert or sync; reset-source is not supported")
	}
	if *deletePolicy != "none" && *deletePolicy != "tombstone" {
		log.Fatal("--delete-policy must be none or tombstone")
	}
	if *mode != "sync" && *deletePolicy != "none" {
		log.Fatal("--delete-policy=tombstone requires --mode=sync")
	}
	if *activationMode == "stage-only" &&
		(*expectedActiveEmpty || *expectedActiveRevision >= 0 ||
			strings.TrimSpace(*expectedActiveReleaseID) != "" ||
			strings.TrimSpace(*expectedActiveManifestDigest) != "") {
		log.Fatal("expected-current flags require --activation-mode=activate")
	}
	if *activationMode == "activate" {
		hasExpectedTuple := strings.TrimSpace(*expectedActiveReleaseID) != "" ||
			strings.TrimSpace(*expectedActiveManifestDigest) != "" || *expectedActiveRevision >= 0
		if *expectedActiveEmpty == hasExpectedTuple {
			log.Fatal("activate requires exactly one of --expected-active-empty or the complete expected-active tuple")
		}
		if !*expectedActiveEmpty &&
			(strings.TrimSpace(*expectedActiveReleaseID) == "" ||
				strings.TrimSpace(*expectedActiveManifestDigest) == "" || *expectedActiveRevision <= 0) {
			log.Fatal("activate expected-active tuple requires release id, manifest digest, and positive revision")
		}
		if *expectedActiveEmpty && *expectedActiveRevision != -1 {
			log.Fatal("--expected-active-empty cannot be combined with --expected-active-revision")
		}
	}

	if strings.TrimSpace(*releaseRoot) == "" {
		log.Fatalf("--release-root is required; full-tree import and sample bundle fallback are forbidden")
	}
	desired, err := LoadReleaseDesiredState(*releaseRoot)
	if err != nil {
		log.Fatalf("load release desired state: %v", err)
	}
	releaseBinding, err := LoadReleaseBinding(*releaseRoot)
	if err != nil {
		log.Fatalf("load immutable release binding: %v", err)
	}
	if desired.ReleaseID != releaseBinding.ReleaseID {
		log.Fatalf(
			"release desired state/header drift: desired=%q header=%q",
			desired.ReleaseID,
			releaseBinding.ReleaseID,
		)
	}
	if strings.TrimSpace(*sourceOwner) != releaseBinding.SourceOwner {
		log.Fatalf(
			"--source-owner must match immutable release owner %q",
			releaseBinding.SourceOwner,
		)
	}
	postFilter := ToSet(desired.DesiredRefs.Posts)
	creatorFilter := ToSet(desired.DesiredRefs.Creators)
	objectRoot, err := ReleaseObjectRoot(*releaseRoot)
	if err != nil {
		log.Fatalf("load release object closure: %v", err)
	}
	releaseMediaAssets, err := LoadReleaseMediaAssets(
		*releaseRoot,
		desired.ReleaseID,
		releaseBinding.ReleaseClass,
	)
	if err != nil {
		log.Fatalf("load release media authority: %v", err)
	}
	creatorSnapshots, err := LoadCreatorAuthorSnapshots(
		objectRoot,
		creatorFilter,
		releaseMediaAssets,
		*mediaAvatarBaseURL,
	)
	if err != nil {
		log.Fatalf("load release creators: %v", err)
	}
	creatorAuthors := CreatorAuthorIDs(creatorSnapshots)
	if len(creatorFilter) > 0 {
		if strings.TrimSpace(*creatorReceipt) == "" {
			log.Fatalf("--creator-receipt is required when the release has creators")
		}
		if err := ValidateCreatorImportReceipt(*creatorReceipt, desired.ReleaseID, creatorAuthors); err != nil {
			log.Fatalf("validate creator import receipt: %v", err)
		}
	}

	posts, err := LoadPosts(objectRoot, postFilter, releaseBinding.ReleaseClass)
	if err != nil {
		log.Fatalf("load posts: %v", err)
	}
	if err := ValidatePostAuthors(posts, creatorAuthors); err != nil {
		log.Fatalf("validate post authors: %v", err)
	}
	if err := BindPostAuthorSnapshots(posts, creatorSnapshots); err != nil {
		log.Fatalf("bind post author snapshots: %v", err)
	}
	mediaBases := runtimemedia.MediaDeliveryBases{
		Image: *mediaImageBaseURL,
		Video: *mediaVideoBaseURL,
	}
	if err := BindPostAssetURLs(
		posts,
		releaseMediaAssets,
		mediaBases,
	); err != nil {
		log.Fatalf("bind post asset URLs: %v", err)
	}
	if err := ValidateImportedPostMediaBindings(posts, releaseBinding.ReleaseClass); err != nil {
		log.Fatalf("validate post media delivery bindings: %v", err)
	}
	postBindings, err := ImportedPostBindings(posts)
	if err != nil {
		log.Fatalf("derive imported post bindings: %v", err)
	}
	reportPostBindings := postBindings
	var replayPostBindings []ImportedPostBinding
	if *requireReplay {
		replayPostBindings, err = LoadImportedPostReplayBindings(
			*replaySourceImportReport,
			*env,
			desired.ReleaseID,
			releaseBinding.ManifestDigest,
			releaseBinding.SourceOwner,
			posts,
		)
		if err != nil {
			log.Fatalf("load replay source import report: %v", err)
		}
		reportPostBindings = replayPostBindings
	}
	log.Printf("[import] env=%s loaded posts=%d", *env, len(posts))
	reportActivationMode := ImportReportActivationMode(*activationMode, *requireReplay)

	if *dryRun {
		log.Printf("[import] dry-run: not writing mongo")
		_ = WriteImportReport(*reportPath, bson.M{
			"schema":         "quwoquan.content_import_report",
			"status":         "dry-run",
			"environment":    *env,
			"releaseId":      desired.ReleaseID,
			"sourceOwner":    releaseBinding.SourceOwner,
			"manifestDigest": releaseBinding.ManifestDigest,
			"mode":           *mode,
			"deletePolicy":   *deletePolicy,
			"activationMode": reportActivationMode,
			"counts":         ImportPoolCounts(posts, len(desired.DesiredRefs.Entities)),
			"postBindings":   reportPostBindings,
			"auditEvents":    []string{"DataReleasePrepared"},
			"stageResult":    ImportStageResultDocument(ImportedReleaseApplyResult{}),
		})
		return
	}

	ctx := context.Background()
	client, err := mongo.Connect(options.Client().ApplyURI(*mongoURI))
	if err != nil {
		log.Fatalf("mongo connect: %v", err)
	}
	defer client.Disconnect(ctx)

	now := time.Now().UTC()
	var expectedRepairCount *int
	if *expectedOutboxRepairCount >= 0 {
		expectedRepairCount = expectedOutboxRepairCount
	}
	opts := NormalizeImportOptions(ImportOptions{
		ReleaseID:                 desired.ReleaseID,
		ManifestDigest:            releaseBinding.ManifestDigest,
		ReleaseClass:              releaseBinding.ReleaseClass,
		ReleaseKind:               releaseBinding.ReleaseKind,
		ActivationMode:            *activationMode,
		Mode:                      *mode,
		DeletePolicy:              *deletePolicy,
		SourceOwner:               *sourceOwner,
		ProjectionVersion:         now.UnixMilli(),
		RequireReplay:             *requireReplay,
		ExpectedOutboxRepairCount: expectedRepairCount,
		ReplayPostBindings:        replayPostBindings,
	})
	stageOpts := opts
	stageOpts.ActivationMode = "stage-only"
	if opts.RequireReplay {
		stageOpts.ActivationMode = "repair-active"
	}
	database := client.Database(*postsDB)
	applyResult, err := StageImportedPostRelease(
		ctx,
		database,
		*env,
		posts,
		releaseMediaAssets,
		now,
		stageOpts,
	)
	if err != nil {
		log.Fatalf("stage Content-owned Data release: %v", err)
	}
	activationResult := ReleaseActivationResult{}
	if *activationMode == "activate" {
		expectedRevision := *expectedActiveRevision
		if *expectedActiveEmpty {
			expectedRevision = 0
		}
		expected := ExpectedActiveRelease{
			Empty:          *expectedActiveEmpty,
			SourceOwner:    opts.SourceOwner,
			ReleaseID:      *expectedActiveReleaseID,
			ManifestDigest: *expectedActiveManifestDigest,
			Revision:       expectedRevision,
		}
		activationResult, err = ActivateImportedPostRelease(
			ctx,
			database,
			*env,
			ReleaseBindingFromImportOptions(opts),
			expected,
			now,
		)
		if err != nil {
			log.Fatalf("activate Content-owned Data release: %v", err)
		}
	}
	mediaAssetsProjected := applyResult.MediaAssetsProjected
	activeCounts := ImportPoolCounts(posts, len(desired.DesiredRefs.Entities))
	activeCounts["mediaAssetsProjected"] = mediaAssetsProjected
	activeCounts["postsUpserted"] = applyResult.PostsUpserted
	activeCounts["postsRemoved"] = applyResult.PostsRemoved
	activeCounts["outboxEventsReady"] = applyResult.OutboxEventsReady
	activeCounts["outboxEventsAppended"] = applyResult.OutboxEventsAppended
	if *activationMode == "activate" {
		activeCounts["postsUpserted"] = activationResult.PostsMaterialized
		activeCounts["postsRemoved"] = activationResult.PostsRemoved
		activeCounts["mediaAssetsProjected"] = activationResult.MediaAssetsMaterialized
		activeCounts["outboxEventsReady"] = activationResult.OutboxEventsReady
		activeCounts["outboxEventsAppended"] = activationResult.OutboxEventsAppended
	}
	auditEvents := ImportStageAuditEvents(applyResult.OutboxRepairAudits...)
	if *activationMode == "activate" {
		auditEvents = ImportAuditEvents(
			activationResult.Previous.ReleaseID,
			activationResult.Previous.ManifestDigest,
			applyResult.OutboxRepairAudits...,
		)
	}
	if opts.RequireReplay {
		auditEvents = ImportReplayRepairAuditEvents(
			applyResult.OutboxRepairAudits...,
		)
	}
	reportMode := *activationMode
	if opts.RequireReplay {
		reportMode = "repair-active"
	}
	report := bson.M{
		"schema":         "quwoquan.content_import_report",
		"status":         ImportReportStatus(reportMode),
		"environment":    *env,
		"releaseId":      opts.ReleaseID,
		"sourceOwner":    opts.SourceOwner,
		"manifestDigest": opts.ManifestDigest,
		"mode":           opts.Mode,
		"deletePolicy":   opts.DeletePolicy,
		"activationMode": reportActivationMode,
		"counts":         activeCounts,
		"postBindings":   reportPostBindings,
		"auditEvents":    auditEvents,
		"generatedAt":    now,
		"stageResult":    ImportStageResultDocument(applyResult),
	}
	if *activationMode == "activate" {
		readback, readErr := ReadActiveImportedPostRelease(ctx, database, *env, opts.SourceOwner)
		if readErr != nil {
			log.Fatalf("read back activated Content release pointer: %v", readErr)
		}
		if !readback.Found || readback.ReleaseID != activationResult.Active.ReleaseID ||
			readback.ManifestDigest != activationResult.Active.ManifestDigest ||
			readback.Revision != activationResult.Active.Revision {
			log.Fatal("GATE_BLOCK: activated Content release readback differs from CAS result")
		}
		report["activationResult"] = ActivationResultDocument(activationResult, readback)
	}
	if err := WriteImportReport(*reportPath, report); err != nil {
		log.Fatalf("write import report: %v", err)
	}
	log.Printf("[import] OK env=%s release=%s status=%s mode=%s deletePolicy=%s materializedPosts=%d materializedMedia=%d outboxEvents=%d appended=%d removedPosts=%d replayed=%t",
		*env, opts.ReleaseID, ImportReportStatus(reportMode), opts.Mode, opts.DeletePolicy,
		activeCounts["postsUpserted"], activeCounts["mediaAssetsProjected"],
		activeCounts["outboxEventsReady"], activeCounts["outboxEventsAppended"],
		activeCounts["postsRemoved"], applyResult.Replayed || activationResult.Replayed)

}

// ValidateReplayRepairOptions keeps the bounded repair mode explicit. Normal
// imports cannot accidentally acquire an expected repair count, while a repair
// cannot silently activate a different release.
func ValidateReplayRepairOptions(requireReplay bool, expectedRepairCount int) error {
	if requireReplay && expectedRepairCount < 0 {
		return fmt.Errorf("--require-replay requires --expected-outbox-repair-count")
	}
	if !requireReplay && expectedRepairCount >= 0 {
		return fmt.Errorf("--expected-outbox-repair-count requires --require-replay")
	}
	return nil
}

// ImportReportStatus reports importer-owned staging facts only. Activation
// is recorded by the independent content release activation receipt, while a
// bounded replay repair retains its explicit validation status.
func ImportReportStatus(activationMode string) string {
	if strings.TrimSpace(activationMode) == "repair-active" {
		return "replay_validated"
	}
	return "imported"
}

// ImportReportActivationMode keeps the Data-reachable import report on the
// stage-only rail; activation is not an importer-owned report fact.
func ImportReportActivationMode(_ string, _ bool) string {
	return "stage-only"
}

// ImportStageAuditEvents reports only facts established by candidate staging.
func ImportStageAuditEvents(repairs ...ImportedPostOutboxRepairAudit) []string {
	events := []string{"DataReleasePrepared", "DataReleaseVerified"}
	sortedRepairs := append([]ImportedPostOutboxRepairAudit(nil), repairs...)
	sort.Slice(sortedRepairs, func(left, right int) bool {
		return sortedRepairs[left].EventID < sortedRepairs[right].EventID
	})
	events = append(events, fmt.Sprintf("DataReleaseOutboxRepair|count=%d", len(sortedRepairs)))
	return events
}

// ImportAuditEvents records the previous active pointer and bounded outbox
// repair digests without expanding the public import-report schema.
func ImportAuditEvents(
	previousReleaseID,
	previousManifestDigest string,
	repairs ...ImportedPostOutboxRepairAudit,
) []string {
	events := []string{"DataReleasePrepared", "DataReleaseActivated"}
	previousReleaseID = strings.TrimSpace(previousReleaseID)
	previousManifestDigest = strings.TrimSpace(previousManifestDigest)
	if previousReleaseID != "" && previousManifestDigest != "" {
		events = append(
			events,
			"PreviousDataRelease|"+previousReleaseID+"|"+previousManifestDigest,
		)
	}
	sortedRepairs := append([]ImportedPostOutboxRepairAudit(nil), repairs...)
	sort.Slice(sortedRepairs, func(left, right int) bool {
		return sortedRepairs[left].EventID < sortedRepairs[right].EventID
	})
	events = append(
		events,
		fmt.Sprintf("DataReleaseOutboxRepair|count=%d", len(sortedRepairs)),
	)
	for _, repair := range sortedRepairs {
		events = append(events, fmt.Sprintf(
			"DataReleaseOutboxEventRepair|eventId=%s|beforeSha256=%s|afterSha256=%s",
			repair.EventID,
			repair.BeforeSHA256,
			repair.AfterSHA256,
		))
	}
	return events
}

// ImportReplayRepairAuditEvents records a repair readback without claiming a
// second activation. The active release-state document remains byte-for-byte
// unchanged on this rail.
func ImportReplayRepairAuditEvents(
	repairs ...ImportedPostOutboxRepairAudit,
) []string {
	events := ImportAuditEvents("", "", repairs...)
	events[1] = "DataReleaseReplayValidated"
	return events
}

// EnsureUnique 幂等建唯一索引（已存在则忽略）。
func EnsureUnique(ctx context.Context, coll *mongo.Collection, key, name string) {
	if _, err := coll.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: key, Value: 1}},
		Options: options.Index().SetName(name).SetUnique(true),
	}); err != nil {
		log.Printf("WARN: ensure %s: %v", name, err)
	}
}

// EnsureSparseUnique only constrains imported documents that carry bridge refs.
func EnsureSparseUnique(ctx context.Context, coll *mongo.Collection, key, name string) {
	if _, err := coll.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: key, Value: 1}},
		Options: options.Index().SetName(name).SetUnique(true).SetSparse(true),
	}); err != nil {
		log.Printf("WARN: ensure %s: %v", name, err)
	}
}

// UpsertPosts 幂等 upsert 文章到运行库；createdAt 仅插入时写，updatedAt 每次刷新。
func UpsertPosts(ctx context.Context, coll *mongo.Collection, posts []PostDoc, now time.Time) (int, error) {
	return UpsertPostsWithOptions(ctx, coll, posts, now, NormalizeImportOptions(ImportOptions{}))
}

type ImportOptions struct {
	ReleaseID      string
	ManifestDigest string
	// ActivationMode 由 CLI importer 显式选择 stage-only 或 activate；
	// StageImportedPostRelease 只执行 stage，激活必须另调 CAS 命令。
	ActivationMode string
	// ReleaseClass 是 release.json 声明的 release 级类别（research|commercial），
	// 随导入落进 data_release_state，供 research readback 判定 release 类别。
	ReleaseClass              string
	ReleaseKind               string
	Mode                      string
	DeletePolicy              string
	SourceOwner               string
	ProjectionVersion         int64
	RequireReplay             bool
	ExpectedOutboxRepairCount *int
	ReplayPostBindings        []ImportedPostBinding
}

func NormalizeImportOptions(opts ImportOptions) ImportOptions {
	if opts.ReleaseID == "" {
		opts.ReleaseID = "adhoc"
	}
	if opts.Mode == "" {
		opts.Mode = "upsert"
	}
	if opts.DeletePolicy == "" {
		opts.DeletePolicy = "none"
	}
	if opts.SourceOwner == "" {
		opts.SourceOwner = "qwq_data"
	}
	return opts
}

// ImportedPostDeletionSnapshot freezes the consumer-owned Post fields before
// a full-sync applies its local tombstone/hard-delete policy.
type ImportedPostDeletionSnapshot struct {
	PostID             string    `bson:"_id"`
	AuthorID           string    `bson:"authorId"`
	ContentType        string    `bson:"contentType"`
	ContentIdentity    string    `bson:"contentIdentity"`
	Status             string    `bson:"status"`
	LifecycleStatus    string    `bson:"lifecycleStatus"`
	DeletedByReleaseID string    `bson:"deletedByReleaseId"`
	DeletedAt          time.Time `bson:"deletedAt"`
}

// MissingImportedPostSnapshots freezes the exact canonical deletion facts
// before Content mutates the old Posts. Consumers never receive release-only
// metadata in place of the Post lifecycle fields they own.
func MissingImportedPostSnapshots(
	ctx context.Context,
	coll *mongo.Collection,
	posts []PostDoc,
	opts ImportOptions,
	replayed bool,
	occurredAt time.Time,
) ([]ImportedPostDeletionSnapshot, error) {
	opts = NormalizeImportOptions(opts)
	if !missingPolicyEnabled(opts) || opts.DeletePolicy == "none" {
		return nil, nil
	}
	filter := bson.M{
		"sourceOwner": opts.SourceOwner,
		"postRef":     bson.M{"$nin": desiredPostRefs(posts)},
	}
	if replayed {
		filter["lifecycleStatus"] = "tombstone"
		filter["deletedByReleaseId"] = opts.ReleaseID
		filter["deletedAt"] = occurredAt
	} else {
		filter["$or"] = bson.A{
			bson.M{"lifecycleStatus": bson.M{"$ne": "tombstone"}},
			bson.M{"deletedByReleaseId": bson.M{"$ne": opts.ReleaseID}},
		}
	}
	cursor, err := coll.Find(ctx, filter, options.Find().SetProjection(bson.M{
		"_id": 1, "authorId": 1, "contentType": 1, "contentIdentity": 1,
		"status": 1, "lifecycleStatus": 1, "deletedByReleaseId": 1, "deletedAt": 1,
	}).SetSort(bson.D{{Key: "_id", Value: 1}}))
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	snapshots := make([]ImportedPostDeletionSnapshot, 0)
	for cursor.Next(ctx) {
		var snapshot ImportedPostDeletionSnapshot
		if err := cursor.Decode(&snapshot); err != nil {
			return nil, err
		}
		snapshot.PostID = strings.TrimSpace(snapshot.PostID)
		snapshot.AuthorID = strings.TrimSpace(snapshot.AuthorID)
		snapshot.ContentType = strings.TrimSpace(snapshot.ContentType)
		snapshot.Status = strings.TrimSpace(snapshot.Status)
		snapshot.LifecycleStatus = strings.TrimSpace(snapshot.LifecycleStatus)
		snapshot.DeletedByReleaseID = strings.TrimSpace(snapshot.DeletedByReleaseID)
		contentIdentity, err := canonicalImportedContentIdentity(
			snapshot.ContentIdentity,
		)
		if err != nil {
			return nil, fmt.Errorf("imported Post %q: %w", snapshot.PostID, err)
		}
		snapshot.ContentIdentity = contentIdentity
		if snapshot.PostID == "" || snapshot.AuthorID == "" ||
			snapshot.ContentType == "" || snapshot.Status == "" {
			return nil, fmt.Errorf(
				"imported Post deletion snapshot lacks canonical lifecycle fields",
			)
		}
		if replayed {
			if snapshot.Status != "deleted" || snapshot.LifecycleStatus != "tombstone" ||
				snapshot.DeletedByReleaseID != opts.ReleaseID ||
				!snapshot.DeletedAt.Equal(occurredAt) {
				return nil, fmt.Errorf(
					"GATE_BLOCK: imported Post %q is not the exact active-release tombstone",
					snapshot.PostID,
				)
			}
		}
		// Data release Posts are materialized only as published. Match the
		// canonical DeletePost event, which carries status-before-delete. This
		// also applies when a new release takes ownership of an already
		// tombstoned Post; persisting status=deleted would make that release
		// impossible to replay byte-for-byte.
		snapshot.Status = "published"
		snapshots = append(snapshots, snapshot)
	}
	if err := cursor.Err(); err != nil {
		return nil, err
	}
	return snapshots, nil
}

func sourceHash(v any) string {
	raw, _ := json.Marshal(v)
	sum := sha256.Sum256(raw)
	return hex.EncodeToString(sum[:])
}

// RuntimePostID derives the public Post identity exclusively from the stable
// contentId admitted by the canonical content pool. Missing contentId is an
// invalid release input and never falls back to a producer object path.
func RuntimePostID(contentID string) string {
	identity := strings.TrimSpace(contentID)
	if identity == "" {
		return ""
	}
	sum := sha256.Sum256([]byte("qwq-content-post:" + identity))
	return "data_post_" + hex.EncodeToString(sum[:])
}

// CanonicalImportReportPostRef projects the loader storage postRef
// (posts/<carrier>/...) into the release-object postRef consumed by
// import_report.schema.json and ship verify (carrier/...).
func CanonicalImportReportPostRef(storagePostRef string) (string, error) {
	ref := strings.TrimSpace(strings.ReplaceAll(storagePostRef, "\\", "/"))
	if ref == "" {
		return "", fmt.Errorf("imported postRef is empty")
	}
	reportRef := strings.TrimPrefix(ref, "posts/")
	if reportRef == ref || reportRef == "" {
		return "", fmt.Errorf("imported postRef must be under posts/: %q", storagePostRef)
	}
	switch {
	case strings.HasPrefix(reportRef, "article/"),
		strings.HasPrefix(reportRef, "image/"),
		strings.HasPrefix(reportRef, "video/"):
		return reportRef, nil
	default:
		return "", fmt.Errorf("imported postRef carrier is unsupported: %q", storagePostRef)
	}
}

// ImportedPostBinding is the releaseimport-owned mapping from a canonical
// post object to its runtime identity and consumer-visible owner. It is
// emitted in every importer report so Data release evidence can verify the
// exact records materialized by this package without deriving IDs itself.
type ImportedPostBinding struct {
	PostRef        string `json:"postRef" bson:"postRef"`
	PostID         string `json:"postId" bson:"postId"`
	ContentID      string `json:"contentId" bson:"contentId"`
	ContentVersion int64  `json:"contentVersion" bson:"contentVersion"`
	UsageScope     string `json:"usageScope" bson:"usageScope"`
	ContentType    string `json:"contentType" bson:"contentType"`
	AuthorID       string `json:"authorId" bson:"authorId"`
}

// ImportedPostBindings produces a deterministic, complete binding set for
// one immutable release. Empty post releases are valid (for example an empty
// baseline); malformed or duplicate content releases fail before any write.
func ImportedPostBindings(posts []PostDoc) ([]ImportedPostBinding, error) {
	bindings := make([]ImportedPostBinding, 0, len(posts))
	seenRefs := make(map[string]struct{}, len(posts))
	seenIDs := make(map[string]struct{}, len(posts))
	for _, post := range posts {
		storagePostRef := strings.TrimSpace(post.PostRef)
		contentType := strings.TrimSpace(post.ContentType)
		authorID := strings.TrimSpace(post.AuthorID)
		postID := RuntimePostID(post.ContentID)
		reportPostRef, err := CanonicalImportReportPostRef(storagePostRef)
		if err != nil {
			return nil, err
		}
		if storagePostRef == "" || postID == "" || contentType == "" || authorID == "" ||
			strings.TrimSpace(post.ContentID) == "" || post.ContentVersion < 1 ||
			(post.Admission.UsageScope != "research" && post.Admission.UsageScope != "commercial") {
			return nil, fmt.Errorf("imported post binding requires admitted content, post and author identities")
		}
		if _, exists := seenRefs[reportPostRef]; exists {
			return nil, fmt.Errorf("duplicate imported postRef %q", reportPostRef)
		}
		if _, exists := seenIDs[postID]; exists {
			return nil, fmt.Errorf("duplicate imported postId %q", postID)
		}
		seenRefs[reportPostRef] = struct{}{}
		seenIDs[postID] = struct{}{}
		bindings = append(bindings, ImportedPostBinding{
			PostRef: reportPostRef, PostID: postID, ContentID: post.ContentID,
			ContentVersion: post.ContentVersion, UsageScope: post.Admission.UsageScope,
			ContentType: contentType, AuthorID: authorID,
		})
	}
	sort.Slice(bindings, func(left, right int) bool {
		return bindings[left].PostRef < bindings[right].PostRef
	})
	return bindings, nil
}

func releaseFields(opts ImportOptions, now time.Time, lifecycleStatus string) bson.M {
	fields := bson.M{
		"releaseId":            opts.ReleaseID,
		"visibleFromReleaseId": opts.ReleaseID,
		"sourceOwner":          opts.SourceOwner,
		"lifecycleStatus":      lifecycleStatus,
		"releaseUpdatedAt":     now,
	}
	if strings.TrimSpace(opts.ManifestDigest) != "" {
		fields["manifestDigest"] = strings.TrimSpace(opts.ManifestDigest)
	}
	return fields
}

func desiredPostRefs(posts []PostDoc) []string {
	refs := make([]string, 0, len(posts))
	for _, p := range posts {
		if p.PostRef != "" {
			refs = append(refs, p.PostRef)
		}
	}
	return refs
}

func desiredRuntimePostIDs(posts []PostDoc) []string {
	ids := make([]string, 0, len(posts))
	for _, p := range posts {
		id := RuntimePostID(p.ContentID)
		if id != "" {
			ids = append(ids, id)
		}
	}
	return ids
}

func desiredEntityRefs(entities []EntityDoc) []string {
	refs := make([]string, 0, len(entities))
	for _, e := range entities {
		if e.EntityRef != "" {
			refs = append(refs, e.EntityRef)
		}
	}
	return refs
}

func BuildCanonicalImportedPostDocument(
	post PostDoc,
	now time.Time,
	opts ImportOptions,
	lifecycleStatus string,
) (bson.M, error) {
	opts = NormalizeImportOptions(opts)
	contentIdentity, err := canonicalImportedContentIdentity(post.ContentIdentity)
	if err != nil {
		return nil, fmt.Errorf("%s: %w", post.PostRef, err)
	}
	postID := RuntimePostID(post.ContentID)
	if postID == "" {
		return nil, fmt.Errorf("contentId is required to derive runtime postId")
	}
	runtimeEntityRefs := post.NormalizedEntityRefs
	if len(runtimeEntityRefs) == 0 {
		runtimeEntityRefs = post.EntityRefs
	}
	accessMode := MediaDeliveryAccessModeForReleaseClass(opts.ReleaseClass)
	media := ImportedMediaFields(importedPostAssets(post), accessMode)
	body := post.ArticleMarkdown
	summary := ProjectImportedArticleSummary(post.ArticleMarkdown)
	if post.ContentType == "image" {
		body = post.Body
		summary = post.Body
	}
	document := bson.M{
		"_id": postID, "postRef": post.PostRef, "postId": postID,
		"contentType": post.ContentType, "contentId": post.ContentID,
		"contentVersion": post.ContentVersion, "poolSourceType": post.PoolSourceType,
		"variantPurpose": post.VariantPurpose, "admission": post.Admission,
		"poolStatus": post.PoolStatus, "contentIdentity": contentIdentity,
		"title": post.Title, "angle": post.Angle, "seq": post.Seq,
		"entityRefs": runtimeEntityRefs, "tagRefs": post.TagRefs,
		"intersectionHints": post.IntersectionHints, "semanticMentions": post.SemanticMentions,
		"authorId": post.AuthorID, "authorDisplayNameSnapshot": post.AuthorDisplayName,
		"authorAvatarUrlSnapshot": post.AuthorAvatarURL,
		"creatorProfileId":        post.CreatorProfileID, "creatorArchetype": post.CreatorArchetype,
		"creatorProfileVersion": post.CreatorProfileVersion,
		"creatorDisclosure":     post.CreatorDisclosure, "experienceClaimMode": post.ExperienceClaimMode,
		"authorQualitySignals": post.AuthorQualitySignals,
		"sourceCollectionId":   post.SourceCollectionID, "sourcePlatform": post.SourcePlatform,
		"sourceAttribution": post.SourceAttribution, "creator": post.Creator,
		"page": post.Page, "licenseProof": post.LicenseProof,
		"template": post.Template, "articleTemplate": post.Template,
		"body": body, "summary": summary, "mediaUrls": media.MediaURLs,
		"mediaItems": media.MediaItems, "coverUrl": media.CoverURL,
		"mediaAssetIds": media.MediaAssetIDs, "articleMarkdown": post.ArticleMarkdown,
		"articleDigest": post.ArticleDigest, "articleMarkdownDigest": post.ArticleDigest,
		"articleAssetManifest": ImportedArticleAssetManifest(post.ArticleAssetManifest, accessMode),
		"createdAt":            post.CreatedAt, "updatedAt": post.UpdatedAt,
		"publishedAt": post.PublishedAt, "version": opts.ProjectionVersion,
		"status": "published", "visibility": "public",
		"moderationStatus": importedModerationStatus, "sourceHash": sourceHash(post),
	}
	applyImportedVideoFields(document, media)
	ApplyImportedAuthorAvatarDeliveryFields(document, post, accessMode)
	for key, value := range releaseFields(opts, now, lifecycleStatus) {
		document[key] = value
	}
	return document, nil
}

func UpsertPostsWithOptions(ctx context.Context, coll *mongo.Collection, posts []PostDoc, now time.Time, opts ImportOptions) (int, error) {
	opts = NormalizeImportOptions(opts)
	n := 0
	for _, post := range posts {
		document, err := BuildCanonicalImportedPostDocument(post, now, opts, "active")
		if err != nil {
			return n, err
		}
		postID := document["_id"].(string)
		if err := migrateImportedPostIdentity(ctx, coll, post.ContentID, post.PostRef, postID, opts); err != nil {
			return n, err
		}
		delete(document, "_id")
		if _, err := coll.UpdateOne(ctx,
			bson.M{"_id": postID},
			bson.M{"$set": document, "$setOnInsert": bson.M{"_id": postID}},
			options.UpdateOne().SetUpsert(true),
		); err != nil {
			return n, err
		}
		n++
	}
	return n, nil
}

func migrateImportedPostIdentity(
	ctx context.Context,
	coll *mongo.Collection,
	contentID string,
	postRef string,
	runtimeID string,
	opts ImportOptions,
) error {
	var existing struct {
		ID          string `bson:"_id"`
		SourceOwner string `bson:"sourceOwner"`
	}
	identityFilters := bson.A{bson.M{"postRef": postRef}}
	if stableContentID := strings.TrimSpace(contentID); stableContentID != "" {
		identityFilters = append(identityFilters, bson.M{"contentId": stableContentID})
	}
	err := coll.FindOne(ctx,
		bson.M{"$or": identityFilters},
		options.FindOne().SetProjection(bson.M{"_id": 1, "sourceOwner": 1}),
	).Decode(&existing)
	if err != nil {
		if err == mongo.ErrNoDocuments {
			return nil
		}
		return err
	}
	if existing.ID == "" || existing.ID == runtimeID {
		return nil
	}
	if existing.SourceOwner != "" && existing.SourceOwner != opts.SourceOwner {
		return fmt.Errorf("refuse to migrate postRef %q owned by %q while importing owner %q", postRef, existing.SourceOwner, opts.SourceOwner)
	}
	if _, err := coll.DeleteOne(ctx, bson.M{"_id": existing.ID}); err != nil {
		return err
	}
	return nil
}

// contentSourceChanged 判断目标文档相对新内容 hash 是否发生实质变更。
// 文档不存在（首次插入）视为变更；已存在且 sourceHash 相同视为未变更。
func contentSourceChanged(ctx context.Context, coll *mongo.Collection, filter bson.M, newHash string) (bool, error) {
	var existing struct {
		SourceHash string `bson:"sourceHash"`
	}
	err := coll.FindOne(ctx, filter, options.FindOne().SetProjection(bson.M{"sourceHash": 1})).Decode(&existing)
	if err != nil {
		if err == mongo.ErrNoDocuments {
			return true, nil
		}
		return false, err
	}
	return existing.SourceHash != newHash, nil
}

// UpsertEntities 幂等 upsert 实体到运行库。
func UpsertEntities(ctx context.Context, coll *mongo.Collection, entities []EntityDoc, now time.Time) (int, error) {
	return UpsertEntitiesWithOptions(ctx, coll, entities, now, NormalizeImportOptions(ImportOptions{}))
}

func UpsertEntitiesWithOptions(ctx context.Context, coll *mongo.Collection, entities []EntityDoc, now time.Time, opts ImportOptions) (int, error) {
	opts = NormalizeImportOptions(opts)
	n := 0
	for _, e := range entities {
		doc := bson.M{
			"entityRef": e.EntityRef, "domain": e.Domain, "etype": e.Etype, "name": e.Name,
			"label": e.Label, "tagRefs": e.TagRefs, "page": e.Page, "hasPage": e.HasPage,
			"assetManifest":    e.AssetManifest,
			"conditionProfile": e.ConditionProfile,
			"updatedAt":        now, "sourceHash": sourceHash(e),
		}
		for k, v := range releaseFields(opts, now, "candidate") {
			doc[k] = v
		}
		if _, err := coll.UpdateOne(ctx,
			bson.M{"entityRef": e.EntityRef},
			bson.M{"$set": doc, "$setOnInsert": bson.M{"createdAt": now}},
			options.UpdateOne().SetUpsert(true),
		); err != nil {
			return n, err
		}
		n++
	}
	return n, nil
}

func missingPolicyEnabled(opts ImportOptions) bool {
	return opts.Mode == "sync" && opts.DeletePolicy == "tombstone"
}

func ApplyMissingPostPolicy(ctx context.Context, coll *mongo.Collection, posts []PostDoc, now time.Time, opts ImportOptions) (int64, error) {
	opts = NormalizeImportOptions(opts)
	if !missingPolicyEnabled(opts) || opts.DeletePolicy == "none" {
		return 0, nil
	}
	filter := bson.M{
		"sourceOwner": opts.SourceOwner,
		"postRef":     bson.M{"$nin": desiredPostRefs(posts)},
		"$or": bson.A{
			bson.M{"lifecycleStatus": bson.M{"$ne": "tombstone"}},
			bson.M{"deletedByReleaseId": bson.M{"$ne": opts.ReleaseID}},
		},
	}
	if opts.DeletePolicy == "hard-delete" {
		res, err := coll.DeleteMany(ctx, filter)
		if err != nil {
			return 0, err
		}
		return res.DeletedCount, nil
	}
	res, err := coll.UpdateMany(ctx, filter, bson.M{"$set": bson.M{
		"status": "deleted", "visibility": "hidden", "lifecycleStatus": "tombstone",
		"deletedAt": now, "deletedByReleaseId": opts.ReleaseID, "updatedAt": now,
	}})
	if err != nil {
		return 0, err
	}
	return res.ModifiedCount, nil
}

func ApplyMissingEntityPolicy(ctx context.Context, coll *mongo.Collection, entities []EntityDoc, now time.Time, opts ImportOptions) (int64, error) {
	opts = NormalizeImportOptions(opts)
	if !missingPolicyEnabled(opts) || opts.DeletePolicy == "none" {
		return 0, nil
	}
	filter := bson.M{
		"sourceOwner": opts.SourceOwner,
		"entityRef":   bson.M{"$nin": desiredEntityRefs(entities)},
		"$or": bson.A{
			bson.M{"lifecycleStatus": bson.M{"$ne": "tombstone"}},
			bson.M{"deletedByReleaseId": bson.M{"$ne": opts.ReleaseID}},
		},
	}
	if opts.DeletePolicy == "hard-delete" {
		res, err := coll.DeleteMany(ctx, filter)
		if err != nil {
			return 0, err
		}
		return res.DeletedCount, nil
	}
	res, err := coll.UpdateMany(ctx, filter, bson.M{"$set": bson.M{
		"lifecycleStatus": "tombstone", "deletedAt": now, "deletedByReleaseId": opts.ReleaseID, "updatedAt": now,
	}})
	if err != nil {
		return 0, err
	}
	return res.ModifiedCount, nil
}

func UpsertReleaseState(
	ctx context.Context,
	coll *mongo.Collection,
	env string,
	opts ImportOptions,
	now time.Time,
	counts bson.M,
) error {
	_ = ctx
	_ = coll
	_ = env
	_ = opts
	_ = now
	_ = counts
	return fmt.Errorf("UpsertReleaseState is disabled; use StageImportedPostRelease then ActivateImportedPostRelease with expected-current CAS")
}

// ImportLoadedCounts always emits schema-required loaded counters, including
// zero values. JSON consumers reject reports that omit entitiesLoaded=0.
func ImportLoadedCounts(postsLoaded, entitiesLoaded int) bson.M {
	return bson.M{
		"postsLoaded":    postsLoaded,
		"entitiesLoaded": entitiesLoaded,
	}
}

// ImportPoolCounts exposes the minimal pool and carrier totals used by Data,
// Search and Recommendation release verification.
func ImportPoolCounts(posts []PostDoc, entitiesLoaded int) bson.M {
	counts := ImportLoadedCounts(len(posts), entitiesLoaded)
	counts["articleLoaded"] = 0
	counts["imageLoaded"] = 0
	counts["videoLoaded"] = 0
	counts["researchLoaded"] = 0
	counts["commercialLoaded"] = 0
	for _, post := range posts {
		switch post.ContentType {
		case "article":
			counts["articleLoaded"] = counts["articleLoaded"].(int) + 1
		case "image":
			counts["imageLoaded"] = counts["imageLoaded"].(int) + 1
		case "video":
			counts["videoLoaded"] = counts["videoLoaded"].(int) + 1
		}
		switch post.Admission.UsageScope {
		case "research":
			counts["researchLoaded"] = counts["researchLoaded"].(int) + 1
		case "commercial":
			counts["commercialLoaded"] = counts["commercialLoaded"].(int) + 1
		}
	}
	return counts
}

func ActiveReleaseBindingDocument(binding ActiveReleaseBinding) bson.M {
	document := bson.M{
		"found": binding.Found, "environment": binding.Environment,
		"sourceOwner": binding.SourceOwner, "releaseId": binding.ReleaseID,
		"manifestDigest": binding.ManifestDigest, "releaseClass": binding.ReleaseClass,
		"projectionVersion": binding.ProjectionVersion, "revision": binding.Revision,
	}
	if !binding.ActivatedAt.IsZero() {
		document["activatedAt"] = binding.ActivatedAt.UTC().Format(time.RFC3339Nano)
	}
	return document
}

func ImportStageResultDocument(result ImportedReleaseApplyResult) bson.M {
	return bson.M{
		"postsExpected": result.PostsExpected, "postsProjected": result.PostsUpserted,
		"mediaExpected": result.MediaAssetsExpected, "mediaProjected": result.MediaAssetsProjected,
		"outboxExpected": result.OutboxEventsReady, "outboxProjected": result.OutboxEventsAppended,
		"projectionVersion": result.ProjectionVersion, "replayed": result.Replayed,
	}
}

func ActivationResultDocument(result ReleaseActivationResult, readback ActiveReleaseBinding) bson.M {
	return bson.M{
		"before": ActiveReleaseBindingDocument(ActiveReleaseBinding{
			Found: !result.Previous.Empty(), SourceOwner: result.Previous.SourceOwner,
			ReleaseID: result.Previous.ReleaseID, ManifestDigest: result.Previous.ManifestDigest,
		}),
		"after":    ActiveReleaseBindingDocument(result.Active),
		"readback": ActiveReleaseBindingDocument(readback),
		"replayed": result.Replayed,
	}
}

func WriteActiveReleaseReport(path string, binding ActiveReleaseBinding) error {
	if strings.TrimSpace(path) == "" {
		return fmt.Errorf("active release report path is required")
	}
	return WriteImportReport(path, bson.M{
		"schema": "quwoquan.content_active_release",
		"active": ActiveReleaseBindingDocument(binding),
	})
}

func WriteImportReport(path string, report bson.M) error {
	if path == "" {
		return nil
	}
	if counts, ok := report["counts"].(bson.M); ok {
		if _, exists := counts["postsLoaded"]; !exists {
			counts["postsLoaded"] = 0
		}
		if _, exists := counts["entitiesLoaded"]; !exists {
			counts["entitiesLoaded"] = 0
		}
	}
	raw, err := json.MarshalIndent(report, "", "  ")
	if err != nil {
		return err
	}
	raw = append(raw, '\n')
	return os.WriteFile(path, raw, 0o644)
}
