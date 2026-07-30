package releaseimport_test

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"testing"

	runtimemedia "quwoquan_service/runtime/media"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/releaseimport"
)

func writeFile(t *testing.T, path, content string) {
	t.Helper()
	if strings.Contains(filepath.ToSlash(path), "/posts/") &&
		strings.HasSuffix(path, "manifest.json") &&
		strings.Contains(content, `"contentType"`) &&
		!strings.Contains(content, `"contentIdentity"`) {
		// Canonical fixture manifests model data-engineering output. Tests that
		// exercise a missing identity must bypass this fixture authoring helper.
		content = strings.Replace(content, "{", `{"contentIdentity":"work",`, 1)
	}
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
}

func TestLoadPostsRejectsMissingContentIdentity(t *testing.T) {
	root := t.TempDir()
	path := filepath.Join(root, "posts/article/攻略/缺少身份/1/manifest.json")
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(`{
		"contentType":"article",
		"entityRefs":[],
		"tagRefs":[],
		"publishTitle":"缺少身份",
		"publishAngle":"攻略",
		"publishSeq":1,
		"publishedAt":"2026-07-30T00:00:00Z"
	}`), 0o644); err != nil {
		t.Fatal(err)
	}

	_, err := LoadPosts(root, nil)
	if err == nil || !strings.Contains(err.Error(), "contentIdentity is required") {
		t.Fatalf("expected missing contentIdentity rejection, got %v", err)
	}
}

func fixturePublish(t *testing.T) string {
	t.Helper()
	root := t.TempDir()
	// 两篇文章
	writeFile(t, filepath.Join(root, "posts/article/体验/甲居藏寨体验/1/manifest.json"),
		`{"contentType":"article","authorId":"builtin_travel_blogger","creatorProfileId":"qwq_creator_travel_blogger_001","creatorArchetype":"travel_blogger","creatorProfileVersion":"1.0.0","creatorDisclosure":{"type":"platform_virtual_creator","displayText":"平台虚拟创作者","visible":true},"experienceClaimMode":"editorial_synthesis","authorQualitySignals":{"qualityScore":0.85,"fatigueScore":0.2,"riskTier":"low"},"entityRefs":["地点/景区/甲居藏寨"],"normalizedEntityRefs":["entity:景区:甲居藏寨"],"tagRefs":["Topic/旅行"],"intersectionHints":[{"dimension":"content","source":"entityRef","tagRefs":[],"actionType":"view_object","actionTargetId":"entity:景区:甲居藏寨"},{"dimension":"interest","source":"tagRef","tagRefs":["Topic/旅行"],"actionType":"join","actionTargetId":"Topic/旅行"}],"template":"journal","generatorModel":"agent/x","articleMarkdownDigest":"sha256:1111111111111111111111111111111111111111111111111111111111111111","publishTitle":"甲居藏寨体验","publishAngle":"体验","publishSeq":1,"sourceTaskId":"旅行/环线/川西环线/川西大环线自驾","createdAt":"2026-05-01T00:00:00Z","updatedAt":"2026-05-03T00:00:00Z","publishedAt":"2026-05-04T00:00:00Z","articleAssetManifest":{"schema":"article-asset-manifest","markdownDialect":"qwq-rich-md","articleMarkdownDigest":"sha256:1111111111111111111111111111111111111111111111111111111111111111","documentSha256":"sha256:1111111111111111111111111111111111111111111111111111111111111111","assetManifestSha256":"sha256:2222222222222222222222222222222222222222222222222222222222222222","documentVersionSha256":"sha256:3333333333333333333333333333333333333333333333333333333333333333","assets":[{"assetId":"cover","cdnUrl":"https://img.example.com/media/cover.jpg","sha256":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}]}}`)
	writeFile(t, filepath.Join(root, "posts/article/体验/甲居藏寨体验/1/article.md"), "# 甲居藏寨体验\n正文\n")
	writeFile(t, filepath.Join(root, "posts/article/攻略/色达攻略/1/manifest.json"),
		`{"contentType":"article","entityRefs":["地点/景区/色达"],"tagRefs":[],"publishTitle":"色达攻略","publishAngle":"攻略","publishSeq":1,"createdAt":"2026-04-01T00:00:00Z","updatedAt":"2026-04-01T00:00:00Z","publishedAt":"2026-04-02T00:00:00Z"}`)
	writeFile(t, filepath.Join(root, "posts/article/攻略/色达攻略/1/article.md"), "# 色达攻略\n")
	// 实体（一个有 page.md，一个没有）
	writeFile(t, filepath.Join(root, "entities/地点/景区/甲居藏寨/_entity.json"),
		`{"label":"甲居藏寨","domain":"地点","type":"景区","tagRefs":["Entity/地点/景区"],"conditionProfile":{"regions":["高原","山地"],"seasons":["夏","秋"],"altitudeMeters":3500},"sourceTaskId":"旅行/环线/川西环线/川西大环线自驾"}`)
	writeFile(t, filepath.Join(root, "entities/地点/景区/甲居藏寨/page.md"), "# 甲居藏寨\n")
	writeFile(t, filepath.Join(root, "entities/地点/景区/甲居藏寨/asset.refs.json"),
		`{"assets":[{"assetId":"甲居藏寨_homepage_detail","cdnUrl":"https://img.example.com/media/homepage.png","sha256":"sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}]}`)
	writeFile(t, filepath.Join(root, "entities/地点/景区/色达/_entity.json"),
		`{"label":"色达","domain":"地点","type":"景区","tagRefs":[]}`)
	return root
}

func imageManifestWithRights(status, issuesJSON, license, termsURL string) string {
	return fmt.Sprintf(`{
		"contentType":"image",
		"caption":"山间晨雾。",
		"publishedAt":"2026-06-13T02:00:00Z",
		"sourceCollectionId":"collection:morning-mist",
		"assets":[{
			"assetId":"image_1",
			"kind":"image",
			"sha256":"sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
			"sourceCollectionId":"collection:morning-mist",
			"creator":"photographer-a",
			"collectionPageUrl":"https://example.com/albums/morning-mist",
			"license":%q,
			"termsUrl":%q,
			"rightsAuditStatus":%q,
			"rightsAuditIssues":%s
		}]
	}`, license, termsURL, status, issuesJSON)
}

func TestLoadPostsFull(t *testing.T) {
	root := fixturePublish(t)
	posts, err := LoadPosts(root, nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(posts) != 2 {
		t.Fatalf("want 2 posts, got %d", len(posts))
	}
	byRef := map[string]PostDoc{}
	for _, p := range posts {
		byRef[p.PostRef] = p
	}
	p := byRef["posts/article/体验/甲居藏寨体验/1"]
	if p.Title != "甲居藏寨体验" || p.Angle != "体验" || p.ArticleMarkdown == "" {
		t.Fatalf("post not loaded correctly: %+v", p)
	}
	if len(p.EntityRefs) != 1 || p.EntityRefs[0] != "地点/景区/甲居藏寨" {
		t.Fatalf("entityRefs wrong: %+v", p.EntityRefs)
	}
	if len(p.NormalizedEntityRefs) != 1 || p.NormalizedEntityRefs[0] != "entity:景区:甲居藏寨" {
		t.Fatalf("normalizedEntityRefs wrong: %+v", p.NormalizedEntityRefs)
	}
	if p.SourceTaskId != "旅行/环线/川西环线/川西大环线自驾" {
		t.Fatalf("sourceTaskId not loaded: %q", p.SourceTaskId)
	}
	if len(p.IntersectionHints) != 2 || p.IntersectionHints[0].ActionTargetID != "entity:景区:甲居藏寨" {
		t.Fatalf("intersectionHints not loaded: %+v", p.IntersectionHints)
	}
	if p.AuthorID != "builtin_travel_blogger" || p.CreatorProfileID != "qwq_creator_travel_blogger_001" {
		t.Fatalf("creator projection not loaded: %+v", p)
	}
	if p.CreatorDisclosure["visible"] != true || p.ExperienceClaimMode != "editorial_synthesis" {
		t.Fatalf("creator boundary fields not loaded: %+v", p)
	}
	if p.CreatedAt.Year() != 2026 || p.CreatedAt.Month() != 5 || p.CreatedAt.Day() != 1 {
		t.Fatalf("createdAt not loaded from manifest: %+v", p.CreatedAt)
	}
	if p.UpdatedAt.Year() != 2026 || p.UpdatedAt.Month() != 5 || p.UpdatedAt.Day() != 3 {
		t.Fatalf("updatedAt not loaded from manifest: %+v", p.UpdatedAt)
	}
	if p.PublishedAt.Year() != 2026 || p.PublishedAt.Month() != 5 || p.PublishedAt.Day() != 4 {
		t.Fatalf("publishedAt not loaded from manifest: %+v", p.PublishedAt)
	}
	if p.ArticleAssetManifest == nil {
		t.Fatalf("articleAssetManifest not loaded: %+v", p)
	}
	if p.ArticleAssetManifest.Schema != ArticleAssetManifestSchema {
		t.Fatalf(
			"articleAssetManifest.schema = %q, want %q",
			p.ArticleAssetManifest.Schema,
			ArticleAssetManifestSchema,
		)
	}
	if len(p.ArticleAssetManifest.Assets) != 1 {
		t.Fatalf("articleAssetManifest assets wrong: %+v", p.ArticleAssetManifest)
	}
	if p.ArticleAssetManifest.DocumentVersionSha256 == "" {
		t.Fatalf("documentVersionSha256 not loaded: %+v", p.ArticleAssetManifest)
	}
}

func TestLoadVideoPreservesSourceAttribution(t *testing.T) {
	root := t.TempDir()
	writeFile(
		t,
		filepath.Join(root, "posts/video/体验/西湖荷花/1/manifest.json"),
		`{
			"contentType":"video",
			"entityRefs":["地点/景区/杭州西湖"],
			"tagRefs":[],
			"publishTitle":"西湖荷花",
			"publishAngle":"体验",
			"publishSeq":1,
			"publishedAt":"2026-07-28T05:39:06Z",
			"assets":[
				{
					"assetId":"video-1",
					"kind":"video",
					"sha256":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
					"rightsAuditStatus":"verified",
					"rightsAuditIssues":[],
					"posterAssetId":"poster-1"
				},
				{
					"assetId":"poster-1",
					"kind":"image",
					"role":"cover",
					"sha256":"sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
					"rightsAuditStatus":"verified",
					"rightsAuditIssues":[]
				}
			],
			"sourceAttribution":{
				"isOriginal":false,
				"originalCreatorName":"Liuxingy",
				"platform":"Wikimedia Commons",
				"sourcePostUrl":"https://commons.wikimedia.org/wiki/File:west-lake.webm",
				"attributionText":"Liuxingy — CC BY-SA 4.0",
				"rightsBasis":"CC BY-SA 4.0",
				"publicationAdmission":"commercial_release"
			}
		}`,
	)

	posts, err := LoadPosts(root, nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(posts) != 1 {
		t.Fatalf("want one video post, got %d", len(posts))
	}
	attribution, ok := posts[0].SourceAttribution.(map[string]any)
	if !ok {
		t.Fatalf("sourceAttribution not preserved: %#v", posts[0].SourceAttribution)
	}
	if attribution["originalCreatorName"] != "Liuxingy" ||
		attribution["publicationAdmission"] != "commercial_release" {
		t.Fatalf("sourceAttribution drifted: %#v", attribution)
	}
}

func TestImportedPostBindingsAreCompleteAndDeterministic(t *testing.T) {
	posts, err := LoadPosts(fixturePublish(t), nil)
	if err != nil {
		t.Fatal(err)
	}
	bindings, err := ImportedPostBindings(posts[:1])
	if err != nil {
		t.Fatal(err)
	}
	if len(bindings) != 1 {
		t.Fatalf("binding count mismatch: got=%d want=1", len(bindings))
	}
	for index, binding := range bindings {
		if binding.PostRef == "" || binding.PostID == "" || binding.ContentType == "" || binding.AuthorID == "" {
			t.Fatalf("binding %d is incomplete: %+v", index, binding)
		}
		if binding.PostID != RuntimePostID(binding.PostRef) {
			t.Fatalf("binding %d runtime identity drift: %+v", index, binding)
		}
		if index > 0 && bindings[index-1].PostRef >= binding.PostRef {
			t.Fatalf("bindings are not sorted by canonical postRef: %+v", bindings)
		}
	}
}

func TestImportedPostBindingsRejectMissingAuthor(t *testing.T) {
	posts, err := LoadPosts(fixturePublish(t), nil)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := ImportedPostBindings(posts); err == nil {
		t.Fatal("post binding must reject a post without a public author")
	}
}

func TestValidateArticleAssetManifestRejectsNonCanonicalSchema(t *testing.T) {
	for _, schema := range []string{"", "article-asset-manifest-retired"} {
		err := ValidateArticleAssetManifest(
			&ArticleAssetManifestDoc{Schema: schema},
			"posts/article/test",
		)
		if err == nil || !strings.Contains(err.Error(), "articleAssetManifest.schema") {
			t.Fatalf("schema %q must be rejected, got %v", schema, err)
		}
	}
}

func TestLoadPostsFilteredBySampleBundle(t *testing.T) {
	root := fixturePublish(t)
	filter := ToSet([]string{"article/攻略/色达攻略/1"})
	posts, err := LoadPosts(root, filter)
	if err != nil {
		t.Fatal(err)
	}
	if len(posts) != 1 || posts[0].Title != "色达攻略" || posts[0].PostRef != "posts/article/攻略/色达攻略/1" {
		t.Fatalf("sample filter failed: %+v", posts)
	}
}

func TestLoadEntitiesAndPageFlag(t *testing.T) {
	root := fixturePublish(t)
	ents, err := LoadEntities(root, nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(ents) != 2 {
		t.Fatalf("want 2 entities, got %d", len(ents))
	}
	byRef := map[string]EntityDoc{}
	for _, e := range ents {
		byRef[e.EntityRef] = e
	}
	if !byRef["地点/景区/甲居藏寨"].HasPage {
		t.Fatalf("甲居藏寨 should have page")
	}
	if byRef["地点/景区/色达"].HasPage {
		t.Fatalf("色达 should NOT have page")
	}
	jiaju := byRef["地点/景区/甲居藏寨"]
	if jiaju.SourceTaskId != "旅行/环线/川西环线/川西大环线自驾" {
		t.Fatalf("entity sourceTaskId not loaded: %+v", jiaju)
	}
	if jiaju.ConditionProfile == nil {
		t.Fatalf("conditionProfile not loaded: %+v", jiaju)
	}
	if jiaju.AssetManifest == nil {
		t.Fatalf("entity asset manifest not loaded: %+v", jiaju)
	}
	if alt, _ := jiaju.ConditionProfile["altitudeMeters"].(float64); alt != 3500 {
		t.Fatalf("conditionProfile.altitudeMeters wrong: %v", jiaju.ConditionProfile["altitudeMeters"])
	}
	if byRef["地点/景区/色达"].ConditionProfile != nil {
		t.Fatalf("色达 应无 conditionProfile, got %+v", byRef["地点/景区/色达"].ConditionProfile)
	}
}

func TestConditionProfileIndex(t *testing.T) {
	idx := ConditionProfileIndex([]EntityDoc{
		{EntityRef: "地点/景区/甲居藏寨", ConditionProfile: map[string]any{"regions": []any{"高原"}, "altitudeMeters": 3500}},
		{EntityRef: "地点/景区/色达"}, // 无画像，不应入索引
	})
	if _, ok := idx["地点/景区/甲居藏寨"]; !ok {
		t.Fatalf("有画像实体应入索引")
	}
	if _, ok := idx["地点/景区/色达"]; ok {
		t.Fatalf("空画像实体不应入索引")
	}
}

func TestLoadEntitiesFiltered(t *testing.T) {
	root := fixturePublish(t)
	ents, err := LoadEntities(root, ToSet([]string{"地点/景区/色达"}))
	if err != nil {
		t.Fatal(err)
	}
	if len(ents) != 1 || ents[0].Name != "色达" {
		t.Fatalf("entity filter failed: %+v", ents)
	}
}

func TestEmptySampleBundleFiltersToZeroObjects(t *testing.T) {
	root := fixturePublish(t)
	posts, err := LoadPosts(root, ToSet(nil))
	if err != nil {
		t.Fatal(err)
	}
	if len(posts) != 0 {
		t.Fatalf("empty post sample must not load full publish tree: %+v", posts)
	}
	ents, err := LoadEntities(root, ToSet(nil))
	if err != nil {
		t.Fatal(err)
	}
	if len(ents) != 0 {
		t.Fatalf("empty entity sample must not load full publish tree: %+v", ents)
	}
}

func TestDesiredStateLoadRejectsMissingCanonicalObjects(t *testing.T) {
	root := fixturePublish(t)

	_, err := LoadPosts(root, ToSet([]string{
		"article/攻略/色达攻略/1",
		"article/攻略/已隔离文章/1",
	}))
	if err == nil || !strings.Contains(err.Error(), "article/攻略/已隔离文章/1") {
		t.Fatalf("missing desired post must fail closed, got %v", err)
	}

	_, err = LoadEntities(root, ToSet([]string{
		"地点/景区/色达",
		"地点/景区/已隔离实体",
	}))
	if err == nil || !strings.Contains(err.Error(), "地点/景区/已隔离实体") {
		t.Fatalf("missing desired entity must fail closed, got %v", err)
	}
}

func TestLoadReleaseDesiredState(t *testing.T) {
	root := t.TempDir()
	writeFile(t, filepath.Join(root, "payload", "desired_state.json"),
		`{"schema":"quwoquan_data.release_desired_state","releaseId":"release-a","desiredRefs":{"posts":["article/攻略/色达攻略/1"],"entities":["地点/景区/色达"]}}`)
	b, err := LoadReleaseDesiredState(root)
	if err != nil {
		t.Fatal(err)
	}
	if b.ReleaseID != "release-a" || len(b.DesiredRefs.Posts) != 1 || len(b.DesiredRefs.Entities) != 1 {
		t.Fatalf("desired state parse wrong: %+v", b)
	}
	if !ToSet(b.DesiredRefs.Posts)["article/攻略/色达攻略/1"] {
		t.Fatalf("ToSet from desired posts failed: %+v", b.DesiredRefs.Posts)
	}
	if _, err := LoadReleaseDesiredState(filepath.Join(root, "missing")); err == nil {
		t.Fatalf("expected error for missing bundle")
	}
}

func TestReleaseObjectRootRequiresImmutablePayloadObjects(t *testing.T) {
	releaseRoot := t.TempDir()
	objects := filepath.Join(releaseRoot, "payload", "objects")
	if err := os.MkdirAll(objects, 0o755); err != nil {
		t.Fatal(err)
	}
	got, err := ReleaseObjectRoot(releaseRoot)
	if err != nil {
		t.Fatal(err)
	}
	if got != objects {
		t.Fatalf("object root = %q, want %q", got, objects)
	}
	if _, err := ReleaseObjectRoot(filepath.Join(releaseRoot, "missing")); err == nil {
		t.Fatal("missing immutable object closure must fail closed")
	}
}

func TestLoadReleaseDesiredStateRejectsRetiredSchemaAndPathEscape(t *testing.T) {
	root := t.TempDir()
	writeFile(t, filepath.Join(root, "payload", "desired_state.json"),
		`{"schema":"quwoquan.content_sample_bundle","releaseId":"release-a","desiredRefs":{"posts":[],"entities":[]}}`)
	if _, err := LoadReleaseDesiredState(root); err == nil {
		t.Fatal("retired sample schema must be rejected")
	}
	writeFile(t, filepath.Join(root, "payload", "desired_state.json"),
		`{"schema":"quwoquan_data.release_desired_state","releaseId":"release-a","desiredRefs":{"posts":["../escape"],"entities":[]}}`)
	if _, err := LoadReleaseDesiredState(root); err == nil {
		t.Fatal("path escape must be rejected")
	}
}

func TestLoadManifestOnlyImagePost(t *testing.T) {
	root := t.TempDir()
	postDir := filepath.Join(root, "posts/image/摄影/九寨沟晨雾/1")
	writeFile(t, filepath.Join(postDir, "manifest.json"), `{
		"contentType":"image",
		"title":"",
		"caption":"神秘雪谷仍在治理，高原晨雾已经发布。",
		"publishedAt":"2026-06-13T02:00:00Z",
		"sourceCollectionId":"flickr:album:jiuzhaigou-morning",
		"sourcePlatform":"flickr",
		"creator":{"name":"photographer-a"},
		"page":"https://example.com/albums/jiuzhaigou-morning",
		"licenseProof":{"license":"CC BY 4.0"},
		"semanticMentions":[
			{"mentionId":"pending_entity","kind":"entity","surface":"神秘雪谷","location":"body","rangeStart":0,"rangeEnd":4,"status":"pending_review","candidateId":"candidate_entity_1"},
			{"mentionId":"published_tag","kind":"tag","surface":"高原晨雾","location":"body","rangeStart":9,"rangeEnd":13,"status":"published","targetRef":"Topic/摄影/晨雾"}
		],
		"assets":[{
			"assetId":"image_1",
			"kind":"image",
			"cdnUrl":"https://img.example.com/media/image-1.jpg",
			"sha256":"sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
			"mimeType":"image/jpeg",
			"sourceCollectionId":"flickr:album:jiuzhaigou-morning",
			"creator":"photographer-a",
			"collectionPageUrl":"https://example.com/albums/jiuzhaigou-morning",
			"license":"CC BY 4.0",
			"termsUrl":"https://creativecommons.org/licenses/by/4.0/",
			"rightsAuditStatus":"verified",
			"rightsAuditIssues":[],
			"caption":"晨雾"
		}]
	}`)

	posts, err := LoadPosts(root, nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(posts) != 1 {
		t.Fatalf("posts = %d", len(posts))
	}
	post := posts[0]
	if post.Title != "" || post.ArticleMarkdown != "" {
		t.Fatalf("image import must remain manifest-only: %+v", post)
	}
	if post.Body == "" || len(post.Assets) != 1 {
		t.Fatalf("image body/assets not loaded: %+v", post)
	}
	if len(post.EntityRefs) != 0 {
		t.Fatalf("pending entity leaked into refs: %#v", post.EntityRefs)
	}
	if len(post.TagRefs) != 1 || post.TagRefs[0] != "Topic/摄影/晨雾" {
		t.Fatalf("active tag refs = %#v", post.TagRefs)
	}
	if !post.CreatedAt.Equal(post.PublishedAt) || !post.UpdatedAt.Equal(post.PublishedAt) {
		t.Fatalf("manifest-only timestamp fallback failed: created=%v updated=%v published=%v", post.CreatedAt, post.UpdatedAt, post.PublishedAt)
	}
}

func TestLoadManifestOnlyImagePostRejectsUnverifiedRightsWithAuditIssue(t *testing.T) {
	root := t.TempDir()
	writeFile(
		t,
		filepath.Join(root, "posts/image/摄影/晨雾/1/manifest.json"),
		imageManifestWithRights("unverified", `["license evidence pending"]`, "", ""),
	)

	if _, err := LoadPosts(root, nil); err == nil || !strings.Contains(
		err.Error(),
		"cannot enter an immutable release",
	) {
		t.Fatalf("unverified image must fail closed, got %v", err)
	}
}

func TestLoadManifestOnlyImagePostRejectsUnverifiedRightsWithoutIssue(t *testing.T) {
	root := t.TempDir()
	writeFile(
		t,
		filepath.Join(root, "posts/image/摄影/晨雾/1/manifest.json"),
		imageManifestWithRights("unverified", `[]`, "", ""),
	)

	if _, err := LoadPosts(root, nil); err == nil || !strings.Contains(err.Error(), "cannot enter an immutable release") {
		t.Fatalf("unverified image without audit issue must fail, got %v", err)
	}
}

func TestLoadManifestOnlyImagePostRejectsVerifiedRightsWithoutProof(t *testing.T) {
	root := t.TempDir()
	writeFile(
		t,
		filepath.Join(root, "posts/image/摄影/晨雾/1/manifest.json"),
		imageManifestWithRights("verified", `[]`, "CC BY 4.0", ""),
	)

	if _, err := LoadPosts(root, nil); err == nil || !strings.Contains(err.Error(), "missing license or proof") {
		t.Fatalf("verified image without proof must fail, got %v", err)
	}
}

func TestLoadPostRejectsPrivateObjectKey(t *testing.T) {
	root := t.TempDir()
	manifest := imageManifestWithRights(
		"verified",
		`[]`,
		"CC BY 4.0",
		"https://creativecommons.org/licenses/by/4.0/",
	)
	manifest = strings.Replace(
		manifest,
		`"assetId":"image_1",`,
		`"assetId":"image_1","objectKey":"media/objects/sha256/cc/cc/cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc.jpg",`,
		1,
	)
	writeFile(
		t,
		filepath.Join(root, "posts/image/摄影/晨雾/1/manifest.json"),
		manifest,
	)

	if _, err := LoadPosts(root, nil); err == nil || !strings.Contains(
		err.Error(),
		"must not expose private objectKey",
	) {
		t.Fatalf("private objectKey must fail closed, got %v", err)
	}
}

func TestLoadManifestOnlyVideoPostAndCoverContract(t *testing.T) {
	root := t.TempDir()
	postDir := filepath.Join(root, "posts/video/旅行/雪山视频/1")
	writeFile(t, filepath.Join(postDir, "manifest.json"), `{
		"contentType":"video",
		"title":"雪山视频",
		"caption":"雪山短视频。",
		"entityRefs":["地点/景区/雪山"],
		"tagRefs":["Topic/旅行/视频"],
		"createdAt":"2026-06-20T02:00:00Z",
		"updatedAt":"2026-06-20T02:00:00Z",
		"publishedAt":"2026-06-20T02:00:00Z",
		"assets":[{
			"assetId":"clip",
			"kind":"video",
			"sha256":"sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
			"rightsAuditStatus":"verified",
			"rightsAuditIssues":[],
			"mimeType":"video/mp4",
			"posterAssetId":"poster",
			"coverStrategy":"manual",
			"coverFrameTimeMs":0,
			"durationMs":12000,
			"width":1080,
			"height":1920
		},{
			"assetId":"poster",
			"kind":"image",
			"role":"cover",
			"sha256":"sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
			"rightsAuditStatus":"verified",
			"rightsAuditIssues":[],
			"mimeType":"image/webp",
			"width":1080,
			"height":1920
		}]
	}`)

	posts, err := LoadPosts(root, nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(posts) != 1 {
		t.Fatalf("posts = %d", len(posts))
	}
	post := posts[0]
	if post.ContentType != "video" || len(post.Assets) != 2 {
		t.Fatalf("video manifest not loaded: %+v", post)
	}
	releaseAssets := map[string]ReleaseMediaAsset{
		"clip": {
			AssetID: "clip", Kind: "video", Version: 1, ContentType: "video/mp4",
			PublicSliceKey: runtimemedia.BuildContentMediaPublicSliceKey(
				"video", "clip", 1, "video/mp4",
			),
			SHA256:             "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
			Bytes:              1,
			OwnerRefs:          []string{"posts/video/旅行/雪山视频/1"},
			RightsSnapshotRefs: []string{"objects/posts/video/旅行/雪山视频/1/rights_snapshots/video.json"},
		},
		"poster": {
			AssetID: "poster", Kind: "image", Version: 1, ContentType: "image/webp",
			PublicSliceKey: runtimemedia.BuildContentMediaPublicSliceKey(
				"image", "poster", 1, "image/webp",
			),
			SHA256:             "sha256:eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",
			Bytes:              1,
			OwnerRefs:          []string{"posts/video/旅行/雪山视频/1"},
			RightsSnapshotRefs: []string{"objects/posts/video/旅行/雪山视频/1/rights_snapshots/poster.json"},
		},
	}
	if err := BindPostAssetURLs(
		posts,
		releaseAssets,
		runtimemedia.MediaDeliveryBases{
			Image: "https://image.example.com",
			Video: "https://video.example.com",
		},
	); err != nil {
		t.Fatal(err)
	}
	post = posts[0]
	asset := post.Assets[0]
	poster := post.Assets[1]
	if asset.ThumbnailURL != poster.CDNURL || asset.CoverURL != poster.CDNURL {
		t.Fatalf("video cover fields not loaded: %+v", asset)
	}
	if asset.ObjectKey != "" || poster.ObjectKey != "" ||
		!strings.HasPrefix(asset.CDNURL, "https://video.example.com/") ||
		!strings.HasPrefix(poster.CDNURL, "https://image.example.com/") ||
		!strings.Contains(asset.CDNURL, "/media/video/s/asset/clip/v1/source.mp4") ||
		!strings.Contains(poster.CDNURL, "/media/image/s/asset/poster/v1/source.webp") {
		t.Fatalf("importer must consume public slices without retaining CAS keys: %+v %+v", asset, poster)
	}
	if asset.CoverStrategy != "manual" || asset.CoverFrameTimeMs != 0 || asset.DurationMs != 12000 {
		t.Fatalf("video cover strategy/duration wrong: %+v", asset)
	}

	media := ImportedMediaFields(post.Assets)
	if media.VideoURL != asset.CDNURL {
		t.Fatalf("videoUrl = %q, want %q", media.VideoURL, asset.CDNURL)
	}
	if media.ThumbnailURL != asset.ThumbnailURL || media.CoverURL != asset.CoverURL {
		t.Fatalf("cover summary wrong: %+v", media)
	}
	if media.CoverStrategy != "manual" || media.CoverFrameTimeMs != 0 || media.DurationMs != 12000 {
		t.Fatalf("video summary strategy/duration wrong: %+v", media)
	}
	if len(media.MediaItems) != 2 || media.MediaItems[0]["thumbnailUrl"] != asset.ThumbnailURL {
		t.Fatalf("media item thumbnail missing: %+v", media.MediaItems)
	}
	if media.MediaItems[0]["coverFrameTimeMs"] != int64(0) {
		t.Fatalf("media item must preserve first-frame coverFrameTimeMs=0: %+v", media.MediaItems[0])
	}
	publicPayload, err := json.Marshal(media)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(publicPayload), "objectKey") ||
		strings.Contains(string(publicPayload), "objects/sha256") {
		t.Fatalf("public post media fields leaked private CAS identity: %s", publicPayload)
	}
}

func TestBindPostAssetURLsRejectsAmbiguousBaseURL(t *testing.T) {
	posts := []PostDoc{{
		PostRef: "posts/image/旅行/封面/1",
		Assets: []AssetManifestItem{{
			AssetID:   "cover",
			ObjectKey: "media/objects/sha256/aa/aa/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.webp",
		}},
	}}
	for _, base := range []string{
		"",
		"media.example.com",
		"ftp://media.example.com",
		"https://media.example.com/root?token=secret",
		"https://media.example.com/root#fragment",
	} {
		if err := BindPostAssetURLs(
			posts,
			nil,
			runtimemedia.MediaDeliveryBases{Image: base},
		); err == nil {
			t.Fatalf("ambiguous media base %q must fail closed", base)
		}
	}
}

func TestBindPostAssetURLsAllowsEmptyBaselineWithoutMediaBase(t *testing.T) {
	if err := BindPostAssetURLs(nil, nil, runtimemedia.MediaDeliveryBases{}); err != nil {
		t.Fatalf("empty baseline must not require a media base: %v", err)
	}
}

func TestBindPostAssetURLsRejectsIdentityOwnerAndRightsDrift(t *testing.T) {
	tests := []struct {
		name   string
		mutate func(*AssetManifestItem, *ReleaseMediaAsset)
	}{
		{
			name: "kind",
			mutate: func(asset *AssetManifestItem, _ *ReleaseMediaAsset) {
				asset.Kind = "video"
			},
		},
		{
			name: "sha256",
			mutate: func(asset *AssetManifestItem, _ *ReleaseMediaAsset) {
				asset.Sha256 = "sha256:" + strings.Repeat("b", 64)
			},
		},
		{
			name: "owner",
			mutate: func(_ *AssetManifestItem, authority *ReleaseMediaAsset) {
				authority.OwnerRefs = []string{"posts/image/旅行/其他/1"}
			},
		},
		{
			name: "rights",
			mutate: func(_ *AssetManifestItem, authority *ReleaseMediaAsset) {
				authority.RightsSnapshotRefs =
					[]string{"objects/posts/image/旅行/其他/1/rights_snapshots/image.json"}
			},
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			asset := AssetManifestItem{
				AssetID: "cover",
				Kind:    "image",
				Sha256:  "sha256:" + strings.Repeat("a", 64),
			}
			authority := ReleaseMediaAsset{
				AssetID:     "cover",
				Kind:        "image",
				Version:     1,
				ContentType: "image/jpeg",
				PublicSliceKey: runtimemedia.BuildContentMediaPublicSliceKey(
					"image", "cover", 1, "image/jpeg",
				),
				SHA256:    "sha256:" + strings.Repeat("a", 64),
				Bytes:     1,
				OwnerRefs: []string{"posts/image/旅行/封面/1"},
				RightsSnapshotRefs: []string{
					"objects/posts/image/旅行/封面/1/rights_snapshots/image.json",
				},
			}
			test.mutate(&asset, &authority)
			err := BindPostAssetURLs(
				[]PostDoc{{
					PostRef: "posts/image/旅行/封面/1",
					Assets:  []AssetManifestItem{asset},
				}},
				map[string]ReleaseMediaAsset{"cover": authority},
				runtimemedia.MediaDeliveryBases{Image: "https://image.example.com"},
			)
			if err == nil {
				t.Fatalf("%s drift must fail closed", test.name)
			}
		})
	}
}

func TestLoadReleaseMediaAssetsRejectsPrivateCASAndAcceptsCanonicalPublicSlice(t *testing.T) {
	releaseRoot := t.TempDir()
	path := filepath.Join(releaseRoot, "payload/media_manifest.json")
	writeFile(
		t,
		filepath.Join(
			releaseRoot,
			"payload/objects/posts/image/画报/杭州西湖/1/rights_snapshots/a.json",
		),
		`{
			"assetId":"杭州西湖_cover_三潭印月",
			"manifestAsset":{
				"assetId":"杭州西湖_cover_三潭印月",
				"sha256":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
			}
		}`,
	)
	validDocument := `{
		"schema":"quwoquan_data.release_media_manifest",
		"releaseId":"release-a",
		"sourceOwner":"qwq_data",
		"assets":[{
			"assetId":"杭州西湖_cover_三潭印月",
			"kind":"image",
			"version":1,
			"contentType":"image/jpeg",
			"publicSliceKey":"` + runtimemedia.BuildContentMediaPublicSliceKey(
		"image", "杭州西湖_cover_三潭印月", 1, "image/jpeg",
	) + `",
			"sha256":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
			"bytes":12,
			"ownerRefs":["posts/image/画报/杭州西湖/1"],
			"rightsSnapshotRefs":["objects/posts/image/画报/杭州西湖/1/rights_snapshots/a.json"]
		}],
		"issues":[],
		"counts":{"assets":1,"issues":0}
	}`
	writeFile(t, path, validDocument)
	assets, err := LoadReleaseMediaAssets(releaseRoot, "release-a")
	if err != nil {
		t.Fatal(err)
	}
	if len(assets) != 1 || strings.Contains(assets["杭州西湖_cover_三潭印月"].PublicSliceKey, "objects/") {
		t.Fatalf("release media authority not loaded: %+v", assets)
	}
	if _, err := LoadReleaseMediaAssets(releaseRoot, "release-b"); err == nil {
		t.Fatal("release media manifest with a mismatched releaseId must fail closed")
	}

	privateDocument := []byte(strings.Replace(
		validDocument,
		`"publicSliceKey":`,
		`"objectKey":"media/objects/sha256/aa/aa/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.jpg","publicSliceKey":`,
		1,
	))
	if err := os.WriteFile(path, privateDocument, 0o644); err != nil {
		t.Fatal(err)
	}
	if _, err := LoadReleaseMediaAssets(releaseRoot, "release-a"); err == nil {
		t.Fatal("release media manifest exposing objectKey must fail closed")
	}

	var duplicateDocument map[string]any
	if err := json.Unmarshal([]byte(validDocument), &duplicateDocument); err != nil {
		t.Fatal(err)
	}
	rows := duplicateDocument["assets"].([]any)
	duplicate := make(map[string]any, len(rows[0].(map[string]any)))
	for key, value := range rows[0].(map[string]any) {
		duplicate[key] = value
	}
	duplicate["assetId"] = "other-asset"
	duplicateDocument["assets"] = append(rows, duplicate)
	duplicateDocument["counts"].(map[string]any)["assets"] = float64(2)
	raw, err := json.Marshal(duplicateDocument)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, raw, 0o644); err != nil {
		t.Fatal(err)
	}
	if _, err := LoadReleaseMediaAssets(releaseRoot, "release-a"); err == nil {
		t.Fatal("two assets sharing one public slice must fail closed")
	}

	kindDrift := strings.Replace(validDocument, `"kind":"image"`, `"kind":"video"`, 1)
	if err := os.WriteFile(path, []byte(kindDrift), 0o644); err != nil {
		t.Fatal(err)
	}
	if _, err := LoadReleaseMediaAssets(releaseRoot, "release-a"); err == nil {
		t.Fatal("MediaAsset kind/contentType drift must fail closed")
	}
}

func TestValidatePostAuthorsRejectsMissingReleaseCreator(t *testing.T) {
	posts := []PostDoc{{PostRef: "posts/article/旅行/甲/1", AuthorID: "author-a"}}
	if err := ValidatePostAuthors(posts, map[string]bool{}); err == nil {
		t.Fatal("post author outside the release creator closure must be rejected")
	}
	if err := ValidatePostAuthors(posts, map[string]bool{"author-a": true}); err != nil {
		t.Fatalf("release creator author must be accepted: %v", err)
	}
}

func TestValidateCreatorImportReceiptRequiresExactAuthorClosure(t *testing.T) {
	path := filepath.Join(t.TempDir(), "creator-import.json")
	writeFile(t, path, `{
		"schema":"quwoquan.user_creator_import_report",
		"status":"active",
		"releaseId":"release-a",
		"sourceOwner":"qwq_data",
		"authorIds":["author-a"]
	}`)
	if err := ValidateCreatorImportReceipt(path, "release-a", map[string]bool{"author-a": true}); err != nil {
		t.Fatalf("valid creator receipt rejected: %v", err)
	}
	if err := ValidateCreatorImportReceipt(path, "release-a", map[string]bool{"author-b": true}); err == nil {
		t.Fatal("creator receipt with a mismatched author closure must be rejected")
	}
}

func TestLoadPostsValidatesRawActiveRefsNotNormalizedAliases(t *testing.T) {
	root := t.TempDir()
	postDir := filepath.Join(root, "posts/article/攻略/黄山风景区攻略/1")
	writeFile(t, filepath.Join(postDir, "manifest.json"), `{
		"contentType":"article",
		"entityRefs":["/entity/地点/景区/黄山风景区"],
		"normalizedEntityRefs":["entity:景区:黄山风景区"],
		"tagRefs":["Topic/旅行"],
		"semanticMentions":[
			{"mentionId":"published_entity","kind":"entity","surface":"黄山风景区","location":"body","status":"published","targetRef":"/entity/地点/景区/黄山风景区"},
			{"mentionId":"published_tag","kind":"tag","surface":"旅行","location":"manifest","status":"published","targetRef":"Topic/旅行"}
		],
		"publishTitle":"黄山风景区攻略",
		"publishAngle":"攻略",
		"publishSeq":1,
		"createdAt":"2026-06-13T02:00:00Z",
		"updatedAt":"2026-06-13T02:00:00Z",
		"publishedAt":"2026-06-13T02:00:00Z"
	}`)
	writeFile(t, filepath.Join(postDir, "article.md"), "# 黄山风景区攻略\n正文\n")

	posts, err := LoadPosts(root, nil)
	if err != nil {
		t.Fatal(err)
	}
	if len(posts) != 1 {
		t.Fatalf("posts = %d", len(posts))
	}
	if len(posts[0].EntityRefs) != 1 || posts[0].EntityRefs[0] != "/entity/地点/景区/黄山风景区" {
		t.Fatalf("entity projection wrong: %+v", posts[0].EntityRefs)
	}
	if len(posts[0].NormalizedEntityRefs) != 1 || posts[0].NormalizedEntityRefs[0] != "entity:景区:黄山风景区" {
		t.Fatalf("normalized entity projection wrong: %+v", posts[0].NormalizedEntityRefs)
	}
	if len(posts[0].TagRefs) != 1 || posts[0].TagRefs[0] != "Topic/旅行" {
		t.Fatalf("tag projection wrong: %+v", posts[0].TagRefs)
	}
}

func TestLoadPostsRejectsCandidateActiveRef(t *testing.T) {
	root := t.TempDir()
	writeFile(t, filepath.Join(root, "posts/article/攻略/非法候选/1/manifest.json"), `{
		"contentType":"article",
		"entityRefs":["candidate:entity:1"],
		"publishedAt":"2026-06-13T02:00:00Z"
	}`)
	if _, err := LoadPosts(root, nil); err == nil {
		t.Fatal("expected candidate active ref rejection")
	}
}

func TestLoadPostsRejectsDanglingIntersectionHint(t *testing.T) {
	root := t.TempDir()
	writeFile(t, filepath.Join(root, "posts/article/攻略/悬空交集/1/manifest.json"), `{
		"contentType":"article",
		"entityRefs":["地点/景区/黄山风景区"],
		"normalizedEntityRefs":["entity:景区:黄山风景区"],
		"tagRefs":["Topic/旅行"],
		"intersectionHints":[
			{"dimension":"content","source":"entityRef","tagRefs":[],"actionType":"view_object","actionTargetId":"entity:景区:不存在"}
		],
		"publishTitle":"悬空交集",
		"publishAngle":"攻略",
		"publishSeq":1,
		"publishedAt":"2026-06-13T02:00:00Z"
	}`)
	if _, err := LoadPosts(root, nil); err == nil {
		t.Fatal("expected dangling intersection hint rejection")
	}
}

func TestLoadPostsRejectsSystemCreatorWithoutDisclosure(t *testing.T) {
	root := t.TempDir()
	writeFile(t, filepath.Join(root, "posts/article/攻略/作者缺披露/1/manifest.json"), `{
		"contentType":"article",
		"authorId":"agent_author_travel_000000001",
		"creatorProfileId":"agent_creator_travel_000000001",
		"creatorArchetype":"travel_blogger",
		"creatorProfileVersion":"1.0.0",
		"experienceClaimMode":"editorial_synthesis",
		"entityRefs":[],
		"tagRefs":[],
		"publishedAt":"2026-06-13T02:00:00Z"
	}`)
	if _, err := LoadPosts(root, nil); err == nil {
		t.Fatal("expected missing creatorDisclosure rejection")
	}
}

func TestImportedMediaFields(t *testing.T) {
	media := ImportedMediaFields([]AssetManifestItem{{
		AssetID: "image_1",
		Kind:    "image",
		CDNURL:  "https://img.example.com/image-1.jpg",
		Caption: "晨雾",
		Width:   1600,
		Height:  900,
	}})
	if len(media.MediaURLs) != 1 || len(media.MediaItems) != 1 || media.CoverURL != media.MediaURLs[0] {
		t.Fatalf("media fields = %#v", media)
	}
	if media.MediaItems[0]["caption"] != "晨雾" || media.MediaItems[0]["width"] != int64(1600) {
		t.Fatalf("media item = %#v", media.MediaItems[0])
	}
}
