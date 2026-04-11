package main

import (
	"path/filepath"
	"strings"
)

// HTTP mutation wires for entity/homepage/service.yaml (writable_fields per operation).

func emitEntityHomepageMutationWiresFile(outPath string, svc *serviceFile) {
	if svc == nil {
		return
	}
	var b strings.Builder
	b.WriteString("// GENERATED FILE — DO NOT EDIT BY HAND.\n")
	b.WriteString("// Source: contracts/metadata/entity/homepage/service.yaml (writable_fields per operation).\n")
	b.WriteString("// Regenerate: make codegen-app\n\n")

	b.WriteString(`Map<String, dynamic> _entityHomepageMutationPutOpt(Map<String, dynamic> m, String k, Object? v) {
  if (v == null) return m;
  m[k] = v;
  return m;
}

`)

	type spec struct {
		op        string
		className string
	}
	for _, sp := range []spec{
		{op: "ReviewHomepageClaimRequest", className: "ReviewHomepageClaimRequestWire"},
		{op: "ReviewHomepageStatusReport", className: "ReviewHomepageStatusReportWire"},
		{op: "PublishHomepageCandidate", className: "PublishHomepageCandidateWire"},
	} {
		fields := findWritableFields(svc.APIRoutes, sp.op)
		renderEntityHomepageMutationWireClass(&b, sp.className, fields)
	}

	writeFile(outPath, b.String())
}

func renderEntityHomepageMutationWireClass(b *strings.Builder, className string, fields []string) {
	var nonEmpty []string
	for _, f := range fields {
		if f != "" {
			nonEmpty = append(nonEmpty, f)
		}
	}
	b.WriteString("/// HTTP body for ")
	b.WriteString(strings.TrimSuffix(className, "Wire"))
	b.WriteString(" (metadata writable_fields).\n")
	b.WriteString("class ")
	b.WriteString(className)
	b.WriteString(" {\n")
	if len(nonEmpty) == 0 {
		b.WriteString("  const ")
		b.WriteString(className)
		b.WriteString("();\n\n")
		b.WriteString("  Map<String, dynamic> toWire() => <String, dynamic>{};\n\n")
		b.WriteString("  factory ")
		b.WriteString(className)
		b.WriteString(".fromMap(Map<String, dynamic> m) => ")
		b.WriteString(className)
		b.WriteString("();\n}\n\n")
		return
	}
	b.WriteString("  ")
	b.WriteString(className)
	b.WriteString("({\n")
	for _, f := range nonEmpty {
		b.WriteString("    this.")
		b.WriteString(f)
		b.WriteString(",\n")
	}
	b.WriteString("  });\n\n")

	for _, f := range nonEmpty {
		b.WriteString("  final String? ")
		b.WriteString(f)
		b.WriteString(";\n")
	}
	b.WriteString("\n  Map<String, dynamic> toWire() {\n    final m = <String, dynamic>{};\n")
	for _, f := range nonEmpty {
		b.WriteString("    _entityHomepageMutationPutOpt(m, '")
		b.WriteString(f)
		b.WriteString("', ")
		b.WriteString(f)
		b.WriteString(");\n")
	}
	b.WriteString("    return m;\n  }\n\n")

	b.WriteString("  factory ")
	b.WriteString(className)
	b.WriteString(".fromMap(Map<String, dynamic> m) {\n    return ")
	b.WriteString(className)
	b.WriteString("(\n")
	for _, f := range nonEmpty {
		b.WriteString("      ")
		b.WriteString(f)
		b.WriteString(": m['")
		b.WriteString(f)
		b.WriteString("']?.toString(),\n")
	}
	b.WriteString("    );\n  }\n}\n\n")
}

func writeEntityHomepageMutationWiresFromMetadata(metadataDir, appDir string) {
	homeSvcPath := filepath.Join(metadataDir, "entity", "homepage", "service.yaml")
	entHomeSvc, err := readService(homeSvcPath)
	if err != nil {
		return
	}
	out := filepath.Join(appDir, "lib", "cloud", "runtime", "generated", "entity", "entity_homepage_mutation_wires.g.dart")
	emitEntityHomepageMutationWiresFile(out, entHomeSvc)
}
