// spec_ref: specs/feature-tree/shared-homepage-network/spec.md#dom-001
package homepage_import_test

import (
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"

	runtimemedia "quwoquan_service/runtime/media"
	homepagemodel "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/domain/model"
	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/homepageimport"
)

// seedPublishEntityWithCoordinates 复用主线 fixture，但把 manifest.json 的
// coordinates 换成给定原文，用于覆盖发布态坐标 → Homepage.location 的映射。
func seedPublishEntityWithCoordinates(t *testing.T, root, ref, coordinatesJSON string) {
	t.Helper()
	dir := filepath.Join(root, "entities", filepath.FromSlash(ref))
	coordinates := ""
	if strings.TrimSpace(coordinatesJSON) != "" {
		coordinates = `"coordinates":` + coordinatesJSON + `,`
	}
	writeEntityManifest(t, dir, ref,
		`{"label":"九寨沟","domain":"地点","type":"景区",`+
			coordinates+
			`"tagRefs":["Entity/地点/景区/5A景区","Topic/地理/行政区/中国/四川省/阿坝藏族羌族自治州/九寨沟县"],`+
			`"geoTagRef":"Topic/地理/行政区/中国/四川省/阿坝藏族羌族自治州/九寨沟县",`+
			sourceFieldsJSON+`}`)
	writeSemanticHomepagePackage(t, dir, "九寨沟", true)
}

// 地理目录只定位媒体 owner；同名实体靠 manifest 的逻辑 binding 区分。
func TestLoadHomepageProjectionsKeepsLogicalIdentityAcrossGeographyMove(t *testing.T) {
	root := t.TempDir()
	refs := []string{"地点/景区/东山-甲", "地点/景区/东山-乙"}
	paths := []string{"中国/甲省/甲市/景区/东山", "中国/乙省/乙市/景区/东山"}
	for i, objectPath := range paths {
		dir := filepath.Join(root, "entities", filepath.FromSlash(objectPath))
		writeEntityManifest(t, dir, refs[i], `{"label":"东山","domain":"地点","type":"景区",`+sourceFieldsJSON+`}`)
		writeSemanticHomepagePackage(t, dir, strings.ReplaceAll(refs[i], "/", "_"), true)
	}
	before, issues, err := loadHomepageProjections(t, root, nil, "https://media.example.com")
	if err != nil || len(issues) != 0 || len(before) != 2 {
		t.Fatalf("geographic packages: inputs=%+v issues=%v err=%v", before, issues, err)
	}
	byRef := map[string]string{}
	for _, input := range before {
		if input.Title != "东山" || input.HomepageType != "sight" {
			t.Fatalf("directory must not supply display identity: %+v", input)
		}
		byRef[input.EntityRef] = homepagemodel.StableID("", "qwq_data", input.EntityRef, input.HomepageType, input.Title)
	}
	if len(byRef) != 2 || byRef[refs[0]] == "" || byRef[refs[1]] == "" || byRef[refs[0]] == byRef[refs[1]] {
		t.Fatalf("same-name entities must keep distinct logical refs and hp IDs: %v", byRef)
	}

	oldDir := filepath.Join(root, "entities", filepath.FromSlash(paths[0]))
	newDir := filepath.Join(root, "entities", "中国/丙省/丙市/其他分类/改名目录")
	if err := os.MkdirAll(filepath.Dir(newDir), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.Rename(oldDir, newDir); err != nil {
		t.Fatal(err)
	}
	after, issues, err := loadHomepageProjections(t, root, map[string]bool{refs[0]: true}, "https://media.example.com")
	if err != nil || len(issues) != 0 || len(after) != 1 || after[0].EntityRef != refs[0] {
		t.Fatalf("moved object must still match logical filter: inputs=%+v issues=%v err=%v", after, issues, err)
	}
	for _, input := range before {
		if input.EntityRef == refs[0] && !reflect.DeepEqual(input, after[0]) {
			t.Fatalf("moving storage must preserve the entire projection: before=%+v after=%+v", input, after[0])
		}
	}
	if got := homepagemodel.StableID("", "qwq_data", after[0].EntityRef, after[0].HomepageType, after[0].Title); got != byRef[refs[0]] {
		t.Fatalf("hp stable-ID input changed after storage move: %q != %q", got, byRef[refs[0]])
	}
	physical, _, err := loadHomepageProjections(t, root, map[string]bool{"中国/丙省/丙市/其他分类/改名目录": true}, "https://media.example.com")
	if err != nil || len(physical) != 0 {
		t.Fatalf("physical directory must not match logical filter: inputs=%+v err=%v", physical, err)
	}

	authority := releaseMediaAuthority(t, root)
	for id, asset := range authority {
		asset.OwnerRefs = []string{"entities/" + refs[0]}
		asset.RightsSnapshotRefs = []string{"objects/entities/" + refs[0] + "/sources/homepage-cover/source.json"}
		authority[id] = asset
	}
	_, _, err = homepageimport.LoadHomepageProjections(root, map[string]bool{refs[0]: true}, authority,
		runtimemedia.MediaDeliveryBases{Image: "https://media.example.com"})
	if err == nil || !strings.Contains(err.Error(), "ownerRefs") {
		t.Fatalf("logical identity cannot authorize physical storage owner: %v", err)
	}
}

func TestLoadHomepageProjectionsRejectsInvalidManifestWithoutDirectoryFallback(t *testing.T) {
	for _, raw := range []string{
		`{`, `null`, `[]`,
		`{"schema":"wrong","contentType":"homepage","entityRef":"/entity/logical","domain":"地点","type":"景区","label":"名字"}`,
		`{"schema":"quwoquan_data.entity_object","contentType":"article","entityRef":"/entity/logical","domain":"地点","type":"景区","label":"名字"}`,
		`{"schema":"quwoquan_data.entity_object","contentType":"homepage","entityRef":"logical","domain":"地点","type":"景区","label":"名字"}`,
		`{"schema":"quwoquan_data.entity_object","contentType":"homepage","entityRef":"/entity/","domain":"地点","type":"景区","label":"名字"}`,
		`{"schema":"quwoquan_data.entity_object","contentType":"homepage","entityRef":"/entity/logical","type":"景区","label":"名字"}`,
		`{"schema":"quwoquan_data.entity_object","contentType":"homepage","entityRef":"/entity/logical","domain":"地点","label":"名字"}`,
		`{"schema":"quwoquan_data.entity_object","contentType":"homepage","entityRef":"/entity/logical","domain":"地点","type":"景区"}`,
	} {
		t.Run(raw, func(t *testing.T) {
			root := t.TempDir()
			dir := filepath.Join(root, "entities", "地点/景区/旧名称")
			writeFile(t, filepath.Join(dir, "manifest.json"), raw)
			writeFile(t, filepath.Join(dir, "page.md"), "# 正文\n")
			// 即使旧 anchor 合法也不得挽救坏 manifest。
			writeFile(t, filepath.Join(dir, "_entity.json"), `{"label":"旧名称","domain":"地点","type":"景区",`+sourceFieldsJSON+`}`)
			inputs, _, err := homepageimport.LoadHomepageProjections(root, nil, nil, runtimemedia.MediaDeliveryBases{})
			if err == nil || len(inputs) != 0 || !strings.Contains(err.Error(), "manifest.json") {
				t.Fatalf("invalid manifest must fail, not use anchor/directory defaults: inputs=%+v err=%v", inputs, err)
			}
		})
	}
}

func TestLoadHomepageProjectionsNeverReadsRetiredAnchor(t *testing.T) {
	root := t.TempDir()
	dir := filepath.Join(root, "entities", "中国/甲省/景区/旧目录名")
	writeFile(t, filepath.Join(dir, "_entity.json"), `{not-json`)
	writeFile(t, filepath.Join(dir, "page.md"), "# 正文\n")
	inputs, _, err := homepageimport.LoadHomepageProjections(root, nil, nil, runtimemedia.MediaDeliveryBases{})
	if err != nil || len(inputs) != 0 {
		t.Fatalf("anchor-only directory must not be read: inputs=%+v err=%v", inputs, err)
	}
	writeEntityManifest(t, dir, "地点/景区/冻结名字", `{"label":"显示名字","domain":"地点","type":"景区",`+sourceFieldsJSON+`}`)
	inputs, issues, err := loadHomepageProjections(t, root, nil, "")
	if err != nil || len(issues) != 0 || len(inputs) != 1 || inputs[0].EntityRef != "地点/景区/冻结名字" || inputs[0].Title != "显示名字" {
		t.Fatalf("valid manifest must ignore malformed retired anchor: inputs=%+v issues=%v err=%v", inputs, issues, err)
	}
}

// 发布态 coordinates{lat,lon} 必须映射成 Homepage location（latitude/longitude），
// 这是 2dsphere 索引与搜索 filters.near「附近」的唯一供给入口。
func TestLoadHomepageProjectionsMapsCoordinatesToLocation(t *testing.T) {
	root := t.TempDir()
	seedPublishEntityWithCoordinates(t, root, "地点/景区/九寨沟", `{"lat":33.2601,"lon":103.9182}`)

	inputs, issues, err := loadHomepageProjections(t, root, nil, "https://media.example.com")
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if len(issues) != 0 {
		t.Fatalf("valid coordinates must not raise issues, got %v", issues)
	}
	if len(inputs) != 1 {
		t.Fatalf("want 1 input, got %d", len(inputs))
	}
	location := inputs[0].Location
	if location == nil {
		t.Fatalf("coordinates must project to homepage location")
	}
	if location.Latitude != 33.2601 || location.Longitude != 103.9182 {
		t.Fatalf("location axes must not be swapped, got %+v", *location)
	}
}

// 缺坐标的实体保持 location 为空：宁可不参与附近召回，也不按行政区中心点推断。
func TestLoadHomepageProjectionsLeavesLocationEmptyWithoutCoordinates(t *testing.T) {
	root := t.TempDir()
	seedPublishEntity(t, root, "地点/景区/九寨沟", true)

	inputs, issues, err := loadHomepageProjections(t, root, nil, "https://media.example.com")
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	if len(issues) != 0 {
		t.Fatalf("missing coordinates must be silent, got %v", issues)
	}
	if len(inputs) != 1 || inputs[0].Location != nil {
		t.Fatalf("missing coordinates must leave location nil, got %+v", inputs)
	}
}

// 坐标不可信时只丢坐标、不丢主页，并且必须留下可归因 issue。
func TestLoadHomepageProjectionsRejectsUntrustworthyCoordinates(t *testing.T) {
	cases := []struct {
		name        string
		coordinates string
		wantIssue   string
	}{
		{name: "缺 lon", coordinates: `{"lat":33.2601}`, wantIssue: "缺少 lat 或 lon"},
		{name: "纬度越界", coordinates: `{"lat":103.9182,"lon":33.2601}`, wantIssue: "越界或为缺省零点"},
		{name: "缺省零点", coordinates: `{"lat":0,"lon":0}`, wantIssue: "越界或为缺省零点"},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			root := t.TempDir()
			seedPublishEntityWithCoordinates(t, root, "地点/景区/九寨沟", tc.coordinates)

			inputs, issues, err := loadHomepageProjections(t, root, nil, "https://media.example.com")
			if err != nil {
				t.Fatalf("load: %v", err)
			}
			if len(inputs) != 1 {
				t.Fatalf("bad coordinates must not drop the homepage, got %d inputs", len(inputs))
			}
			if inputs[0].Location != nil {
				t.Fatalf("bad coordinates must not reach location, got %+v", *inputs[0].Location)
			}
			joined := strings.Join(issues, "\n")
			if !strings.Contains(joined, tc.wantIssue) {
				t.Fatalf("want issue containing %q, got %v", tc.wantIssue, issues)
			}
		})
	}
}
