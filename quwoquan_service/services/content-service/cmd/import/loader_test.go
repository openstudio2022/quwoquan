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
		`{"contentType":"article","entityRefs":["地点/景区/甲居藏寨"],"tagRefs":["Topic/旅行"],"template":"journal","generatorModel":"agent/x","articleMarkdownDigest":"d1","publishTitle":"甲居藏寨体验","publishAngle":"体验","publishSeq":1,"sourceTaskId":"旅行/环线/川西环线/川西大环线自驾"}`)
	writeFile(t, filepath.Join(root, "posts/article/体验/甲居藏寨体验/1/article.md"), "# 甲居藏寨体验\n正文\n")
	writeFile(t, filepath.Join(root, "posts/article/攻略/色达攻略/1/manifest.json"),
		`{"contentType":"article","entityRefs":["地点/景区/色达"],"tagRefs":[],"publishTitle":"色达攻略","publishAngle":"攻略","publishSeq":1}`)
	writeFile(t, filepath.Join(root, "posts/article/攻略/色达攻略/1/article.md"), "# 色达攻略\n")
	// 实体（一个有 page.md，一个没有）
	writeFile(t, filepath.Join(root, "entities/地点/景区/甲居藏寨/_entity.json"),
		`{"label":"甲居藏寨","domain":"地点","type":"景区","tagRefs":["Entity/地点/景区"],"conditionProfile":{"regions":["高原","山地"],"seasons":["夏","秋"],"altitudeMeters":3500},"sourceTaskId":"旅行/环线/川西环线/川西大环线自驾"}`)
	writeFile(t, filepath.Join(root, "entities/地点/景区/甲居藏寨/page.md"), "# 甲居藏寨\n")
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
	if p.SourceTaskId != "旅行/环线/川西环线/川西大环线自驾" {
		t.Fatalf("sourceTaskId not loaded: %q", p.SourceTaskId)
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
