package releaseimport_test

import (
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"runtime"
	"strings"
	"testing"

	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/releaseimport"
)

func TestLoadRejectsRetiredOrMissingSourceAttributionFacts(t *testing.T) {
	for _, invalid := range []string{
		`{"publicationAdmission":"research_release","derivedModifications":[]}`,
		`{"publicationAdmission":"commercial_release","derivedModifications":[]}`,
		`{"publicationAdmission":"production_release"}`,
		`{"publicationAdmission":"production_release","derivedModifications":null}`,
		`{"publicationAdmission":"production_release","derivedModifications":[],"riskAcceptanceId":null}`,
		`{"publicationAdmission":"production_release","derivedModifications":["unknown"]}`,
		`{"publicationAdmission":"production_release","derivedModifications":["crop","crop"]}`,
		`{"publicationAdmission":"production_release","derivedModifications":[],"watermarkKind":"invented"}`,
		`null`,
	} {
		t.Run(invalid, func(t *testing.T) {
			root := t.TempDir()
			manifest := map[string]any{
				"contentType": "article", "publishedAt": "2026-09-09T00:00:00Z",
				"sourceAttribution": json.RawMessage(invalid),
			}
			raw, err := json.Marshal(manifest)
			if err != nil {
				t.Fatal(err)
			}
			writeFile(t, filepath.Join(root, "posts/article/测试/来源/1/manifest.json"), string(raw))
			if _, err := LoadPosts(root, nil, "production"); err == nil || !strings.Contains(err.Error(), "sourceAttribution") {
				t.Fatalf("invalid sourceAttribution must fail closed: %v", err)
			}
		})
	}
}

// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#req-016
func TestLoadSourceAttributionRejectsMissingNullAndInvalidDataFacts(t *testing.T) {
	valid := map[string]any{
		"isOriginal": false, "originalCreatorName": "摄影师", "platform": "Commons",
		"sourcePostUrl": "https://example.com/source", "originalAssetUrl": "https://example.com/image.jpg",
		"attributionText": "摄影师 / CC BY 4.0", "rightsBasis": "CC BY 4.0",
		"commercialAuthorizationStatus": "unverified", "publicationAdmission": "production_release",
		"derivedModifications": []string{}, "watermarkStatus": "unknown", "audioRightsStatus": "unverified",
		"modelReleaseStatus": "unknown", "propertyReleaseStatus": "unknown",
		"collectedAt": "2026-09-09T00:00:00Z", "takedownPolicy": "notice_and_takedown",
	}
	check := func(t *testing.T, field string, value any, remove bool) {
		t.Helper()
		facts := make(map[string]any, len(valid))
		for key, item := range valid {
			facts[key] = item
		}
		if remove {
			delete(facts, field)
		} else {
			facts[field] = value
		}
		raw, err := json.Marshal(map[string]any{
			"contentType": "article", "publishedAt": "2026-09-09T00:00:00Z", "sourceAttribution": facts,
		})
		if err != nil {
			t.Fatal(err)
		}
		root := t.TempDir()
		writeFile(t, filepath.Join(root, "posts/article/测试/来源/1/manifest.json"), string(raw))
		if _, err := LoadPosts(root, nil, "production"); err == nil || !strings.Contains(err.Error(), "sourceAttribution") {
			t.Fatalf("invalid sourceAttribution %s must fail closed: %v", field, err)
		}
	}
	schema := dataSourceAttributionSchema(t)
	if len(schema.Required) != len(valid) {
		t.Fatalf("Data required facts drifted: %v", schema.Required)
	}
	for _, field := range schema.Required {
		if _, exists := valid[field]; !exists {
			t.Fatalf("Data required fact has no valid test value: %s", field)
		}
		t.Run(field+"/missing", func(t *testing.T) { check(t, field, nil, true) })
		t.Run(field+"/null", func(t *testing.T) { check(t, field, nil, false) })
		if _, ok := valid[field].(string); ok {
			t.Run(field+"/empty", func(t *testing.T) { check(t, field, "", false) })
		}
	}
	for _, field := range []string{"commercialAuthorizationStatus", "watermarkStatus", "audioRightsStatus", "watermarkKind"} {
		t.Run(field+"/unknown", func(t *testing.T) { check(t, field, "invented", false) })
	}
	for _, field := range []string{"watermarkKind", "watermarkNote"} {
		t.Run(field+"/null", func(t *testing.T) { check(t, field, nil, false) })
	}
	t.Run("retiredField", func(t *testing.T) { check(t, "riskAcceptanceId", nil, false) })
	t.Run("duplicateModifications", func(t *testing.T) { check(t, "derivedModifications", []string{"crop", "crop"}, false) })
	t.Run("unknownModification", func(t *testing.T) { check(t, "derivedModifications", []string{"unknown"}, false) })
}

type dataAttributionSchema struct {
	Required   []string                   `json:"required"`
	Properties map[string]json.RawMessage `json:"properties"`
}

func dataSourceAttributionSchema(t *testing.T) dataAttributionSchema {
	t.Helper()
	_, source, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("test source path unavailable")
	}
	raw, err := os.ReadFile(filepath.Join(filepath.Dir(source), "../../../../../../../../quwoquan_data/schema/content/post_manifest.schema.json"))
	if err != nil {
		t.Fatal(err)
	}
	var schema struct {
		Defs struct {
			Attribution dataAttributionSchema `json:"sourceAttribution"`
		} `json:"$defs"`
	}
	if err := json.Unmarshal(raw, &schema); err != nil {
		t.Fatal(err)
	}
	return schema.Defs.Attribution
}

// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#req-016
func TestSourceAttributionGeneratedFieldsMatchDataSchema(t *testing.T) {
	schema := dataSourceAttributionSchema(t)
	model := reflect.TypeOf(postmodel.SourceAttribution{})
	if model.NumField() != len(schema.Properties) {
		t.Fatalf("Data/Service attribution field count drift: %d != %d", model.NumField(), len(schema.Properties))
	}
	for index := 0; index < model.NumField(); index++ {
		name := strings.Split(model.Field(index).Tag.Get("json"), ",")[0]
		if _, exists := schema.Properties[name]; !exists {
			t.Fatalf("Service attribution field absent from Data schema: %s", name)
		}
	}
}

func TestLoadArticlePreservesCompleteSourceAttribution(t *testing.T) {
	root := t.TempDir()
	writeFile(
		t,
		filepath.Join(root, "posts/article/攻略/都江堰/1/manifest.json"),
		`{
			"contentType":"article",
			"contentIdentity":"work",
			"entityRefs":["地点/景区/都江堰"],
			"tagRefs":[],
			"publishTitle":"都江堰",
			"publishAngle":"攻略",
			"publishSeq":1,
			"publishedAt":"2026-08-11T01:02:03Z",
			"sourceAttribution":{
				"isOriginal":false,
				"originalCreatorId":"creator-1",
				"originalCreatorName":"摄影师甲",
				"originalCreatorProfileUrl":"https://media.example/creators/creator-1",
				"platform":"Wikimedia Commons",
				"sourcePostUrl":"https://media.example/posts/dujiangyan",
				"originalAssetUrl":"https://media.example/assets/dujiangyan.jpg",
				"attributionText":"摄影师甲 / CC BY-SA 4.0",
				"rightsBasis":"CC BY-SA 4.0",
				"commercialAuthorizationStatus":"verified",
				"publicationAdmission":"production_release",
				"authorizationProofUrl":"https://media.example/proofs/dujiangyan",
				"termsUrl":"https://creativecommons.org/licenses/by-sa/4.0/",
				"derivedModifications":["resize"],
				"watermarkKind":"none",
				"watermarkNote":"原图未见水印",
				"watermarkStatus":"absent",
				"audioRightsStatus":"no_audio",
				"modelReleaseStatus":"not_required",
				"propertyReleaseStatus":"not_required",
				"collectedAt":"2026-08-11T00:00:00Z",
				"takedownPolicy":"quwoquan_standard_notice_and_takedown"
			}
		}`,
	)

	posts, err := LoadPosts(root, nil, "production")
	if err != nil {
		t.Fatal(err)
	}
	if len(posts) != 1 {
		t.Fatalf("want one article post, got %d", len(posts))
	}
	got := posts[0].SourceAttribution
	if got.IsOriginal ||
		got.OriginalCreatorId != "creator-1" ||
		got.OriginalCreatorName != "摄影师甲" ||
		got.OriginalCreatorProfileUrl != "https://media.example/creators/creator-1" ||
		got.Platform != "Wikimedia Commons" ||
		got.SourcePostUrl != "https://media.example/posts/dujiangyan" ||
		got.OriginalAssetUrl != "https://media.example/assets/dujiangyan.jpg" ||
		got.AttributionText != "摄影师甲 / CC BY-SA 4.0" ||
		got.RightsBasis != "CC BY-SA 4.0" ||
		got.CommercialAuthorizationStatus != "verified" ||
		got.PublicationAdmission != "production_release" ||
		got.AuthorizationProofUrl != "https://media.example/proofs/dujiangyan" ||
		got.TermsUrl != "https://creativecommons.org/licenses/by-sa/4.0/" ||
		len(got.DerivedModifications) != 1 || got.DerivedModifications[0] != "resize" ||
		got.WatermarkKind != "none" || got.WatermarkNote != "原图未见水印" ||
		got.WatermarkStatus != "absent" ||
		got.AudioRightsStatus != "no_audio" ||
		got.ModelReleaseStatus != "not_required" ||
		got.PropertyReleaseStatus != "not_required" ||
		got.CollectedAt.UTC().Format("2006-01-02T15:04:05Z") != "2026-08-11T00:00:00Z" ||
		got.TakedownPolicy != "quwoquan_standard_notice_and_takedown" {
		t.Fatalf("complete sourceAttribution drifted: %#v", got)
	}
}
