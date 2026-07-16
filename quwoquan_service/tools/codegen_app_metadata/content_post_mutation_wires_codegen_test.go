package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// R-CS06：wire 字段 Dart 类型必须由 fields.yaml 的 metadata `type` 驱动，
// 杜绝按字段名硬编码 switch 的桥接债（R06/R24）。重点验证 []object 不再被
// stringify 成 String?，而是结构化 List<CloudJsonMap>?。
func TestDartMutationWireFieldTypeFromMetadata(t *testing.T) {
	fieldTypes := map[string]string{
		"semanticMentions":        "[]object",
		"reviewAspects":           "[]object",
		"mediaUrls":               "[]string",
		"circleIds":               "[]string",
		"articleAssetManifest":    "object",
		"location":                "GeoPoint",
		"primaryHomepageSnapshot": "object",
		"deviceInfo":              "object",
		"illustrationAssetId":     "ObjectId",
		"sourcePostId":            "ObjectId",
		"title":                   "string",
		"personaContextVersion":   "int",
		"visibility":              "enum",
	}

	cases := map[string]string{
		// []object → 结构化数组（核心回归点）
		"semanticMentions": "List<CloudJsonMap>?",
		"reviewAspects":    "List<CloudJsonMap>?",
		// 其它数组 → 字符串数组
		"mediaUrls": "List<String>?",
		"circleIds": "List<String>?",
		// object / GeoPoint → 对象
		"articleAssetManifest":    "CloudJsonMap?",
		"location":                "CloudJsonMap?",
		"primaryHomepageSnapshot": "CloudJsonMap?",
		"deviceInfo":              "CloudJsonMap?",
		// ObjectId / 标量 → stringify
		"illustrationAssetId":   "String?",
		"sourcePostId":          "String?",
		"title":                 "String?",
		"personaContextVersion": "String?",
		"visibility":            "String?",
		// metadata 未提供类型的可写字段回退 String?
		"unregisteredWritableField": "String?",
	}

	for field, want := range cases {
		if got := dartMutationWireFieldType(field, fieldTypes); got != want {
			t.Errorf("dartMutationWireFieldType(%q) = %q, want %q", field, got, want)
		}
	}
}

func TestContentPostMutationWiresOnlyEmitMetadataWritableFields(t *testing.T) {
	outPath := filepath.Join(t.TempDir(), "content_post_mutation_wires.g.dart")
	writeContentPostMutationWires(
		outPath,
		&serviceFile{
			APIRoutes: []routeDef{
				{
					Operation:      "CreatePost",
					WritableFields: []string{"contentType"},
				},
			},
		},
		map[string]string{"contentType": "enum"},
	)

	rendered, err := os.ReadFile(outPath)
	if err != nil {
		t.Fatalf("read generated wire: %v", err)
	}
	output := string(rendered)
	if !strings.Contains(output, "this.contentType") {
		t.Fatal("generated CreatePost wire is missing metadata writable field contentType")
	}
	if strings.Contains(output, "_mutationPutOpt(m, 'type', type)") {
		t.Fatal("generated CreatePost wire must not emit non-writable type field")
	}
}
