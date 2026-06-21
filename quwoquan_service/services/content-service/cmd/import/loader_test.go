package main

import (
	"os"
	"path/filepath"
	"testing"
)

func writeFile(t *testing.T, path, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatal(err)
	}
}

func fixturePublish(t *testing.T) string {
	t.Helper()
	root := t.TempDir()
	// 两篇文章
	writeFile(t, filepath.Join(root, "posts/article/体验/甲居藏寨体验/1/manifest.json"),
		`{"contentType":"article","authorId":"builtin_travel_blogger","creatorProfileId":"qwq_creator_travel_blogger_001","creatorArchetype":"travel_blogger","creatorProfileVersion":"1.0.0","creatorDisclosure":{"type":"platform_virtual_creator","displayText":"平台虚拟创作者","visible":true},"experienceClaimMode":"editorial_synthesis","authorQualitySignals":{"qualityScore":0.85,"fatigueScore":0.2,"riskTier":"low"},"entityRefs":["地点/景区/甲居藏寨"],"normalizedEntityRefs":["entity:景区:甲居藏寨"],"tagRefs":["Topic/旅行"],"template":"journal","generatorModel":"agent/x","articleMarkdownDigest":"sha256:1111111111111111111111111111111111111111111111111111111111111111","publishTitle":"甲居藏寨体验","publishAngle":"体验","publishSeq":1,"sourceTaskId":"旅行/环线/川西环线/川西大环线自驾","createdAt":"2026-05-01T00:00:00Z","updatedAt":"2026-05-03T00:00:00Z","publishedAt":"2026-05-04T00:00:00Z","articleAssetManifest":{"schemaVersion":1,"articleMarkdownVersion":"qwq-rich-md/1","articleMarkdownDigest":"sha256:1111111111111111111111111111111111111111111111111111111111111111","documentSha256":"sha256:1111111111111111111111111111111111111111111111111111111111111111","assetManifestSha256":"sha256:2222222222222222222222222222222222222222222222222222222222222222","documentVersionSha256":"sha256:3333333333333333333333333333333333333333333333333333333333333333","assets":[{"assetId":"cover","objectKey":"media/objects/sha256/aa/aa/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.jpg","cdnUrl":"https://img.example.com/media/objects/sha256/aa/aa/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.jpg","sha256":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}]}}`)
	writeFile(t, filepath.Join(root, "posts/article/体验/甲居藏寨体验/1/article.md"), "# 甲居藏寨体验\n正文\n")
	writeFile(t, filepath.Join(root, "posts/article/攻略/色达攻略/1/manifest.json"),
		`{"contentType":"article","entityRefs":["地点/景区/色达"],"tagRefs":[],"publishTitle":"色达攻略","publishAngle":"攻略","publishSeq":1,"createdAt":"2026-04-01T00:00:00Z","updatedAt":"2026-04-01T00:00:00Z","publishedAt":"2026-04-02T00:00:00Z"}`)
	writeFile(t, filepath.Join(root, "posts/article/攻略/色达攻略/1/article.md"), "# 色达攻略\n")
	// 实体（一个有 page.md，一个没有）
	writeFile(t, filepath.Join(root, "entities/地点/景区/甲居藏寨/_entity.json"),
		`{"label":"甲居藏寨","domain":"地点","type":"景区","tagRefs":["Entity/地点/景区"],"conditionProfile":{"regions":["高原","山地"],"seasons":["夏","秋"],"altitudeMeters":3500},"sourceTaskId":"旅行/环线/川西环线/川西大环线自驾"}`)
	writeFile(t, filepath.Join(root, "entities/地点/景区/甲居藏寨/page.md"), "# 甲居藏寨\n")
	writeFile(t, filepath.Join(root, "entities/地点/景区/甲居藏寨/manifest.json"),
		`{"assets":[{"assetId":"甲居藏寨_homepage_detail","objectKey":"media/objects/sha256/bb/bb/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.png","cdnUrl":"https://img.example.com/media/objects/sha256/bb/bb/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.png","sha256":"sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}]}`)
	writeFile(t, filepath.Join(root, "entities/地点/景区/色达/_entity.json"),
		`{"label":"色达","domain":"地点","type":"景区","tagRefs":[]}`)
	return root
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
	if len(p.ArticleAssetManifest.Assets) != 1 {
		t.Fatalf("articleAssetManifest assets wrong: %+v", p.ArticleAssetManifest)
	}
	if p.ArticleAssetManifest.DocumentVersionSha256 == "" {
		t.Fatalf("documentVersionSha256 not loaded: %+v", p.ArticleAssetManifest)
	}
}

func TestLoadPostsFilteredBySampleBundle(t *testing.T) {
	root := fixturePublish(t)
	filter := toSet([]string{"posts/article/攻略/色达攻略/1"})
	posts, err := LoadPosts(root, filter)
	if err != nil {
		t.Fatal(err)
	}
	if len(posts) != 1 || posts[0].Title != "色达攻略" {
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
	idx := conditionProfileIndex([]EntityDoc{
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
	ents, err := LoadEntities(root, toSet([]string{"地点/景区/色达"}))
	if err != nil {
		t.Fatal(err)
	}
	if len(ents) != 1 || ents[0].Name != "色达" {
		t.Fatalf("entity filter failed: %+v", ents)
	}
}

func TestEmptySampleBundleFiltersToZeroObjects(t *testing.T) {
	root := fixturePublish(t)
	posts, err := LoadPosts(root, toSet(nil))
	if err != nil {
		t.Fatal(err)
	}
	if len(posts) != 0 {
		t.Fatalf("empty post sample must not load full publish tree: %+v", posts)
	}
	ents, err := LoadEntities(root, toSet(nil))
	if err != nil {
		t.Fatal(err)
	}
	if len(ents) != 0 {
		t.Fatalf("empty entity sample must not load full publish tree: %+v", ents)
	}
}

func TestLoadSampleBundle(t *testing.T) {
	root := t.TempDir()
	path := filepath.Join(root, "alpha.json")
	writeFile(t, path, `{"environment":"alpha","posts":["posts/article/攻略/色达攻略/1"],"entities":["地点/景区/色达"]}`)
	b, err := loadSampleBundle(path)
	if err != nil {
		t.Fatal(err)
	}
	if b.Environment != "alpha" || len(b.Posts) != 1 || len(b.Entities) != 1 {
		t.Fatalf("bundle parse wrong: %+v", b)
	}
	if !toSet(b.Posts)["posts/article/攻略/色达攻略/1"] {
		t.Fatalf("toSet from bundle posts failed: %+v", b.Posts)
	}
	if _, err := loadSampleBundle(filepath.Join(root, "missing.json")); err == nil {
		t.Fatalf("expected error for missing bundle")
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
			"objectKey":"media/objects/sha256/cc/cc/cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc.jpg",
			"cdnUrl":"https://img.example.com/media/objects/sha256/cc/cc/cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc.jpg",
			"sha256":"sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc",
			"mimeType":"image/jpeg",
			"sourceCollectionId":"flickr:album:jiuzhaigou-morning",
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
	urls, items, cover := importedMediaFields([]AssetManifestItem{{
		AssetID: "image_1",
		Kind:    "image",
		CDNURL:  "https://img.example.com/image-1.jpg",
		Caption: "晨雾",
		Width:   1600,
		Height:  900,
	}})
	if len(urls) != 1 || len(items) != 1 || cover != urls[0] {
		t.Fatalf("media fields urls=%#v items=%#v cover=%q", urls, items, cover)
	}
	if items[0]["caption"] != "晨雾" || items[0]["width"] != int64(1600) {
		t.Fatalf("media item = %#v", items[0])
	}
}
