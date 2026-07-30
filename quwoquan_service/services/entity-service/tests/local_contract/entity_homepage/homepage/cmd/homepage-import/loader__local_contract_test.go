package homepage_import_test

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	runtimemedia "quwoquan_service/runtime/media"
	application "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application/homepage_orchestration"
	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/homepageimport"
)

func writeFile(t *testing.T, path string, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatalf("mkdir: %v", err)
	}
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("write %s: %v", path, err)
	}
}

const sourceFieldsJSON = `"primarySource":{"sourceKind":"wikipedia","sourceUrl":"https://zh.wikipedia.org/wiki/%E4%B9%9D%E5%AF%A8%E6%B2%9F","title":"九寨沟","fetchedAt":"2026-07-11T00:00:00Z","snapshotHash":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","policyRevision":"encyclopedia-primary","sourceUseMode":"licensed_adaptation"},"sourceUrls":["https://zh.wikipedia.org/wiki/%E4%B9%9D%E5%AF%A8%E6%B2%9F"]`

func seedPublishEntity(t *testing.T, root string, ref string, withMediaBinding bool) {
	t.Helper()
	dir := filepath.Join(root, "entities", filepath.FromSlash(ref))
	writeFile(t, filepath.Join(dir, "_entity.json"),
		`{"label":"九寨沟","domain":"地点","type":"景区","sourceTaskId":"旅行/试点",`+
			`"tagRefs":["Entity/地点/景区/5A景区","Topic/地理/行政区/中国/四川省/阿坝藏族羌族自治州/九寨沟县"],`+
			`"geoTagRef":"Topic/地理/行政区/中国/四川省/阿坝藏族羌族自治州/九寨沟县",`+
			sourceFieldsJSON+`}`)
	writeSemanticHomepagePackage(t, dir, "九寨沟", withMediaBinding)
}

func writeSemanticHomepagePackage(t *testing.T, dir string, title string, withMediaBinding bool) {
	t.Helper()
	assetID := title + "_cover_树正寨_42_a1b2c3d4"
	writeFile(t, filepath.Join(dir, "page.md"),
		"---\ncoverImage: asset://"+assetID+"\n---\n\n# "+title+"\n\n## 概况\n\n真实正文。\n")
	asset := map[string]any{
		"assetId":   assetID,
		"caption":   "树正寨",
		"role":      "cover",
		"sourceRef": "sources/九寨沟__encyclopedia__2489d9dc/source.md",
	}
	if withMediaBinding {
		asset["kind"] = "image"
		asset["sha256"] = "sha256:" + strings.Repeat("a", 64)
	}
	manifest, _ := json.Marshal(map[string]any{"executionId": "20260715--travel-homepage-coverage--cn-sichuan--m1-001", "assets": []any{asset}})
	writeFile(t, filepath.Join(dir, "manifest.json"), string(manifest))
	// CAS closure is intentionally non-semantic. The importer must never use it
	// to decide asset roles or captions.
	assetRef := map[string]any{"assetId": assetID}
	refs, _ := json.Marshal(map[string]any{"assets": []any{assetRef}})
	writeFile(t, filepath.Join(dir, "asset.refs.json"), string(refs))
}

func releaseMediaAuthority(t *testing.T, root string) map[string]runtimemedia.ReleaseMediaAsset {
	t.Helper()
	assets := map[string]runtimemedia.ReleaseMediaAsset{}
	err := filepath.WalkDir(filepath.Join(root, "entities"), func(path string, entry os.DirEntry, err error) error {
		if err != nil || entry.IsDir() || entry.Name() != "manifest.json" {
			return err
		}
		raw, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		var manifest struct {
			Assets []struct {
				AssetID string `json:"assetId"`
				Kind    string `json:"kind"`
				SHA256  string `json:"sha256"`
			} `json:"assets"`
		}
		if err := json.Unmarshal(raw, &manifest); err != nil {
			return err
		}
		entityDir := filepath.Dir(path)
		entityRef, err := filepath.Rel(filepath.Join(root, "entities"), entityDir)
		if err != nil {
			return err
		}
		for _, asset := range manifest.Assets {
			if asset.AssetID == "" || asset.Kind == "" || asset.SHA256 == "" {
				continue
			}
			assets[asset.AssetID] = runtimemedia.ReleaseMediaAsset{
				AssetID:     asset.AssetID,
				Kind:        asset.Kind,
				Version:     1,
				ContentType: "image/jpeg",
				PublicSliceKey: runtimemedia.BuildContentMediaPublicSliceKey(
					asset.Kind, asset.AssetID, 1, "image/jpeg",
				),
				SHA256:    asset.SHA256,
				Bytes:     1,
				OwnerRefs: []string{"entities/" + filepath.ToSlash(entityRef)},
				RightsSnapshotRefs: []string{
					"objects/entities/" + filepath.ToSlash(entityRef) + "/rights_snapshots/asset.json",
				},
			}
		}
		return nil
	})
	if err != nil {
		t.Fatalf("build release media authority: %v", err)
	}
	return assets
}

func loadHomepageProjections(
	t *testing.T,
	root string,
	filter map[string]bool,
	imageBase string,
) ([]application.ImportedHomepageInput, []string, error) {
	t.Helper()
	return homepageimport.LoadHomepageProjections(
		root,
		filter,
		releaseMediaAuthority(t, root),
		runtimemedia.MediaDeliveryBases{Image: imageBase},
	)
}

func TestLoadHomepageProjectionsMapsPageAndAssets(t *testing.T) {
	root := t.TempDir()
	seedPublishEntity(t, root, "地点/景区/九寨沟", true)

	inputs, issues, err := loadHomepageProjections(t, root, nil, "https://media.example.com")
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if len(issues) != 0 {
		t.Fatalf("unexpected issues: %v", issues)
	}
	if len(inputs) != 1 {
		t.Fatalf("expected 1 projection, got %d", len(inputs))
	}
	got := inputs[0]
	if got.EntityRef != "地点/景区/九寨沟" || got.Title != "九寨沟" || got.HomepageType != "sight" {
		t.Fatalf("projection header mismatch: %+v", got)
	}
	if !strings.Contains(got.IntroductionMarkdown, "## 概况") {
		t.Fatalf("introductionMarkdown must carry page.md body")
	}
	if len(got.IntroductionAssets) != 1 {
		t.Fatalf("expected 1 asset, got %d", len(got.IntroductionAssets))
	}
	asset := got.IntroductionAssets[0]
	if !strings.HasPrefix(asset.URL, "https://media.example.com/media/image/s/asset/") ||
		strings.Contains(asset.URL, "objects/sha256") {
		t.Fatalf("asset URL must use the canonical public slice, got %q", asset.URL)
	}
	if asset.Role != "cover" || asset.Caption != "树正寨" {
		t.Fatalf("asset role/caption mismatch: %+v", asset)
	}
	// WP3 统一打标：_entity.json.tagRefs 必须透传为 categoryTags 投影输入。
	if len(got.CategoryTags) != 2 ||
		got.CategoryTags[0] != "Entity/地点/景区/5A景区" ||
		got.CategoryTags[1] != "Topic/地理/行政区/中国/四川省/阿坝藏族羌族自治州/九寨沟县" {
		t.Fatalf("categoryTags must carry _entity.json tagRefs, got %+v", got.CategoryTags)
	}
	if got.PrimarySource == nil || got.PrimarySource.SourceKind != "wikipedia" ||
		len(got.SourceURLs) != 1 || got.SourceURLs[0] != got.PrimarySource.SourceURL {
		t.Fatalf("public source projection mismatch: primary=%+v urls=%v", got.PrimarySource, got.SourceURLs)
	}
}

func TestLoadHomepageProjectionsRejectsUnsafePublicSourceURL(t *testing.T) {
	root := t.TempDir()
	dir := filepath.Join(root, "entities", "地点", "景区", "危险来源")
	writeFile(t, filepath.Join(dir, "_entity.json"),
		`{"label":"危险来源","domain":"地点","type":"景区","primarySource":`+
			`{"sourceKind":"wikipedia","sourceUrl":"http://127.0.0.1/source","policyRevision":"encyclopedia-primary"},`+
			`"sourceUrls":["http://127.0.0.1/source"]}`)
	writeFile(t, filepath.Join(dir, "page.md"), "# 危险来源\n")
	inputs, issues, err := loadHomepageProjections(t, root, nil, "https://media.example.com")
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if len(inputs) != 0 || len(issues) != 1 || !strings.Contains(issues[0], "canonical HTTPS") {
		t.Fatalf("unsafe source URL must block import, inputs=%v issues=%v", inputs, issues)
	}
}

func TestLoadHomepageProjectionsMapsPilotScopePlaceTypes(t *testing.T) {
	// entityTypeToHomepageType 必须覆盖数据工程试点 scope 全集（裁决 6 / WP3-4），
	// 枚举唯一真相源 contracts/metadata/_shared/types.yaml HomepageType。
	root := t.TempDir()
	expected := map[string]string{
		"博物馆":  "museum",
		"遗址":   "heritage_site",
		"古镇":   "ancient_town",
		"宗教场所": "religious_site",
		"打卡地":  "check_in_spot",
		"自然景观": "natural_landscape",
		"公园":   "park",
		"温泉":   "hot_spring",
		"主题乐园": "theme_park",
	}
	for etype := range expected {
		dir := filepath.Join(root, "entities", "地点", etype, "样例"+etype)
		writeFile(t, filepath.Join(dir, "_entity.json"),
			`{"label":"样例`+etype+`","domain":"地点","type":"`+etype+`",`+sourceFieldsJSON+`}`)
		writeSemanticHomepagePackage(t, dir, "样例"+etype, true)
	}

	inputs, issues, err := loadHomepageProjections(t, root, nil, "https://media.example.com")
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if len(issues) != 0 {
		t.Fatalf("pilot scope types must all be mapped, issues=%v", issues)
	}
	if len(inputs) != len(expected) {
		t.Fatalf("expected %d projections, got %d", len(expected), len(inputs))
	}
	for _, input := range inputs {
		parts := strings.Split(input.EntityRef, "/")
		if got := expected[parts[1]]; input.HomepageType != got {
			t.Fatalf("%s: homepageType %q != %q", input.EntityRef, input.HomepageType, got)
		}
	}
}

func TestLoadHomepageProjectionsRequiresEnvironmentMediaBase(t *testing.T) {
	root := t.TempDir()
	seedPublishEntity(t, root, "地点/景区/九寨沟", true)
	_, _, err := loadHomepageProjections(t, root, nil, "")
	if err == nil || !strings.Contains(err.Error(), "public media base URL") {
		t.Fatalf("missing environment media base must fail closed, err=%v", err)
	}
}

func TestLoadHomepageProjectionsReportsUnmaterializedAssets(t *testing.T) {
	root := t.TempDir()
	seedPublishEntity(t, root, "地点/景区/九寨沟", false)
	_, _, err := loadHomepageProjections(t, root, nil, "https://media.example.com")
	if err == nil || !strings.Contains(err.Error(), "absent from release media authority") {
		t.Fatalf("unmaterialized asset must fail closed, err=%v", err)
	}
}

func TestLoadHomepageProjectionsRejectsObjectKeyAndIdentityDrift(t *testing.T) {
	for _, test := range []struct {
		name        string
		mutate      func(string) string
		errorMarker string
	}{
		{
			name: "objectKey",
			mutate: func(raw string) string {
				return strings.Replace(
					raw,
					`"kind":"image"`,
					`"objectKey":"media/objects/sha256/aa/bb/`+strings.Repeat("a", 64)+`.jpg","kind":"image"`,
					1,
				)
			},
			errorMarker: "forbidden objectKey",
		},
		{
			name: "kind",
			mutate: func(raw string) string {
				return strings.Replace(raw, `"kind":"image"`, `"kind":"video"`, 1)
			},
			errorMarker: "kind differs",
		},
		{
			name: "sha256",
			mutate: func(raw string) string {
				return strings.Replace(
					raw,
					`"sha256":"sha256:`+strings.Repeat("a", 64)+`"`,
					`"sha256":"sha256:`+strings.Repeat("b", 64)+`"`,
					1,
				)
			},
			errorMarker: "sha256 differs",
		},
	} {
		t.Run(test.name, func(t *testing.T) {
			root := t.TempDir()
			seedPublishEntity(t, root, "地点/景区/九寨沟", true)
			authority := releaseMediaAuthority(t, root)
			manifestPath := filepath.Join(
				root,
				"entities",
				"地点",
				"景区",
				"九寨沟",
				"manifest.json",
			)
			raw, err := os.ReadFile(manifestPath)
			if err != nil {
				t.Fatal(err)
			}
			writeFile(t, manifestPath, test.mutate(string(raw)))
			_, _, err = homepageimport.LoadHomepageProjections(
				root,
				nil,
				authority,
				runtimemedia.MediaDeliveryBases{Image: "https://image.example.com"},
			)
			if err == nil || !strings.Contains(err.Error(), test.errorMarker) {
				t.Fatalf("%s drift must fail closed, err=%v", test.name, err)
			}
		})
	}
}

func TestLoadHomepageProjectionsRejectsOwnerAndRightsDrift(t *testing.T) {
	for _, test := range []struct {
		name        string
		mutate      func(*runtimemedia.ReleaseMediaAsset)
		errorMarker string
	}{
		{
			name: "owner",
			mutate: func(asset *runtimemedia.ReleaseMediaAsset) {
				asset.OwnerRefs = []string{"entities/地点/景区/其他"}
			},
			errorMarker: "ownerRefs",
		},
		{
			name: "rights",
			mutate: func(asset *runtimemedia.ReleaseMediaAsset) {
				asset.RightsSnapshotRefs =
					[]string{"objects/entities/地点/景区/其他/rights_snapshots/asset.json"}
			},
			errorMarker: "rightsSnapshotRefs",
		},
	} {
		t.Run(test.name, func(t *testing.T) {
			root := t.TempDir()
			seedPublishEntity(t, root, "地点/景区/九寨沟", true)
			authority := releaseMediaAuthority(t, root)
			for assetID, asset := range authority {
				test.mutate(&asset)
				authority[assetID] = asset
			}
			_, _, err := homepageimport.LoadHomepageProjections(
				root,
				nil,
				authority,
				runtimemedia.MediaDeliveryBases{Image: "https://image.example.com"},
			)
			if err == nil || !strings.Contains(err.Error(), test.errorMarker) {
				t.Fatalf("%s drift must fail closed, err=%v", test.name, err)
			}
		})
	}
}

func TestLoadHomepageProjectionsRejectsSemanticRoleDrift(t *testing.T) {
	root := t.TempDir()
	seedPublishEntity(t, root, "地点/景区/九寨沟", true)
	manifestPath := filepath.Join(root, "entities", "地点", "景区", "九寨沟", "manifest.json")
	raw, err := os.ReadFile(manifestPath)
	if err != nil {
		t.Fatalf("read manifest: %v", err)
	}
	mutated := strings.Replace(string(raw), `"role":"cover"`, `"role":"detail"`, 1)
	writeFile(t, manifestPath, mutated)
	_, _, err = loadHomepageProjections(t, root, nil, "https://media.example.com")
	if err == nil || !strings.Contains(err.Error(), "unsupported role") {
		t.Fatalf("semantic role drift must fail closed, err=%v", err)
	}
}

func TestLoadHomepageProjectionsRejectsCoverManifestMismatch(t *testing.T) {
	root := t.TempDir()
	seedPublishEntity(t, root, "地点/景区/九寨沟", true)
	pagePath := filepath.Join(root, "entities", "地点", "景区", "九寨沟", "page.md")
	writeFile(t, pagePath, "---\ncoverImage: asset://other_cover\n---\n\n# 九寨沟\n")
	_, _, err := loadHomepageProjections(t, root, nil, "https://media.example.com")
	if err == nil || !strings.Contains(err.Error(), "does not match semantic cover asset") {
		t.Fatalf("cover mismatch must fail closed, err=%v", err)
	}
}

func TestLoadHomepageProjectionsHonorsSampleBundleFilter(t *testing.T) {
	root := t.TempDir()
	seedPublishEntity(t, root, "地点/景区/九寨沟", true)
	seedPublishEntity(t, root, "地点/景区/黄龙", true)
	inputs, _, err := loadHomepageProjections(t, root, map[string]bool{"地点/景区/黄龙": true}, "https://media.example.com")
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if len(inputs) != 1 || inputs[0].EntityRef != "地点/景区/黄龙" {
		t.Fatalf("filter must keep only bundle entities, got %+v", inputs)
	}
}

func TestLoadHomepageProjectionsSkipsUnknownEntityType(t *testing.T) {
	root := t.TempDir()
	dir := filepath.Join(root, "entities", "食物", "小吃", "钟水饺")
	writeFile(t, filepath.Join(dir, "_entity.json"), `{"label":"钟水饺","domain":"食物","type":"小吃",`+sourceFieldsJSON+`}`)
	writeFile(t, filepath.Join(dir, "page.md"), "# 钟水饺\n")
	inputs, issues, err := loadHomepageProjections(t, root, nil, "")
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if len(inputs) != 0 {
		t.Fatalf("unknown entity type must be skipped, got %+v", inputs)
	}
	if len(issues) != 1 || !strings.Contains(issues[0], "未登记主页类型映射") {
		t.Fatalf("must report mapping gap, got %v", issues)
	}
}
