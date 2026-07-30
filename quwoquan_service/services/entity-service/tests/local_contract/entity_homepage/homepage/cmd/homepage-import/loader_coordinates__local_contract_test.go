package homepage_import_test

import (
	"path/filepath"
	"strings"
	"testing"
)

// seedPublishEntityWithCoordinates 复用主线 fixture，但把 _entity.json 的
// coordinates 换成给定原文，用于覆盖发布态坐标 → Homepage.location 的映射。
func seedPublishEntityWithCoordinates(t *testing.T, root, ref, coordinatesJSON string) {
	t.Helper()
	dir := filepath.Join(root, "entities", filepath.FromSlash(ref))
	coordinates := ""
	if strings.TrimSpace(coordinatesJSON) != "" {
		coordinates = `"coordinates":` + coordinatesJSON + `,`
	}
	writeFile(t, filepath.Join(dir, "_entity.json"),
		`{"label":"九寨沟","domain":"地点","type":"景区","sourceTaskId":"旅行/试点",`+
			coordinates+
			`"tagRefs":["Entity/地点/景区/5A景区","Topic/地理/行政区/中国/四川省/阿坝藏族羌族自治州/九寨沟县"],`+
			`"geoTagRef":"Topic/地理/行政区/中国/四川省/阿坝藏族羌族自治州/九寨沟县",`+
			sourceFieldsJSON+`}`)
	writeSemanticHomepagePackage(t, dir, "九寨沟", true)
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
