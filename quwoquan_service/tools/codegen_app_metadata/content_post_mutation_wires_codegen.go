package main

import (
	"fmt"
	"strings"
)

func dartMutationWireFieldType(field string) string {
	switch field {
	case "tags", "mediaUrls", "circleIds":
		return "List<String>?"
	case "articleDocument", "location", "primaryHomepageSnapshot", "deviceInfo", "publishLocation":
		return "CloudJsonMap?"
	default:
		return "String?"
	}
}

func writeContentPostMutationWires(outPath string, svc *serviceFile) {
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
		renderMutationWireClass(&b, sp.className, fields, sp.extraFields)
	}

	writeFile(outPath, b.String())
}

func renderMutationWireClass(b *strings.Builder, className string, fields []string, extra []string) {
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
		fmt.Fprintf(b, "  final %s %s;\n", dartMutationWireFieldType(f), f)
	}
	b.WriteString("\n  CloudJsonMap toWire() {\n    final m = <String, dynamic>{};\n")
	for _, f := range ordered {
		t := dartMutationWireFieldType(f)
		switch t {
		case "List<String>?", "CloudJsonMap?":
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
		t := dartMutationWireFieldType(f)
		switch t {
		case "List<String>?":
			fmt.Fprintf(b, "      %s: _mutationStringList(m['%s']),\n", f, f)
		case "CloudJsonMap?":
			fmt.Fprintf(b, "      %s: _mutationStringKeyedMap(m['%s']),\n", f, f)
		default:
			fmt.Fprintf(b, "      %s: m['%s']?.toString(),\n", f, f)
		}
	}
	b.WriteString("    );\n  }\n}\n\n")
}
