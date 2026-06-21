// Command import 把 publish 主线的 posts/entities 灌入运行库（mongo）。
//
// 唯一内容真相源是 quwoquan_data/publish；本工具只读消费其目录树，按可选 sample bundle
// 过滤某环境子集，幂等 upsert 到 content/entity 两个库，可重跑。
//
// 用法:
//
//	go run ./services/content-service/cmd/import \
//	  --publish-root ../quwoquan_data/publish \
//	  --sample-bundle ../quwoquan_data/publish/sample_bundles/gamma.json \
//	  --mongo-uri mongodb://localhost:27017 --env gamma
package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"os"
	"strings"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"
)

func main() {
	publishRoot := flag.String("publish-root", "../quwoquan_data/publish", "path to publish mainline")
	sampleBundle := flag.String("sample-bundle", "", "optional sample bundle json (env subset); empty = full")
	mongoURI := flag.String("mongo-uri", "mongodb://localhost:27017", "mongo connection uri")
	postsDB := flag.String("posts-db", "quwoquan_content", "target db for posts")
	entitiesDB := flag.String("entities-db", "quwoquan_entity", "target db for entities")
	env := flag.String("env", "", "environment label (for logging)")
	dryRun := flag.Bool("dry-run", false, "load + report only, do not write mongo")
	releaseID := flag.String("release-id", "", "data release id")
	mode := flag.String("mode", "upsert", "apply mode: upsert|sync|reset-source")
	deletePolicy := flag.String("delete-policy", "none", "missing object policy: none|tombstone|hard-delete")
	sourceOwner := flag.String("source-owner", "qwq_data", "source owner for imported documents")
	reportPath := flag.String("report", "", "optional machine-readable import report path")
	flag.Parse()

	var postFilter, entityFilter map[string]bool
	if *sampleBundle != "" {
		bundle, err := loadSampleBundle(*sampleBundle)
		if err != nil {
			log.Fatalf("load sample bundle: %v", err)
		}
		postFilter = toSet(bundle.Posts)
		entityFilter = toSet(bundle.Entities)
	}

	posts, err := LoadPosts(*publishRoot, postFilter)
	if err != nil {
		log.Fatalf("load posts: %v", err)
	}
	entities, err := LoadEntities(*publishRoot, entityFilter)
	if err != nil {
		log.Fatalf("load entities: %v", err)
	}
	log.Printf("[import] env=%s loaded posts=%d entities=%d", *env, len(posts), len(entities))

	if *dryRun {
		log.Printf("[import] dry-run: not writing mongo")
		_ = WriteImportReport(*reportPath, bson.M{
			"schemaVersion": "quwoquan.content_import_report.v1",
			"status":        "dry-run",
			"environment":   *env,
			"releaseId":     NormalizeImportOptions(ImportOptions{ReleaseID: *releaseID}).ReleaseID,
			"counts":        bson.M{"postsLoaded": len(posts), "entitiesLoaded": len(entities)},
			"auditEvents":   []string{"DataReleasePrepared"},
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
	entityColl := client.Database(*entitiesDB).Collection("entities")
	EnsureUnique(ctx, entityColl, "entityRef", "idx_entity_ref")

	now := time.Now().UTC()
	opts := NormalizeImportOptions(ImportOptions{
		ReleaseID:    *releaseID,
		Mode:         *mode,
		DeletePolicy: *deletePolicy,
		SourceOwner:  *sourceOwner,
	})
	np, err := UpsertPostsWithOptions(ctx, postsColl, posts, now, opts)
	if err != nil {
		log.Fatalf("upsert posts: %v", err)
	}
	ne, err := UpsertEntitiesWithOptions(ctx, entityColl, entities, now, opts)
	if err != nil {
		log.Fatalf("upsert entities: %v", err)
	}
	tp, err := ApplyMissingPostPolicy(ctx, postsColl, posts, now, opts)
	if err != nil {
		log.Fatalf("apply missing post policy: %v", err)
	}
	te, err := ApplyMissingEntityPolicy(ctx, entityColl, entities, now, opts)
	if err != nil {
		log.Fatalf("apply missing entity policy: %v", err)
	}

	// 同写发现流 ReadModel（rm_discovery_feed），让冷启动内容进入 tag/hot/explore 等召回通道；
	// 与在线 DiscoveryFeedProjector / BulkImport 路径字段一致（sourceTaskId + conditionProfile）。
	feedColl := client.Database(*postsDB).Collection("rm_discovery_feed")
	condByEntity := conditionProfileIndex(entities)
	nf, err := UpsertDiscoveryFeedWithOptions(ctx, feedColl, posts, condByEntity, now, opts)
	if err != nil {
		log.Fatalf("upsert discovery feed: %v", err)
	}
	tf, err := ApplyMissingFeedPolicy(ctx, feedColl, posts, now, opts)
	if err != nil {
		log.Fatalf("apply missing feed policy: %v", err)
	}
	stateColl := client.Database(*postsDB).Collection("data_release_state")
	if err := UpsertReleaseState(ctx, stateColl, *env, opts, now, bson.M{
		"postsUpserted": np, "entitiesUpserted": ne, "feedUpserted": nf,
		"postsRemoved": tp, "entitiesRemoved": te, "feedRemoved": tf,
	}); err != nil {
		log.Fatalf("upsert release state: %v", err)
	}
	if err := WriteImportReport(*reportPath, bson.M{
		"schemaVersion": "quwoquan.content_import_report.v1",
		"status":        "active",
		"environment":   *env,
		"releaseId":     opts.ReleaseID,
		"sourceOwner":   opts.SourceOwner,
		"mode":          opts.Mode,
		"deletePolicy":  opts.DeletePolicy,
		"counts": bson.M{
			"postsLoaded": len(posts), "entitiesLoaded": len(entities),
			"postsUpserted": np, "entitiesUpserted": ne, "feedUpserted": nf,
			"postsRemoved": tp, "entitiesRemoved": te, "feedRemoved": tf,
		},
		"auditEvents": []string{"DataReleasePrepared", "DataReleaseActivated"},
		"generatedAt": now,
	}); err != nil {
		log.Fatalf("write import report: %v", err)
	}
	log.Printf("[import] OK env=%s release=%s mode=%s deletePolicy=%s upserted posts=%d entities=%d discoveryFeed=%d removed posts=%d entities=%d feed=%d",
		*env, opts.ReleaseID, opts.Mode, opts.DeletePolicy, np, ne, nf, tp, te, tf)
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
	ReleaseID    string
	Mode         string
	DeletePolicy string
	SourceOwner  string
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

func releaseFields(opts ImportOptions, now time.Time, lifecycleStatus string) bson.M {
	return bson.M{
		"releaseId":            opts.ReleaseID,
		"visibleFromReleaseId": opts.ReleaseID,
		"sourceOwner":          opts.SourceOwner,
		"lifecycleStatus":      lifecycleStatus,
		"releaseUpdatedAt":     now,
	}
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
		postID := RuntimePostID(p.PostRef)
		if postID == "" {
			return n, fmt.Errorf("postRef is required to derive runtime postId")
		}
		newHash := sourceHash(p)
		runtimeEntityRefs := p.NormalizedEntityRefs
		if len(runtimeEntityRefs) == 0 {
			runtimeEntityRefs = p.EntityRefs
		}
		mediaURLs, mediaItems, coverURL := importedMediaFields(p.Assets)
		body := p.ArticleMarkdown
		summary := p.ArticleDigest
		if p.ContentType == "image" {
			body = p.Body
			summary = p.Body
		}
		doc := bson.M{
			"postRef": p.PostRef, "postId": postID, "contentType": p.ContentType, "title": p.Title,
			"angle": p.Angle, "seq": p.Seq, "entityRefs": runtimeEntityRefs, "tagRefs": p.TagRefs,
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
			"creator":               p.Creator,
			"page":                  p.Page,
			"licenseProof":          p.LicenseProof,
			"template":              p.Template, "generatorModel": p.GeneratorModel, "articleTemplate": p.Template,
			"body": body, "summary": summary,
			"mediaUrls": mediaURLs, "mediaItems": mediaItems, "coverUrl": coverURL,
			"articleMarkdown": p.ArticleMarkdown, "articleDigest": p.ArticleDigest, "articleMarkdownDigest": p.ArticleDigest,
			"articleAssetManifest": p.ArticleAssetManifest,
			"sourceTaskId":         p.SourceTaskId,
			"createdAt":            p.CreatedAt,
			"updatedAt":            p.UpdatedAt,
			"publishedAt":          p.PublishedAt,
			// Path A 导入的 publish 主线文章默认视为已公开发布，保证
			// 在线 search/feed 与 rm_discovery_feed 的 discoverability 口径一致。
			"status":     "published",
			"visibility": "public",
			"sourceHash": newHash,
		}
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
	filter := bson.M{"sourceOwner": opts.SourceOwner, "postRef": bson.M{"$nin": desiredPostRefs(posts)}}
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
	filter := bson.M{"sourceOwner": opts.SourceOwner, "entityRef": bson.M{"$nin": desiredEntityRefs(entities)}}
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

// conditionProfileIndex 建立 entityRef→conditionProfile 映射，供发现流投影按主实体冗余条件画像。
func conditionProfileIndex(entities []EntityDoc) map[string]map[string]any {
	idx := make(map[string]map[string]any, len(entities))
	for _, e := range entities {
		if len(e.ConditionProfile) > 0 {
			idx[e.EntityRef] = e.ConditionProfile
		}
	}
	return idx
}

func importedMediaFields(assets []AssetManifestItem) ([]string, []bson.M, string) {
	urls := make([]string, 0, len(assets))
	items := make([]bson.M, 0, len(assets))
	coverURL := ""
	for _, asset := range assets {
		url := asset.CDNURL
		if url == "" {
			continue
		}
		if coverURL == "" {
			coverURL = url
		}
		urls = append(urls, url)
		item := bson.M{
			"assetId": asset.AssetID,
			"kind":    asset.Kind,
			"url":     url,
		}
		if asset.Caption != "" {
			item["caption"] = asset.Caption
		}
		if asset.Role != "" {
			item["role"] = asset.Role
		}
		if asset.Width > 0 {
			item["width"] = asset.Width
		}
		if asset.Height > 0 {
			item["height"] = asset.Height
		}
		items = append(items, item)
	}
	return urls, items, coverURL
}

// UpsertDiscoveryFeed 把发布主线内容同写发现流 ReadModel（rm_discovery_feed）。
// postId 用运行时安全 ID；postRef 保留发布证据引用；conditionProfile 取首个命中实体的画像冗余。
// status/visibility 固定 published/public（冷启动内容均为公开发布），保证召回可见。
// authorId/coverUrl 由 manifest 契约补齐（P1 produce 侧）后再透传；缺省留空不影响 tag/hot/explore 召回。
func UpsertDiscoveryFeed(ctx context.Context, coll *mongo.Collection, posts []PostDoc, condByEntity map[string]map[string]any, now time.Time) (int, error) {
	return UpsertDiscoveryFeedWithOptions(ctx, coll, posts, condByEntity, now, NormalizeImportOptions(ImportOptions{}))
}

func UpsertDiscoveryFeedWithOptions(ctx context.Context, coll *mongo.Collection, posts []PostDoc, condByEntity map[string]map[string]any, now time.Time, opts ImportOptions) (int, error) {
	opts = NormalizeImportOptions(opts)
	n := 0
	for _, p := range posts {
		postID := RuntimePostID(p.PostRef)
		if postID == "" {
			return n, fmt.Errorf("postRef is required to derive discovery feed postId")
		}
		var cond map[string]any
		runtimeEntityRefs := p.NormalizedEntityRefs
		if len(runtimeEntityRefs) == 0 {
			runtimeEntityRefs = p.EntityRefs
		}
		for _, er := range runtimeEntityRefs {
			if c, ok := condByEntity[er]; ok {
				cond = c
				break
			}
		}
		newHash := sourceHash(p)
		set := bson.M{
			"postId":                postID,
			"postRef":               p.PostRef,
			"title":                 p.Title,
			"contentType":           p.ContentType,
			"contentIdentity":       "work",
			"authorId":              p.AuthorID,
			"creatorProfileId":      p.CreatorProfileID,
			"creatorArchetype":      p.CreatorArchetype,
			"creatorProfileVersion": p.CreatorProfileVersion,
			"creatorDisclosure":     p.CreatorDisclosure,
			"experienceClaimMode":   p.ExperienceClaimMode,
			"authorQualitySignals":  p.AuthorQualitySignals,
			"tagRefs":               p.TagRefs,
			"entityRefs":            runtimeEntityRefs,
			"semanticMentions":      p.SemanticMentions,
			"sourceCollectionId":    p.SourceCollectionID,
			"sourcePlatform":        p.SourcePlatform,
			"creator":               p.Creator,
			"page":                  p.Page,
			"licenseProof":          p.LicenseProof,
			"articleAssetManifest":  p.ArticleAssetManifest,
			"sourceTaskId":          p.SourceTaskId,
			"conditionProfile":      cond,
			"status":                "published",
			"visibility":            "public",
			"sourceHash":            newHash,
			"createdAt":             p.CreatedAt,
			"updatedAt":             p.UpdatedAt,
			"publishedAt":           p.PublishedAt,
		}
		mediaURLs, mediaItems, coverURL := importedMediaFields(p.Assets)
		if len(mediaURLs) > 0 {
			set["mediaUrls"] = mediaURLs
			set["mediaItems"] = mediaItems
			set["coverUrl"] = coverURL
		}
		for k, v := range releaseFields(opts, now, "active") {
			set[k] = v
		}
		if err := removeLegacyDiscoveryFeedIdentity(ctx, coll, p.PostRef, postID, opts); err != nil {
			return n, err
		}
		if _, err := coll.UpdateOne(ctx,
			bson.M{"postId": postID},
			bson.M{"$set": set, "$setOnInsert": bson.M{
				"likeCount": int64(0), "commentCount": int64(0),
				"viewCount": int64(0), "recScore": 0.0,
			}},
			options.UpdateOne().SetUpsert(true),
		); err != nil {
			return n, err
		}
		n++
	}
	return n, nil
}

func removeLegacyDiscoveryFeedIdentity(ctx context.Context, coll *mongo.Collection, postRef string, runtimeID string, opts ImportOptions) error {
	filter := bson.M{"postId": postRef}
	if opts.SourceOwner != "" {
		filter["sourceOwner"] = opts.SourceOwner
	}
	res, err := coll.DeleteOne(ctx, filter)
	if err != nil {
		return err
	}
	if res.DeletedCount > 0 {
		return nil
	}
	return nil
}

func ApplyMissingFeedPolicy(ctx context.Context, coll *mongo.Collection, posts []PostDoc, now time.Time, opts ImportOptions) (int64, error) {
	opts = NormalizeImportOptions(opts)
	if !missingPolicyEnabled(opts) || opts.DeletePolicy == "none" {
		return 0, nil
	}
	filter := bson.M{"sourceOwner": opts.SourceOwner, "postId": bson.M{"$nin": desiredRuntimePostIDs(posts)}}
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

func UpsertReleaseState(ctx context.Context, coll *mongo.Collection, env string, opts ImportOptions, now time.Time, counts bson.M) error {
	opts = NormalizeImportOptions(opts)
	_, err := coll.UpdateOne(ctx,
		bson.M{"environment": env, "sourceOwner": opts.SourceOwner},
		bson.M{"$set": bson.M{
			"environment": env, "sourceOwner": opts.SourceOwner,
			"activeReleaseId": opts.ReleaseID, "status": "active",
			"mode": opts.Mode, "deletePolicy": opts.DeletePolicy,
			"counts": counts, "updatedAt": now,
		}, "$setOnInsert": bson.M{"createdAt": now}},
		options.UpdateOne().SetUpsert(true),
	)
	return err
}

func WriteImportReport(path string, report bson.M) error {
	if path == "" {
		return nil
	}
	raw, err := json.MarshalIndent(report, "", "  ")
	if err != nil {
		return err
	}
	raw = append(raw, '\n')
	return os.WriteFile(path, raw, 0o644)
}
