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

	platformredis "quwoquan_service/internal/platform/redis"
	runtimemedia "quwoquan_service/runtime/media"
	rtredis "quwoquan_service/runtime/redis"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
	postmessaging "quwoquan_service/services/content-service/internal/content/post/infrastructure/messaging"
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
	creatorReceipt := flag.String("creator-receipt", "", "user-service creator import receipt")
	redisAddr := flag.String("redis-addr", "", "canonical Redis address for post lifecycle projection")
	redisDB := flag.Int("redis-db", 0, "canonical Redis database for post lifecycle projection")
	postsDB := flag.String("posts-db", "quwoquan_content", "target db for posts")
	env := flag.String("env", "", "environment label (for logging)")
	dryRun := flag.Bool("dry-run", false, "load + report only, do not write mongo")
	mode := flag.String("mode", "upsert", "apply mode: upsert|sync|reset-source")
	deletePolicy := flag.String("delete-policy", "none", "missing object policy: none|tombstone|hard-delete")
	sourceOwner := flag.String("source-owner", "qwq_data", "source owner for imported documents")
	reportPath := flag.String("report", "", "optional machine-readable import report path")
	flag.Parse()

	if strings.TrimSpace(*releaseRoot) == "" {
		log.Fatalf("--release-root is required; full-tree import and sample bundle fallback are forbidden")
	}
	if !*dryRun && strings.TrimSpace(*redisAddr) == "" {
		log.Fatalf("--redis-addr is required for recommendation candidate projection")
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
	releaseMediaAssets, err := LoadReleaseMediaAssets(*releaseRoot, desired.ReleaseID)
	if err != nil {
		log.Fatalf("load release media authority: %v", err)
	}
	creatorAuthors, err := LoadCreatorAuthorIDs(objectRoot, creatorFilter)
	if err != nil {
		log.Fatalf("load release creators: %v", err)
	}
	if len(creatorFilter) > 0 {
		if strings.TrimSpace(*creatorReceipt) == "" {
			log.Fatalf("--creator-receipt is required when the release has creators")
		}
		if err := ValidateCreatorImportReceipt(*creatorReceipt, desired.ReleaseID, creatorAuthors); err != nil {
			log.Fatalf("validate creator import receipt: %v", err)
		}
	}

	posts, err := LoadPosts(objectRoot, postFilter)
	if err != nil {
		log.Fatalf("load posts: %v", err)
	}
	if err := ValidatePostAuthors(posts, creatorAuthors); err != nil {
		log.Fatalf("validate post authors: %v", err)
	}
	if err := BindPostAssetURLs(
		posts,
		releaseMediaAssets,
		runtimemedia.MediaDeliveryBases{
			Image: *mediaImageBaseURL,
			Video: *mediaVideoBaseURL,
		},
	); err != nil {
		log.Fatalf("bind post asset URLs: %v", err)
	}
	postBindings, err := ImportedPostBindings(posts)
	if err != nil {
		log.Fatalf("derive imported post bindings: %v", err)
	}
	log.Printf("[import] env=%s loaded posts=%d", *env, len(posts))

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
			"counts":         ImportLoadedCounts(len(posts), len(desired.DesiredRefs.Entities)),
			"postBindings":   postBindings,
			"auditEvents":    []string{"DataReleasePrepared"},
		})
		return
	}

	ctx := context.Background()
	client, err := mongo.Connect(options.Client().ApplyURI(*mongoURI))
	if err != nil {
		log.Fatalf("mongo connect: %v", err)
	}
	defer client.Disconnect(ctx)

	postsColl := client.Database(*postsDB).Collection("posts")
	EnsureSparseUnique(ctx, postsColl, "postRef", "idx_post_ref")

	now := time.Now().UTC()
	opts := NormalizeImportOptions(ImportOptions{
		ReleaseID:         desired.ReleaseID,
		ManifestDigest:    releaseBinding.ManifestDigest,
		Mode:              *mode,
		DeletePolicy:      *deletePolicy,
		SourceOwner:       *sourceOwner,
		ProjectionVersion: now.UnixMilli(),
	})
	deletedPostIDs, err := MissingImportedPostIDs(ctx, postsColl, posts, opts)
	if err != nil {
		log.Fatalf("resolve missing posts: %v", err)
	}
	np, err := UpsertPostsWithOptions(ctx, postsColl, posts, now, opts)
	if err != nil {
		log.Fatalf("upsert posts: %v", err)
	}
	tp, err := ApplyMissingPostPolicy(ctx, postsColl, posts, now, opts)
	if err != nil {
		log.Fatalf("apply missing post policy: %v", err)
	}
	candidateEvents, err := PublishImportedPostLifecycle(
		ctx,
		strings.TrimSpace(*redisAddr),
		*redisDB,
		posts,
		deletedPostIDs,
		opts,
		now,
	)
	if err != nil {
		log.Fatalf("publish recommendation candidate lifecycle: %v", err)
	}
	stateColl := client.Database(*postsDB).Collection("data_release_state")
	if err := UpsertReleaseState(ctx, stateColl, *env, opts, now, bson.M{
		"postsUpserted": np,
		"postsRemoved":  tp,
	}); err != nil {
		log.Fatalf("upsert release state: %v", err)
	}
	activeCounts := ImportLoadedCounts(len(posts), len(desired.DesiredRefs.Entities))
	activeCounts["postsUpserted"] = np
	activeCounts["postsRemoved"] = tp
	activeCounts["candidateEventsPublished"] = candidateEvents
	if err := WriteImportReport(*reportPath, bson.M{
		"schema":         "quwoquan.content_import_report",
		"status":         "active",
		"environment":    *env,
		"releaseId":      opts.ReleaseID,
		"sourceOwner":    opts.SourceOwner,
		"manifestDigest": opts.ManifestDigest,
		"mode":           opts.Mode,
		"deletePolicy":   opts.DeletePolicy,
		"counts":         activeCounts,
		"postBindings":   postBindings,
		"auditEvents":    []string{"DataReleasePrepared", "DataReleaseActivated"},
		"generatedAt":    now,
	}); err != nil {
		log.Fatalf("write import report: %v", err)
	}
	log.Printf("[import] OK env=%s release=%s mode=%s deletePolicy=%s upserted posts=%d lifecycleEvents=%d removed posts=%d",
		*env, opts.ReleaseID, opts.Mode, opts.DeletePolicy, np, candidateEvents, tp)
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
	ReleaseID         string
	ManifestDigest    string
	Mode              string
	DeletePolicy      string
	SourceOwner       string
	ProjectionVersion int64
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
	if opts.ProjectionVersion <= 0 {
		opts.ProjectionVersion = time.Now().UTC().UnixMilli()
	}
	return opts
}

func PublishImportedPostLifecycle(
	ctx context.Context,
	redisAddr string,
	redisDB int,
	posts []PostDoc,
	deletedPostIDs []string,
	opts ImportOptions,
	occurredAt time.Time,
) (int, error) {
	opts = NormalizeImportOptions(opts)
	router, err := platformredis.NewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general": {
				Mode:           "standalone",
				Addr:           redisAddr,
				DB:             redisDB,
				DialTimeoutMs:  3000,
				ReadTimeoutMs:  3000,
				WriteTimeoutMs: 3000,
			},
		},
		DefaultScene: "general",
	})
	if err != nil {
		return 0, fmt.Errorf("configure Redis lifecycle publisher: %w", err)
	}
	publisher := postmessaging.NewPostLifecycleStreamPublisher(router.Scene("general"))
	for _, post := range posts {
		contentIdentity, err := canonicalImportedContentIdentity(post.ContentIdentity)
		if err != nil {
			return 0, fmt.Errorf("%s: %w", post.PostRef, err)
		}
		entityRefs := post.NormalizedEntityRefs
		if len(entityRefs) == 0 {
			entityRefs = post.EntityRefs
		}
		media := ImportedMediaFields(importedPostAssets(post))
		body := post.ArticleMarkdown
		summary := post.ArticleDigest
		if post.ContentType == "image" {
			body = post.Body
			summary = post.Body
		}
		payload, err := json.Marshal(bson.M{
			"postId":           RuntimePostID(post.PostRef),
			"status":           "published",
			"visibility":       "public",
			"moderationStatus": importedModerationStatus,
			"contentType":      post.ContentType,
			"contentIdentity":  contentIdentity,
			"authorId":         post.AuthorID,
			"title":            post.Title,
			"body":             body,
			"summary":          summary,
			"mediaUrls":        media.MediaURLs,
			"coverUrl":         media.CoverURL,
			"thumbnailUrl":     media.ThumbnailURL,
			"videoUrl":         media.VideoURL,
			"width":            media.Width,
			"height":           media.Height,
			"durationMs":       media.DurationMs,
			"tagRefs":          post.TagRefs,
			"entityRefs":       entityRefs,
			"contentVertical":  post.Angle,
			"createdAt":        post.CreatedAt,
			"publishedAt":      post.PublishedAt,
			"updatedAt":        post.UpdatedAt,
			"releaseId":        opts.ReleaseID,
		})
		if err != nil {
			return 0, fmt.Errorf("encode imported post lifecycle %s: %w", post.PostRef, err)
		}
		postID := RuntimePostID(post.PostRef)
		if err := publisher.Publish(ctx, postports.OutboxEvent{
			EventID:          fmt.Sprintf("data-release:%s:%s:PostPublished", opts.ReleaseID, postID),
			EventType:        "PostPublished",
			AggregateType:    "Post",
			AggregateID:      postID,
			AggregateVersion: opts.ProjectionVersion,
			Payload:          payload,
			OccurredAt:       occurredAt,
		}); err != nil {
			return 0, fmt.Errorf("%s: %w", post.PostRef, err)
		}
	}
	for _, postID := range deletedPostIDs {
		postID = strings.TrimSpace(postID)
		if postID == "" {
			return 0, fmt.Errorf("deleted post lifecycle identity is empty")
		}
		payload, err := json.Marshal(bson.M{
			"postId":      postID,
			"releaseId":   opts.ReleaseID,
			"sourceOwner": opts.SourceOwner,
			"deletedAt":   occurredAt,
		})
		if err != nil {
			return 0, fmt.Errorf("encode imported post deletion %s: %w", postID, err)
		}
		if err := publisher.Publish(ctx, postports.OutboxEvent{
			EventID:          fmt.Sprintf("data-release:%s:%s:PostDeleted", opts.ReleaseID, postID),
			EventType:        "PostDeleted",
			AggregateType:    "Post",
			AggregateID:      postID,
			AggregateVersion: opts.ProjectionVersion,
			Payload:          payload,
			OccurredAt:       occurredAt,
		}); err != nil {
			return 0, fmt.Errorf("%s: %w", postID, err)
		}
	}
	return len(posts) + len(deletedPostIDs), nil
}

// MissingImportedPostIDs freezes the exact deletion set before the Content
// owner applies its local tombstone/hard-delete policy. The same identities are
// then published as PostDeleted so Recommendation can remove stale candidates.
func MissingImportedPostIDs(
	ctx context.Context,
	coll *mongo.Collection,
	posts []PostDoc,
	opts ImportOptions,
) ([]string, error) {
	opts = NormalizeImportOptions(opts)
	if !missingPolicyEnabled(opts) || opts.DeletePolicy == "none" {
		return nil, nil
	}
	cursor, err := coll.Find(ctx, bson.M{
		"sourceOwner": opts.SourceOwner,
		"postRef":     bson.M{"$nin": desiredPostRefs(posts)},
		"$or": bson.A{
			bson.M{"lifecycleStatus": bson.M{"$ne": "tombstone"}},
			bson.M{"deletedByReleaseId": bson.M{"$ne": opts.ReleaseID}},
		},
	}, options.Find().SetProjection(bson.M{"_id": 1}).SetSort(bson.D{{Key: "_id", Value: 1}}))
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)
	identities := make([]string, 0)
	for cursor.Next(ctx) {
		var document struct {
			ID string `bson:"_id"`
		}
		if err := cursor.Decode(&document); err != nil {
			return nil, err
		}
		if strings.TrimSpace(document.ID) == "" {
			return nil, fmt.Errorf("imported Post has an empty runtime identity")
		}
		identities = append(identities, document.ID)
	}
	if err := cursor.Err(); err != nil {
		return nil, err
	}
	return identities, nil
}

func sourceHash(v any) string {
	raw, _ := json.Marshal(v)
	sum := sha256.Sum256(raw)
	return hex.EncodeToString(sum[:])
}

func RuntimePostID(postRef string) string {
	ref := strings.TrimSpace(postRef)
	if ref == "" {
		return ""
	}
	sum := sha256.Sum256([]byte("qwq-content-post:" + ref))
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
	PostRef     string `json:"postRef" bson:"postRef"`
	PostID      string `json:"postId" bson:"postId"`
	ContentType string `json:"contentType" bson:"contentType"`
	AuthorID    string `json:"authorId" bson:"authorId"`
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
		postID := RuntimePostID(storagePostRef)
		reportPostRef, err := CanonicalImportReportPostRef(storagePostRef)
		if err != nil {
			return nil, err
		}
		if storagePostRef == "" || postID == "" || contentType == "" || authorID == "" {
			return nil, fmt.Errorf("imported post binding requires postRef, contentType, and authorId")
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
			PostRef: reportPostRef, PostID: postID, ContentType: contentType, AuthorID: authorID,
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
		id := RuntimePostID(p.PostRef)
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

func UpsertPostsWithOptions(ctx context.Context, coll *mongo.Collection, posts []PostDoc, now time.Time, opts ImportOptions) (int, error) {
	opts = NormalizeImportOptions(opts)
	n := 0
	for _, p := range posts {
		contentIdentity, err := canonicalImportedContentIdentity(p.ContentIdentity)
		if err != nil {
			return n, fmt.Errorf("%s: %w", p.PostRef, err)
		}
		postID := RuntimePostID(p.PostRef)
		if postID == "" {
			return n, fmt.Errorf("postRef is required to derive runtime postId")
		}
		newHash := sourceHash(p)
		runtimeEntityRefs := p.NormalizedEntityRefs
		if len(runtimeEntityRefs) == 0 {
			runtimeEntityRefs = p.EntityRefs
		}
		media := ImportedMediaFields(importedPostAssets(p))
		body := p.ArticleMarkdown
		summary := p.ArticleDigest
		if p.ContentType == "image" {
			body = p.Body
			summary = p.Body
		}
		doc := bson.M{
			"postRef": p.PostRef, "postId": postID, "contentType": p.ContentType,
			"contentIdentity": contentIdentity, "title": p.Title,
			"angle": p.Angle, "seq": p.Seq, "entityRefs": runtimeEntityRefs, "tagRefs": p.TagRefs,
			"intersectionHints":     p.IntersectionHints,
			"semanticMentions":      p.SemanticMentions,
			"authorId":              p.AuthorID,
			"creatorProfileId":      p.CreatorProfileID,
			"creatorArchetype":      p.CreatorArchetype,
			"creatorProfileVersion": p.CreatorProfileVersion,
			"creatorDisclosure":     p.CreatorDisclosure,
			"experienceClaimMode":   p.ExperienceClaimMode,
			"authorQualitySignals":  p.AuthorQualitySignals,
			"sourceCollectionId":    p.SourceCollectionID,
			"sourcePlatform":        p.SourcePlatform,
			"sourceAttribution":     p.SourceAttribution,
			"creator":               p.Creator,
			"page":                  p.Page,
			"licenseProof":          p.LicenseProof,
			"template":              p.Template, "generatorModel": p.GeneratorModel, "articleTemplate": p.Template,
			"body": body, "summary": summary,
			"mediaUrls": media.MediaURLs, "mediaItems": media.MediaItems, "coverUrl": media.CoverURL,
			"articleMarkdown": p.ArticleMarkdown, "articleDigest": p.ArticleDigest, "articleMarkdownDigest": p.ArticleDigest,
			"articleAssetManifest": p.ArticleAssetManifest,
			"sourceTaskId":         p.SourceTaskId,
			"createdAt":            p.CreatedAt,
			"updatedAt":            p.UpdatedAt,
			"publishedAt":          p.PublishedAt,
			"version":              opts.ProjectionVersion,
			// Path A 导入的 publish 主线文章默认视为已公开发布，保证
			// 在线 search/feed 与 rm_discovery_feed 的 discoverability 口径一致。
			"status":           "published",
			"visibility":       "public",
			"moderationStatus": importedModerationStatus,
			"sourceHash":       newHash,
		}
		applyImportedVideoFields(doc, media)
		for k, v := range releaseFields(opts, now, "active") {
			doc[k] = v
		}
		if err := migrateImportedPostIdentity(ctx, coll, p.PostRef, postID, opts); err != nil {
			return n, err
		}
		if _, err := coll.UpdateOne(ctx,
			bson.M{"postRef": p.PostRef},
			bson.M{"$set": doc, "$setOnInsert": bson.M{"_id": postID}},
			options.UpdateOne().SetUpsert(true),
		); err != nil {
			return n, err
		}
		n++
	}
	return n, nil
}

func migrateImportedPostIdentity(ctx context.Context, coll *mongo.Collection, postRef string, runtimeID string, opts ImportOptions) error {
	var existing struct {
		ID          string `bson:"_id"`
		SourceOwner string `bson:"sourceOwner"`
	}
	err := coll.FindOne(ctx,
		bson.M{"postRef": postRef},
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
	if _, err := coll.DeleteOne(ctx, bson.M{"postRef": postRef, "_id": existing.ID}); err != nil {
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
			"conditionProfile": e.ConditionProfile, "sourceTaskId": e.SourceTaskId,
			"updatedAt": now, "sourceHash": sourceHash(e),
		}
		for k, v := range releaseFields(opts, now, "active") {
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
	return opts.Mode == "sync" || opts.Mode == "reset-source"
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

func UpsertReleaseState(ctx context.Context, coll *mongo.Collection, env string, opts ImportOptions, now time.Time, counts bson.M) error {
	opts = NormalizeImportOptions(opts)
	_, err := coll.UpdateOne(ctx,
		bson.M{"environment": env, "sourceOwner": opts.SourceOwner},
		bson.M{"$set": bson.M{
			"environment": env, "sourceOwner": opts.SourceOwner,
			"activeReleaseId": opts.ReleaseID, "status": "active",
			"manifestDigest": opts.ManifestDigest,
			"readback": bson.M{
				"status": "content_imported",
				"counts": bson.M{
					"posts":          counts["postsUpserted"],
					"discoveryPosts": counts["feedUpserted"],
				},
				"checkedAt": now,
			},
			"mode": opts.Mode, "deletePolicy": opts.DeletePolicy,
			"counts": counts, "updatedAt": now,
		}, "$setOnInsert": bson.M{"createdAt": now}},
		options.UpdateOne().SetUpsert(true),
	)
	return err
}

// ImportLoadedCounts always emits schema-required loaded counters, including
// zero values. JSON consumers reject reports that omit entitiesLoaded=0.
func ImportLoadedCounts(postsLoaded, entitiesLoaded int) bson.M {
	return bson.M{
		"postsLoaded":    postsLoaded,
		"entitiesLoaded": entitiesLoaded,
	}
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
