package main

import (
	"fmt"
	"path/filepath"
	"strings"
)

// HTTP mutation wires for entity homepage-related business-object service metadata.

func emitEntityHomepageMutationWiresFile(outPath string, services map[string]*serviceFile) error {
	rendered, err := renderEntityHomepageMutationWires(services)
	if err != nil {
		return err
	}
	writeFile(outPath, rendered)
	return nil
}

func renderEntityHomepageMutationWires(services map[string]*serviceFile) (string, error) {
	var b strings.Builder
	b.WriteString("// GENERATED FILE — DO NOT EDIT BY HAND.\n")
	b.WriteString("// Source: contracts/metadata/entity/{homepage,homepage_claim_request,homepage_status_report}/service.yaml (writable_fields per operation).\n")
	b.WriteString("// Regenerate: make codegen-app\n\n")

	b.WriteString(`Map<String, dynamic> _entityHomepageMutationPutOpt(Map<String, dynamic> m, String k, Object? v) {
  if (v == null) return m;
  m[k] = v;
  return m;
}

`)

	type spec struct {
		operation             string
		className             string
		sourceObject          string
		requiresWritableField bool
	}
	for _, sp := range []spec{
		{
			operation:             "ReviewHomepageClaimRequest",
			className:             "ReviewHomepageClaimRequestWire",
			sourceObject:          "homepage_claim_request",
			requiresWritableField: true,
		},
		{
			operation:             "ReviewHomepageStatusReport",
			className:             "ReviewHomepageStatusReportWire",
			sourceObject:          "homepage_status_report",
			requiresWritableField: true,
		},
		{
			operation:    "PublishHomepageCandidate",
			className:    "PublishHomepageCandidateWire",
			sourceObject: "homepage",
		},
	} {
		svc := services[sp.sourceObject]
		if svc == nil {
			return "", fmt.Errorf(
				"entity homepage mutation wire source service missing: %s",
				sp.sourceObject,
			)
		}
		fields, found := entityHomepageMutationWritableFields(svc.APIRoutes, sp.operation)
		if !found {
			return "", fmt.Errorf(
				"entity homepage mutation operation missing: %s in %s",
				sp.operation,
				sp.sourceObject,
			)
		}
		if sp.requiresWritableField && len(fields) == 0 {
			return "", fmt.Errorf(
				"entity homepage mutation writable_fields missing: %s in %s",
				sp.operation,
				sp.sourceObject,
			)
		}
		renderEntityHomepageMutationWireClass(&b, sp.className, fields)
	}

	return b.String(), nil
}

func entityHomepageMutationWritableFields(routes []routeDef, operation string) ([]string, bool) {
	for _, route := range routes {
		if strings.EqualFold(route.Operation, operation) {
			return route.WritableFields, true
		}
	}
	return nil, false
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

func writeEntityHomepageMutationWiresFromMetadata(metadataDir, appDir string) error {
	services := make(map[string]*serviceFile, 3)
	for _, objectName := range []string{
		"homepage",
		"homepage_claim_request",
		"homepage_status_report",
	} {
		svcPath := filepath.Join(metadataDir, "entity", objectName, "service.yaml")
		svc, err := readService(svcPath)
		if err != nil {
			return fmt.Errorf(
				"read entity homepage mutation source %s: %w",
				objectName,
				err,
			)
		}
		services[objectName] = svc
	}
	out := filepath.Join(appDir, "lib", "cloud", "runtime", "generated", "entity", "entity_homepage_mutation_wires.g.dart")
	return emitEntityHomepageMutationWiresFile(out, services)
}
