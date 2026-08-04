package main

import (
	"fmt"
	"path/filepath"
	"strings"
)

// recPatchContract mirrors content/content/post/projections/recommendation_realtime_patch.yaml.
// It is the single source of truth for the recommendation realtime patch envelope;
// both this App DTO codegen and the Go runtime struct (runtime/recommendation/
// realtime_patch.go, locked by realtime_patch_test.go) consume it.
type recPatchContract struct {
	RealtimeContract        string `yaml:"realtime_contract"`
	RealtimeChannelTemplate string `yaml:"realtime_channel_template"`
	ClientCodegen           struct {
		PatchTypeEnum        string `yaml:"patch_type_enum"`
		ReasonCodeEnum       string `yaml:"reason_code_enum"`
		RemovalDimensionEnum string `yaml:"removal_dimension_enum"`
		EnvelopeClass        string `yaml:"envelope_class"`
	} `yaml:"client_codegen"`
	PatchTypes []struct {
		ID          string `yaml:"id"`
		Disruption  string `yaml:"disruption"`
		Description string `yaml:"description"`
	} `yaml:"patch_types"`
	ReasonCodes []struct {
		ID          string `yaml:"id"`
		PatchType   string `yaml:"patch_type"`
		Description string `yaml:"description"`
	} `yaml:"reason_codes"`
	RemovalDimensions []struct {
		ID          string `yaml:"id"`
		Description string `yaml:"description"`
	} `yaml:"removal_dimensions"`
	EnvelopeFields []recPatchEnvelopeField `yaml:"envelope_fields"`
}

type recPatchEnvelopeField struct {
	Name        string `yaml:"name"`
	Type        string `yaml:"type"` // string|int|bool|[]string|enum
	DartType    string `yaml:"dart_type"`
	EnumRef     string `yaml:"enum_ref"` // canonical enum class from client_codegen (when type=enum)
	Format      string `yaml:"format"`
	Nullable    bool   `yaml:"nullable"`
	Required    bool   `yaml:"required"`
	Default     string `yaml:"default"`
	Description string `yaml:"description"`
}

func readRecPatchContract(path string) (*recPatchContract, error) {
	var out recPatchContract
	if err := decodeMetadataDocument(path, &out); err != nil {
		return nil, err
	}
	return &out, nil
}

func (c *recPatchContract) enumClassFor(ref string) string {
	canonicalRef := strings.TrimSpace(ref)
	for _, enumClass := range []string{
		c.ClientCodegen.PatchTypeEnum,
		c.ClientCodegen.ReasonCodeEnum,
		c.ClientCodegen.RemovalDimensionEnum,
	} {
		if canonicalRef == strings.TrimSpace(enumClass) {
			return canonicalRef
		}
	}
	return ""
}

// writeRecommendationFeedPatches generates the strongly-typed App DTO + enums +
// parser for the recommendation realtime patch envelope (commercial stage 7 §G).
func writeRecommendationFeedPatches(appDir, metadataDir string) error {
	contractPath := filepath.Join(metadataDir, "content", "content", "post", "projections", "recommendation_realtime_patch.yaml")
	if !hasMetadataDocument(contractPath) {
		return fmt.Errorf("recommendation realtime patch contract is absent")
	}
	contract, err := readRecPatchContract(contractPath)
	if err != nil {
		return fmt.Errorf("read recommendation realtime patch contract: %w", err)
	}
	if err := validateRecPatchContract(contract); err != nil {
		return fmt.Errorf("recommendation realtime patch contract: %w", err)
	}
	out := renderRecommendationFeedPatchesDart(metadataSourceLabel(contractPath), contract)
	outPath := filepath.Join(
		appDir,
		"packages",
		"quwoquan_cloud_contracts",
		"lib",
		"src",
		"generated",
		"realtime",
		"feed_realtime_patch.g.dart",
	)
	writeFile(outPath, out)
	return nil
}

func validateRecPatchContract(c *recPatchContract) error {
	if strings.TrimSpace(c.RealtimeChannelTemplate) == "" {
		return fmt.Errorf("realtime_channel_template is required")
	}
	if len(c.PatchTypes) == 0 {
		return fmt.Errorf("patch_types cannot be empty")
	}
	if len(c.EnvelopeFields) == 0 {
		return fmt.Errorf("envelope_fields cannot be empty")
	}
	validPatchTypes := map[string]struct{}{}
	for _, pt := range c.PatchTypes {
		if strings.TrimSpace(pt.ID) == "" {
			return fmt.Errorf("patch_types entry missing id")
		}
		validPatchTypes[pt.ID] = struct{}{}
	}
	for _, rc := range c.ReasonCodes {
		if strings.TrimSpace(rc.ID) == "" {
			return fmt.Errorf("reason_codes entry missing id")
		}
		if _, ok := validPatchTypes[rc.PatchType]; !ok {
			return fmt.Errorf("reason_code %q references unknown patch_type %q", rc.ID, rc.PatchType)
		}
	}
	for _, f := range c.EnvelopeFields {
		if strings.TrimSpace(f.Name) == "" {
			return fmt.Errorf("envelope_fields entry missing name")
		}
		if f.Type == "enum" && c.enumClassFor(f.EnumRef) == "" {
			return fmt.Errorf("envelope field %q references unknown enum_ref %q", f.Name, f.EnumRef)
		}
		if f.Format != "" && f.Format != "canonical_sha256" {
			return fmt.Errorf("envelope field %q uses unsupported format %q", f.Name, f.Format)
		}
		if f.Format != "" && f.Type != "string" {
			return fmt.Errorf("envelope field %q format requires string type", f.Name)
		}
	}
	return nil
}

func recPatchEnumValues(ids []string) string {
	// reserved for potential future use; kept minimal.
	return strings.Join(ids, ",")
}

func emitRecPatchEnum(b *strings.Builder, className, doc string, ids []string, descByID map[string]string) {
	b.WriteString(fmt.Sprintf("/// %s\n", doc))
	b.WriteString(fmt.Sprintf("enum %s {\n", className))
	for index, id := range ids {
		if d := strings.TrimSpace(descByID[id]); d != "" {
			b.WriteString(fmt.Sprintf("  /// %s\n", d))
		}
		terminator := ","
		if index == len(ids)-1 {
			terminator = ";"
		}
		b.WriteString(fmt.Sprintf("  %s('%s')%s\n", toDartValueName(id), id, terminator))
	}
	b.WriteString("\n")
	b.WriteString(fmt.Sprintf("  const %s(this.wire);\n\n", className))
	b.WriteString("  final String wire;\n\n")
	b.WriteString(fmt.Sprintf("  static %s fromWire(Object? value) {\n", className))
	b.WriteString("    switch (value) {\n")
	for _, id := range ids {
		b.WriteString(fmt.Sprintf("      case '%s':\n", id))
		b.WriteString(fmt.Sprintf("        return %s.%s;\n", className, toDartValueName(id)))
	}
	b.WriteString("      default:\n")
	b.WriteString(fmt.Sprintf("        throw FormatException('Invalid %s wire value: $value');\n", className))
	b.WriteString("    }\n")
	b.WriteString("  }\n")
	b.WriteString("}\n\n")
}

func recPatchFieldFromWireExpr(f recPatchEnvelopeField, enumClass string) string {
	p := fmt.Sprintf("payload['%s']", f.Name)
	switch f.Type {
	case "enum":
		if f.Nullable {
			return fmt.Sprintf("%s == null ? null : %s.fromWire(%s)", p, enumClass, p)
		}
		return fmt.Sprintf("%s.fromWire(%s)", enumClass, p)
	case "int":
		if f.Nullable {
			return fmt.Sprintf("_optionalValue<int>(%s, '%s')", p, f.Name)
		}
		return fmt.Sprintf("_optionalValue<int>(%s, '%s') ?? %s", p, f.Name, recPatchDefaultLiteral(f, "0"))
	case "bool":
		if f.Nullable {
			return fmt.Sprintf("_optionalValue<bool>(%s, '%s')", p, f.Name)
		}
		return fmt.Sprintf("_optionalValue<bool>(%s, '%s') ?? %s", p, f.Name, recPatchDefaultLiteral(f, "false"))
	case "[]string":
		return fmt.Sprintf("_stringList(%s, '%s')", p, f.Name)
	default: // string
		if f.Format == "canonical_sha256" {
			if f.Nullable {
				return fmt.Sprintf("_optionalCanonicalSha256(%s, '%s')", p, f.Name)
			}
			return fmt.Sprintf("_requiredCanonicalSha256(%s, '%s')", p, f.Name)
		}
		if f.Nullable {
			return fmt.Sprintf("_optionalValue<String>(%s, '%s')", p, f.Name)
		}
		if f.Required {
			return fmt.Sprintf("_requiredNonEmptyString(%s, '%s')", p, f.Name)
		}
		return fmt.Sprintf("_optionalValue<String>(%s, '%s') ?? %s", p, f.Name, recPatchDefaultLiteral(f, "''"))
	}
}

func recPatchDefaultLiteral(f recPatchEnvelopeField, fallback string) string {
	if strings.TrimSpace(f.Default) != "" {
		return strings.TrimSpace(f.Default)
	}
	return fallback
}

func renderRecommendationFeedPatchesDart(sourcePath string, c *recPatchContract) string {
	hasCanonicalSHA256 := false
	hasRequiredCanonicalSHA256 := false
	for _, f := range c.EnvelopeFields {
		if f.Format == "canonical_sha256" {
			hasCanonicalSHA256 = true
			hasRequiredCanonicalSHA256 = hasRequiredCanonicalSHA256 || !f.Nullable
		}
	}

	var b strings.Builder
	b.WriteString("// Code generated by tools/codegen_app_metadata from content/content/post/projections/recommendation_realtime_patch.yaml. DO NOT EDIT.\n")
	b.WriteString("// Source: ")
	b.WriteString(filepath.ToSlash(sourcePath))
	b.WriteString("\n// ignore_for_file: prefer_const_constructors\n\n")
	if hasCanonicalSHA256 {
		b.WriteString("import '../../canonical_sha256_digest.dart';\n\n")
	}
	b.WriteString("T? _optionalValue<T>(Object? value, String fieldName) {\n")
	b.WriteString("  if (value == null) return null;\n")
	b.WriteString("  if (value is! T) {\n")
	b.WriteString("    throw FormatException('$fieldName has an invalid type');\n")
	b.WriteString("  }\n")
	b.WriteString("  return value as T;\n")
	b.WriteString("}\n\n")
	b.WriteString("String _requiredNonEmptyString(Object? value, String fieldName) {\n")
	b.WriteString("  final text = _optionalValue<String>(value, fieldName);\n")
	b.WriteString("  if (text == null || text.isEmpty) {\n")
	b.WriteString("    throw FormatException('$fieldName must be a non-empty string');\n")
	b.WriteString("  }\n")
	b.WriteString("  return text;\n")
	b.WriteString("}\n\n")
	b.WriteString("List<String> _stringList(Object? value, String fieldName) {\n")
	b.WriteString("  if (value == null) return const <String>[];\n")
	b.WriteString("  if (value is! List<Object?> || value.any((item) => item is! String)) {\n")
	b.WriteString("    throw FormatException('$fieldName must be a string list');\n")
	b.WriteString("  }\n")
	b.WriteString("  return List<String>.unmodifiable(value.cast<String>());\n")
	b.WriteString("}\n\n")

	if hasCanonicalSHA256 {
		b.WriteString("String? _optionalCanonicalSha256(Object? value, String fieldName) {\n")
		b.WriteString("  if (value == null) return null;\n")
		b.WriteString("  if (value is! String || !isCanonicalSha256Digest(value)) {\n")
		b.WriteString("    throw FormatException('$fieldName must be a canonical SHA-256 digest');\n")
		b.WriteString("  }\n")
		b.WriteString("  return value;\n")
		b.WriteString("}\n\n")
	}
	if hasRequiredCanonicalSHA256 {
		b.WriteString("String _requiredCanonicalSha256(Object? value, String fieldName) =>\n")
		b.WriteString("    _optionalCanonicalSha256(value, fieldName) ??\n")
		b.WriteString("    (throw FormatException('$fieldName is required'));\n\n")
	}

	b.WriteString("/// Per-user realtime channel template (`realtime_channel_template`).\n")
	b.WriteString(fmt.Sprintf("const feedRealtimePatchChannelTemplate = '%s';\n\n", c.RealtimeChannelTemplate))

	b.WriteString("/// Resolve the per-user realtime channel for [userId].\n")
	b.WriteString("String feedRealtimePatchChannelFor(String userId) =>\n")
	b.WriteString("    feedRealtimePatchChannelTemplate.replaceAll('{userId}', userId);\n\n")

	// patch type enum
	patchTypeIDs := make([]string, 0, len(c.PatchTypes))
	patchTypeDesc := map[string]string{}
	for _, pt := range c.PatchTypes {
		patchTypeIDs = append(patchTypeIDs, pt.ID)
		patchTypeDesc[pt.ID] = pt.Description
	}
	emitRecPatchEnum(&b, c.ClientCodegen.PatchTypeEnum, "推荐实时 patch 类型闭集（`patch_types`）。", patchTypeIDs, patchTypeDesc)

	// reason code enum
	reasonIDs := make([]string, 0, len(c.ReasonCodes))
	reasonDesc := map[string]string{}
	for _, rc := range c.ReasonCodes {
		reasonIDs = append(reasonIDs, rc.ID)
		reasonDesc[rc.ID] = rc.Description
	}
	emitRecPatchEnum(&b, c.ClientCodegen.ReasonCodeEnum, "推荐 patch 触发原因码闭集（`reason_codes`）。", reasonIDs, reasonDesc)

	// removal dimension enum
	dimIDs := make([]string, 0, len(c.RemovalDimensions))
	dimDesc := map[string]string{}
	for _, d := range c.RemovalDimensions {
		dimIDs = append(dimIDs, d.ID)
		dimDesc[d.ID] = d.Description
	}
	emitRecPatchEnum(&b, c.ClientCodegen.RemovalDimensionEnum, "负反馈剔除维度闭集（`removal_dimensions`）。", dimIDs, dimDesc)

	// envelope class
	class := c.ClientCodegen.EnvelopeClass
	b.WriteString("/// 强类型推荐实时 patch envelope（单一真相源：recommendation_realtime_patch.yaml）。\n")
	b.WriteString(fmt.Sprintf("class %s {\n", class))
	b.WriteString(fmt.Sprintf("  const %s({\n", class))
	for _, f := range c.EnvelopeFields {
		switch {
		case f.Required:
			b.WriteString(fmt.Sprintf("    required this.%s,\n", f.Name))
		case f.Nullable:
			b.WriteString(fmt.Sprintf("    this.%s,\n", f.Name))
		default:
			b.WriteString(fmt.Sprintf("    this.%s = %s,\n", f.Name, recPatchCtorDefault(f)))
		}
	}
	b.WriteString("  });\n\n")

	for _, f := range c.EnvelopeFields {
		dt := f.DartType
		if f.Nullable {
			b.WriteString(fmt.Sprintf("  final %s? %s;\n", dt, f.Name))
		} else {
			b.WriteString(fmt.Sprintf("  final %s %s;\n", dt, f.Name))
		}
	}

	b.WriteString(fmt.Sprintf("\n  factory %s.fromWire(Map<String, dynamic> payload) {\n", class))
	b.WriteString(fmt.Sprintf("    return %s(\n", class))
	for _, f := range c.EnvelopeFields {
		enumClass := ""
		if f.Type == "enum" {
			enumClass = c.enumClassFor(f.EnumRef)
		}
		b.WriteString(fmt.Sprintf("      %s: %s,\n", f.Name, recPatchFieldFromWireExpr(f, enumClass)))
	}
	b.WriteString("    );\n  }\n\n")
	b.WriteString("  Map<String, Object?> toWire() => <String, Object?>{\n")
	for _, f := range c.EnvelopeFields {
		expression := recPatchFieldToWireExpr(f)
		if f.Nullable {
			b.WriteString(fmt.Sprintf("    if (%s != null) '%s': %s,\n", f.Name, f.Name, expression))
		} else {
			b.WriteString(fmt.Sprintf("    '%s': %s,\n", f.Name, expression))
		}
	}
	b.WriteString("  };\n}\n\n")

	// wire keys manifest (single source for contract tests)
	b.WriteString("/// envelope wire 字段顺序（codegen 与 recommendation_realtime_patch.yaml 同步）。\n")
	b.WriteString("const feedRealtimePatchWireKeys = <String>[\n")
	for _, f := range c.EnvelopeFields {
		b.WriteString(fmt.Sprintf("  '%s',\n", f.Name))
	}
	b.WriteString("];\n\n")

	b.WriteString("/// 解析一条推荐实时 patch 消息体。\n")
	b.WriteString(fmt.Sprintf("%s parseFeedRealtimePatch(Map<String, dynamic> message) {\n", class))
	b.WriteString("  final unknownKeys = message.keys\n")
	b.WriteString("      .where((key) => !feedRealtimePatchWireKeys.contains(key))\n")
	b.WriteString("      .toList(growable: false);\n")
	b.WriteString("  if (unknownKeys.isNotEmpty) {\n")
	b.WriteString("    throw FormatException(\n")
	b.WriteString("      'FeedRealtimePatch contains unknown fields: ${unknownKeys.join(',')}',\n")
	b.WriteString("    );\n")
	b.WriteString("  }\n")
	b.WriteString(fmt.Sprintf("  return %s.fromWire(message);\n", class))
	b.WriteString("}\n")

	return b.String()
}

func recPatchFieldToWireExpr(field recPatchEnvelopeField) string {
	access := field.Name
	if field.Nullable {
		access += "!"
	}
	switch field.Type {
	case "enum":
		return access + ".wire"
	case "[]string":
		return access + ".toList(growable: false)"
	default:
		return access
	}
}

func recPatchCtorDefault(f recPatchEnvelopeField) string {
	def := strings.TrimSpace(f.Default)
	if f.Type == "[]string" {
		if def == "" || def == "<String>[]" {
			return "const <String>[]"
		}
		return "const " + def
	}
	if def == "" {
		switch f.Type {
		case "int":
			return "0"
		case "bool":
			return "false"
		default:
			return "''"
		}
	}
	return def
}

var _ = recPatchEnumValues
