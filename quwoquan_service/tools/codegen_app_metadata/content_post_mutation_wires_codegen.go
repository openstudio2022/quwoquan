package main

import (
	"fmt"
	"strings"
)

// objectMetaTypes 是 wire 中以 JSON object（CloudJsonMap）承载的 metadata 结构体类型集。
// 标量（string/int/enum/ObjectId/...）一律 stringify 为 String?；仅这里登记的结构体类型走对象 wire。
var objectMetaTypes = map[string]bool{
	"object":   true,
	"GeoPoint": true,
}

// dartMutationWireFieldType 由 contracts/metadata/content/post/fields.yaml 的字段 `type` 驱动
// 渲染 wire 字段 Dart 类型（消除按字段名硬编码 switch 的桥接债，R06/R24）：
//
//	[]object        → List<CloudJsonMap>?（结构化数组，禁止 stringify；如 semanticMentions/reviewAspects）
//	其它 []X         → List<String>?（标量/字符串数组，如 mediaUrls/circleIds）
//	object / GeoPoint → CloudJsonMap?（如 articleAssetManifest/location/primaryHomepageSnapshot/deviceInfo）
//	标量(string/int/enum/ObjectId/...) 及缺失字段 → String?（wire 沿用 stringify 标量语义）
//
// fieldTypes 缺失的写入字段（如 CreatePost 的判别字段 type）回退 String?，与既有行为一致。
func dartMutationWireFieldType(field string, fieldTypes map[string]string) string {
	metaType := strings.TrimSpace(fieldTypes[field])
	switch {
	case metaType == "[]object":
		return "List<CloudJsonMap>?"
	case strings.HasPrefix(metaType, "[]"):
		return "List<String>?"
	case objectMetaTypes[metaType]:
		return "CloudJsonMap?"
	default:
		return "String?"
	}
}

func writeContentPostMutationWires(outPath string, svc *serviceFile, fieldTypes map[string]string) {
	if svc == nil {
		return
	}
	var b strings.Builder
	b.WriteString("// GENERATED FILE — DO NOT EDIT BY HAND.\n")
	b.WriteString("// Source: contracts/metadata/content/post/service.yaml (writable_fields per operation).\n")
	b.WriteString("// Regenerate: make codegen-app\n\n")
	b.WriteString("import 'package:quwoquan_app/cloud/runtime/codec/cloud_wire_json_types.dart';\n\n")

	b.WriteString(`CloudJsonMap _mutationPutOpt(CloudJsonMap m, String k, Object? v) {
  if (v == null) return m;
  m[k] = v;
  return m;
}

List<String>? _mutationStringList(Object? v) {
  if (v == null) return null;
  if (v is List) {
    return v.map((e) => e.toString()).where((s) => s.isNotEmpty).toList(growable: false);
  }
  return null;
}

CloudJsonMap? _mutationStringKeyedMap(Object? v) {
  if (v is! Map) return null;
  return Map<String, dynamic>.from(v);
}

List<CloudJsonMap>? _mutationMapList(Object? v) {
  if (v is! List) return null;
  return v
      .whereType<Map>()
      .map((e) => Map<String, dynamic>.from(e))
      .toList(growable: false);
}

`)

	type spec struct {
		op          string
		className   string
		extraFields []string
	}
	for _, sp := range []spec{
		{op: "CreatePost", className: "CreatePostRequestWire", extraFields: []string{"type"}},
		{op: "UpdatePost", className: "UpdatePostRequestWire", extraFields: nil},
		{op: "PublishPost", className: "PublishPostRequestWire", extraFields: nil},
		{op: "UpdatePostSettings", className: "UpdatePostSettingsRequestWire", extraFields: nil},
		{op: "PromotePostToWork", className: "PromotePostToWorkRequestWire", extraFields: nil},
	} {
		fields := findWritableFields(svc.APIRoutes, sp.op)
		renderMutationWireClass(&b, sp.className, fields, sp.extraFields, fieldTypes)
	}

	writeFile(outPath, b.String())
}

func renderMutationWireClass(b *strings.Builder, className string, fields []string, extra []string, fieldTypes map[string]string) {
	all := append(append([]string{}, extra...), fields...)
	seen := map[string]bool{}
	ordered := make([]string, 0, len(all))
	for _, f := range all {
		if f == "" || seen[f] {
			continue
		}
		seen[f] = true
		ordered = append(ordered, f)
	}

	fmt.Fprintf(b, "/// HTTP body for %s (metadata writable_fields).\n", strings.TrimSuffix(className, "RequestWire"))
	b.WriteString("class ")
	b.WriteString(className)
	b.WriteString(" {\n  ")
	b.WriteString(className)
	b.WriteString("({\n")
	for _, f := range ordered {
		fmt.Fprintf(b, "    this.%s,\n", f)
	}
	b.WriteString("  });\n\n")

	for _, f := range ordered {
		fmt.Fprintf(b, "  final %s %s;\n", dartMutationWireFieldType(f, fieldTypes), f)
	}
	b.WriteString("\n  CloudJsonMap toWire() {\n    final m = <String, dynamic>{};\n")
	for _, f := range ordered {
		t := dartMutationWireFieldType(f, fieldTypes)
		switch t {
		case "List<String>?", "List<CloudJsonMap>?", "CloudJsonMap?":
			fmt.Fprintf(b, "    if (%s != null) m['%s'] = %s!;\n", f, f, f)
		default:
			fmt.Fprintf(b, "    _mutationPutOpt(m, '%s', %s);\n", f, f)
		}
	}
	b.WriteString("    return m;\n  }\n\n")

	b.WriteString("  factory ")
	b.WriteString(className)
	b.WriteString(".fromMap(CloudJsonMap m) {\n    return ")
	b.WriteString(className)
	b.WriteString("(\n")
	for _, f := range ordered {
		t := dartMutationWireFieldType(f, fieldTypes)
		switch t {
		case "List<String>?":
			fmt.Fprintf(b, "      %s: _mutationStringList(m['%s']),\n", f, f)
		case "List<CloudJsonMap>?":
			fmt.Fprintf(b, "      %s: _mutationMapList(m['%s']),\n", f, f)
		case "CloudJsonMap?":
			fmt.Fprintf(b, "      %s: _mutationStringKeyedMap(m['%s']),\n", f, f)
		default:
			fmt.Fprintf(b, "      %s: m['%s']?.toString(),\n", f, f)
		}
	}
	b.WriteString("    );\n  }\n}\n\n")
}
