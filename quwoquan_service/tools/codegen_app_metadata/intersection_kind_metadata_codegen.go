package main

import (
	"fmt"
	"path/filepath"
	"sort"
	"strings"

	"quwoquan_service/tools/recintersectionmeta"
)

// 交集 kind 注册表 → package vocabulary / App application policy /
// presentation metadata。
// registry 解析层统一在 tools/recintersectionmeta（服务端 Go codegen 同源复用），
// 本文件只补端侧分层输出需要的严格校验与 Dart 渲染。

const intersectionKindRegistryMetadataPath = "recommendation/recommendation/recommendation_model_release/intersection_kind_registry.yaml"

const intersectionContractVocabularyImport = "package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart"

func dartStringListLiteral(values []string) string {
	if len(values) == 0 {
		return "<String>[]"
	}
	parts := make([]string, 0, len(values))
	for _, v := range values {
		parts = append(parts, dartStringLiteral(v))
	}
	return "<String>[" + strings.Join(parts, ", ") + "]"
}

func readIntersectionGeneratedMetadata(
	metadataDir string,
) (string, *recintersectionmeta.Registry, error) {
	contractPath := filepath.Join(
		metadataDir,
		filepath.FromSlash(intersectionKindRegistryMetadataPath),
	)
	raw, err := readMetadataDocument(contractPath)
	if err != nil {
		return "", nil, fmt.Errorf("intersection kind registry: %w", err)
	}
	registry, err := recintersectionmeta.Parse(raw)
	if err != nil {
		return "", nil, fmt.Errorf("read intersection kind registry: %w", err)
	}
	if err := recintersectionmeta.Validate(registry); err != nil {
		return "", nil, fmt.Errorf("intersection kind registry: %w", err)
	}
	canonicalEnums, err := loadCanonicalSharedEnumValues()
	if err != nil {
		return "", nil, fmt.Errorf("intersection package vocabulary: %w", err)
	}
	canonicalDimensions := canonicalEnums["IntersectionDimension"]
	if err := validateIntersectionGeneratedMetadata(
		registry,
		canonicalDimensions,
	); err != nil {
		return "", nil, fmt.Errorf("intersection generated metadata: %w", err)
	}
	return metadataSourceLabel(contractPath), registry, nil
}

// writeIntersectionFeedbackContracts owns only the cross-object feedback wire
// vocabulary. It deliberately has a separate lifecycle from the legacy
// renderer so retiring the latter cannot silently retire feedback reporting.
func writeIntersectionFeedbackContracts(
	appDir,
	sourcePath string,
	registry *recintersectionmeta.Registry,
) {
	writeFile(filepath.Join(
		appDir,
		"packages",
		"quwoquan_cloud_contracts",
		"lib",
		"src",
		"generated",
		"recommendation",
		"intersection_feedback_contracts.g.dart",
	), renderIntersectionFeedbackContractsDart(sourcePath, registry))
}

func writeCanonicalIntersectionMetadata(
	appDir,
	sourcePath string,
	registry *recintersectionmeta.Registry,
) {
	writeFile(filepath.Join(
		appDir,
		"packages",
		"quwoquan_cloud_contracts",
		"lib",
		"src",
		"generated",
		"recommendation",
		"intersection_contract_vocabulary.g.dart",
	), renderIntersectionContractVocabularyDart(sourcePath, registry))
	writeFile(
		recommendationFeatureProfileApplicationOutputPath(
			appDir,
			"intersection_client_policy.g.dart",
		),
		renderIntersectionClientPolicyDart(sourcePath, registry),
	)
	writeFile(
		recommendationFeatureProfilePresentationOutputPath(
			appDir,
			"intersection_display_metadata.g.dart",
		),
		renderIntersectionDisplayMetadataDart(sourcePath, registry),
	)
}

func renderIntersectionFeedbackContractsDart(
	sourcePath string,
	r *recintersectionmeta.Registry,
) string {
	var b strings.Builder
	b.WriteString("// Code generated from the canonical intersection kind registry. DO NOT EDIT.\n")
	b.WriteString("// Source: ")
	b.WriteString(filepath.ToSlash(sourcePath))
	b.WriteString("\n\n")
	b.WriteString("/// 负反馈闭集；端上报与云侧降权/冷却同源。\n")
	b.WriteString(fmt.Sprintf(
		"const List<String> intersectionFeedbackKinds = %s;\n\n",
		dartStringListLiteral(r.FeedbackKinds),
	))
	for _, kind := range r.FeedbackKinds {
		trimmed := strings.TrimSpace(kind)
		name := "intersectionFeedbackKind" + intersectionDartExportedSuffix(trimmed)
		b.WriteString(fmt.Sprintf("const String %s = %q;\n", name, trimmed))
	}
	return b.String()
}

var intersectionDartReservedWords = map[string]struct{}{
	"abstract": {}, "as": {}, "assert": {}, "async": {}, "await": {},
	"base": {}, "break": {}, "case": {}, "catch": {}, "class": {},
	"const": {}, "continue": {}, "covariant": {}, "default": {},
	"deferred": {}, "do": {}, "dynamic": {}, "else": {}, "enum": {},
	"export": {}, "extends": {}, "extension": {}, "external": {},
	"factory": {}, "false": {}, "final": {}, "finally": {}, "for": {},
	"get": {}, "hide": {}, "if": {}, "implements": {}, "import": {},
	"in": {}, "interface": {}, "is": {}, "late": {}, "library": {},
	"mixin": {}, "new": {}, "null": {}, "of": {}, "on": {},
	"operator": {}, "part": {}, "required": {}, "rethrow": {},
	"return": {}, "sealed": {}, "set": {}, "show": {}, "static": {},
	"super": {}, "switch": {}, "sync": {}, "this": {}, "throw": {},
	"true": {}, "try": {}, "typedef": {}, "var": {}, "void": {},
	"when": {}, "while": {}, "with": {}, "yield": {},
}

func intersectionDartEnumMemberName(value string) string {
	name := toDartFieldName(strings.TrimSpace(value))
	if _, reserved := intersectionDartReservedWords[name]; reserved {
		return name + "Value"
	}
	return name
}

func intersectionDartExportedSuffix(value string) string {
	name := intersectionDartEnumMemberName(value)
	if name == "" {
		return "Value"
	}
	return strings.ToUpper(name[:1]) + name[1:]
}

func validateIntersectionClosedSet(kind string, values []string) error {
	if len(values) == 0 {
		return fmt.Errorf("%s closed set is empty", kind)
	}
	seenValues := map[string]struct{}{}
	seenMembers := map[string]string{}
	for _, raw := range values {
		value := strings.TrimSpace(raw)
		if value == "" || value != raw {
			return fmt.Errorf("%s contains an empty or untrimmed value %q", kind, raw)
		}
		if _, duplicate := seenValues[value]; duplicate {
			return fmt.Errorf("%s contains duplicate value %q", kind, value)
		}
		seenValues[value] = struct{}{}
		member := intersectionDartEnumMemberName(value)
		if !isDartIdentifier(member) {
			return fmt.Errorf(
				"%s value %q maps to invalid Dart member %q",
				kind,
				value,
				member,
			)
		}
		if previous, collision := seenMembers[member]; collision {
			return fmt.Errorf(
				"%s values %q and %q map to Dart member %q",
				kind,
				previous,
				value,
				member,
			)
		}
		seenMembers[member] = value
	}
	return nil
}

func equalIntersectionValues(left, right []string) bool {
	if len(left) != len(right) {
		return false
	}
	for index := range left {
		if left[index] != right[index] {
			return false
		}
	}
	return true
}

func validateIntersectionGeneratedMetadata(
	r *recintersectionmeta.Registry,
	canonicalDimensions []string,
) error {
	if r == nil {
		return fmt.Errorf("registry is nil")
	}
	closedSets := []struct {
		name   string
		values []string
	}{
		{"dimensions", r.Dimensions},
		{"lifecycleStates", r.LifecycleStates},
		{"verticals", r.Verticals},
		{"moments", r.Moments},
		{"gateKeys", r.GateKeys},
		{"feedbackKinds", r.FeedbackKinds},
		{"actionDispatch", r.ActionDispatch},
	}
	for _, item := range closedSets {
		if err := validateIntersectionClosedSet(item.name, item.values); err != nil {
			return err
		}
	}
	if len(canonicalDimensions) == 0 {
		return fmt.Errorf("canonical IntersectionDimension owner is missing")
	}
	if !equalIntersectionValues(r.Dimensions, canonicalDimensions) {
		return fmt.Errorf(
			"registry dimensions %v do not match canonical IntersectionDimension %v",
			r.Dimensions,
			canonicalDimensions,
		)
	}

	actionKeys := make([]string, 0, len(r.ActionHintLegend))
	for key := range r.ActionHintLegend {
		actionKeys = append(actionKeys, key)
	}
	sort.Strings(actionKeys)
	if err := validateIntersectionClosedSet("actionKeys", actionKeys); err != nil {
		return err
	}
	for _, key := range actionKeys {
		meta := r.ActionKeyMeta[key]
		if err := validateIntersectionNoDuplicates(
			"actionKeyMeta["+key+"].requiredGates",
			meta.RequiredGates,
		); err != nil {
			return err
		}
	}

	objectKinds := make([]string, 0, len(r.ObjectKinds))
	seenObjectKinds := map[string]struct{}{}
	for _, item := range r.ObjectKinds {
		kind := strings.TrimSpace(item.Kind)
		if kind == "" || kind != item.Kind {
			return fmt.Errorf("objectKinds contains an empty or untrimmed kind %q", item.Kind)
		}
		if _, duplicate := seenObjectKinds[kind]; duplicate {
			return fmt.Errorf("objectKinds contains duplicate kind %q", kind)
		}
		seenObjectKinds[kind] = struct{}{}
		objectKinds = append(objectKinds, kind)
	}
	if err := validateIntersectionClosedSet("objectKinds", objectKinds); err != nil {
		return err
	}

	seenKinds := map[string]struct{}{}
	for _, item := range r.Kinds {
		kind := strings.TrimSpace(item.Kind)
		if kind == "" || kind != item.Kind {
			return fmt.Errorf("kinds contains an empty or untrimmed kind %q", item.Kind)
		}
		if _, duplicate := seenKinds[kind]; duplicate {
			return fmt.Errorf("kinds contains duplicate kind %q", kind)
		}
		seenKinds[kind] = struct{}{}
		iconKey := strings.TrimSpace(item.IconKey)
		if iconKey == "" {
			return fmt.Errorf("kind %q has no iconKey", kind)
		}
		if _, known := r.IconKeyLegend[iconKey]; !known {
			return fmt.Errorf("kind %q references unknown iconKey %q", kind, iconKey)
		}
		if strings.TrimSpace(r.VisualToneByIcon[iconKey]) == "" {
			return fmt.Errorf("kind %q iconKey %q has no visual tone", kind, iconKey)
		}
	}
	return nil
}

func validateCanonicalIntersectionDimensionMembers(
	members []canonicalRequestEnumMember,
) error {
	if activeMetadataSource == nil {
		return fmt.Errorf("ContractGraph is not initialized")
	}
	var registry struct {
		Dimensions []string `yaml:"dimensions"`
	}
	if err := activeMetadataSource.Decode(
		intersectionKindRegistryMetadataPath,
		&registry,
	); err != nil {
		return fmt.Errorf("decode intersection dimension owner: %w", err)
	}
	canonicalEnums, err := loadCanonicalSharedEnumValues()
	if err != nil {
		return err
	}
	canonicalDimensions := canonicalEnums["IntersectionDimension"]
	if !equalIntersectionValues(registry.Dimensions, canonicalDimensions) {
		return fmt.Errorf(
			"intersection registry dimensions %v do not match canonical IntersectionDimension %v",
			registry.Dimensions,
			canonicalDimensions,
		)
	}
	if len(members) != len(canonicalDimensions) {
		return fmt.Errorf(
			"IntersectionDimension operation enum has %d members, want %d",
			len(members),
			len(canonicalDimensions),
		)
	}
	for index, value := range canonicalDimensions {
		wantMember := intersectionDartEnumMemberName(value)
		if members[index].WireValue != value ||
			members[index].DartMember != wantMember {
			return fmt.Errorf(
				"IntersectionDimension member[%d] = %s/%s, want %s/%s",
				index,
				members[index].WireValue,
				members[index].DartMember,
				value,
				wantMember,
			)
		}
	}
	return nil
}

func validateIntersectionNoDuplicates(kind string, values []string) error {
	seen := map[string]struct{}{}
	for _, value := range values {
		value = strings.TrimSpace(value)
		if _, duplicate := seen[value]; duplicate {
			return fmt.Errorf("%s contains duplicate value %q", kind, value)
		}
		seen[value] = struct{}{}
	}
	return nil
}

func renderIntersectionWireEnum(
	b *strings.Builder,
	name string,
	values []string,
) {
	b.WriteString("enum ")
	b.WriteString(name)
	b.WriteString(" {\n")
	for index, value := range values {
		terminator := ","
		if index == len(values)-1 {
			terminator = ";"
		}
		b.WriteString(fmt.Sprintf(
			"  %s(%q)%s\n",
			intersectionDartEnumMemberName(value),
			value,
			terminator,
		))
	}
	b.WriteString("\n  const ")
	b.WriteString(name)
	b.WriteString("(this.wireName);\n\n")
	b.WriteString("  final String wireName;\n\n")
	b.WriteString("  static ")
	b.WriteString(name)
	b.WriteString(" fromWire(Object? value, String path) {\n")
	b.WriteString("    return switch (value) {\n")
	for _, value := range values {
		b.WriteString(fmt.Sprintf(
			"      %q => %s.%s,\n",
			value,
			name,
			intersectionDartEnumMemberName(value),
		))
	}
	b.WriteString("      _ => throw FormatException('$path has an invalid enum value'),\n")
	b.WriteString("    };\n")
	b.WriteString("  }\n")
	b.WriteString("}\n\n")
}

func renderIntersectionContractVocabularyDart(
	sourcePath string,
	r *recintersectionmeta.Registry,
) string {
	var b strings.Builder
	b.WriteString("// Code generated from the canonical intersection registry. DO NOT EDIT.\n")
	b.WriteString("// Source: ")
	b.WriteString(filepath.ToSlash(sourcePath))
	b.WriteString("\n\nlibrary;\n\n")
	renderIntersectionWireEnum(&b, "IntersectionDimension", r.Dimensions)
	renderIntersectionWireEnum(&b, "IntersectionLifecycleState", r.LifecycleStates)
	renderIntersectionWireEnum(&b, "IntersectionVertical", r.Verticals)
	renderIntersectionWireEnum(&b, "IntersectionMoment", r.Moments)
	renderIntersectionWireEnum(&b, "IntersectionGateKey", r.GateKeys)
	renderIntersectionWireEnum(&b, "IntersectionActionDispatch", r.ActionDispatch)
	actionKeys := make([]string, 0, len(r.ActionHintLegend))
	for key := range r.ActionHintLegend {
		actionKeys = append(actionKeys, key)
	}
	sort.Strings(actionKeys)
	renderIntersectionWireEnum(&b, "IntersectionActionKey", actionKeys)
	renderIntersectionWireEnum(
		&b,
		"IntersectionActionTier",
		[]string{"light", "heavy"},
	)
	objectKinds := make([]string, 0, len(r.ObjectKinds))
	for _, item := range r.ObjectKinds {
		objectKinds = append(objectKinds, item.Kind)
	}
	renderIntersectionWireEnum(&b, "IntersectionObjectKind", objectKinds)
	return b.String()
}

func renderIntersectionClientPolicyDart(
	sourcePath string,
	r *recintersectionmeta.Registry,
) string {
	var b strings.Builder
	b.WriteString("// Code generated from the canonical intersection registry. DO NOT EDIT.\n")
	b.WriteString("// Source: ")
	b.WriteString(filepath.ToSlash(sourcePath))
	b.WriteString("\n\n")
	b.WriteString("import '" + intersectionContractVocabularyImport + "'\n")
	b.WriteString("    show IntersectionActionDispatch, IntersectionActionKey, IntersectionActionTier, IntersectionGateKey, IntersectionObjectKind;\n\n")
	b.WriteString("final class IntersectionActionPolicy {\n")
	b.WriteString("  const IntersectionActionPolicy({\n")
	b.WriteString("    required this.key,\n")
	b.WriteString("    required this.tier,\n")
	b.WriteString("    required this.requiredGates,\n")
	b.WriteString("    required this.dispatch,\n")
	b.WriteString("  });\n\n")
	b.WriteString("  final IntersectionActionKey key;\n")
	b.WriteString("  final IntersectionActionTier tier;\n")
	b.WriteString("  final Set<IntersectionGateKey> requiredGates;\n")
	b.WriteString("  final IntersectionActionDispatch dispatch;\n\n")
	b.WriteString("  bool get isAssistant => dispatch == IntersectionActionDispatch.assistant;\n")
	b.WriteString("  bool get isGathering => dispatch == IntersectionActionDispatch.gathering;\n\n")
	b.WriteString("  static IntersectionActionPolicy of(IntersectionActionKey key) =>\n")
	b.WriteString("      intersectionActionPolicies[key]!;\n")
	b.WriteString("}\n\n")
	b.WriteString("const Map<IntersectionActionKey, IntersectionActionPolicy>\n")
	b.WriteString("    intersectionActionPolicies = <IntersectionActionKey, IntersectionActionPolicy>{\n")
	actionKeys := make([]string, 0, len(r.ActionKeyMeta))
	for key := range r.ActionKeyMeta {
		actionKeys = append(actionKeys, key)
	}
	sort.Strings(actionKeys)
	for _, key := range actionKeys {
		meta := r.ActionKeyMeta[key]
		keyMember := intersectionDartEnumMemberName(key)
		b.WriteString("  IntersectionActionKey.")
		b.WriteString(keyMember)
		b.WriteString(": IntersectionActionPolicy(\n")
		b.WriteString("    key: IntersectionActionKey.")
		b.WriteString(keyMember)
		b.WriteString(",\n")
		b.WriteString("    tier: IntersectionActionTier.")
		b.WriteString(intersectionDartEnumMemberName(meta.Tier))
		b.WriteString(",\n")
		b.WriteString("    requiredGates: <IntersectionGateKey>{")
		for index, gate := range meta.RequiredGates {
			if index > 0 {
				b.WriteString(", ")
			}
			b.WriteString("IntersectionGateKey.")
			b.WriteString(intersectionDartEnumMemberName(gate))
		}
		b.WriteString("},\n")
		b.WriteString("    dispatch: IntersectionActionDispatch.")
		b.WriteString(intersectionDartEnumMemberName(meta.Dispatch))
		b.WriteString(",\n")
		b.WriteString("  ),\n")
	}
	b.WriteString("};\n\n")
	b.WriteString("const Map<IntersectionObjectKind, String> intersectionRouteIdByObjectKind =\n")
	b.WriteString("    <IntersectionObjectKind, String>{\n")
	for _, item := range r.ObjectKinds {
		if strings.TrimSpace(item.RouteID) == "" {
			continue
		}
		b.WriteString(fmt.Sprintf(
			"  IntersectionObjectKind.%s: %q,\n",
			intersectionDartEnumMemberName(item.Kind),
			item.RouteID,
		))
	}
	b.WriteString("};\n\n")
	b.WriteString("String intersectionRouteIdForObjectKind(IntersectionObjectKind kind) =>\n")
	b.WriteString("    intersectionRouteIdByObjectKind[kind] ?? '';\n\n")
	b.WriteString("IntersectionObjectKind? intersectionObjectKindForObjectType(\n")
	b.WriteString("  String? objectType,\n")
	b.WriteString(") {\n")
	b.WriteString("  return switch (objectType?.trim()) {\n")
	bindings := append([]recintersectionmeta.ObjectTypeBinding(nil), r.ObjectTypeBindings...)
	sort.Slice(bindings, func(i, j int) bool {
		return bindings[i].ObjectType < bindings[j].ObjectType
	})
	for _, binding := range bindings {
		b.WriteString(fmt.Sprintf(
			"    %q => IntersectionObjectKind.%s,\n",
			binding.ObjectType,
			intersectionDartEnumMemberName(binding.ObjectKind),
		))
	}
	b.WriteString("    _ => null,\n")
	b.WriteString("  };\n")
	b.WriteString("}\n")
	return b.String()
}

func renderIntersectionDisplayMetadataDart(
	sourcePath string,
	r *recintersectionmeta.Registry,
) string {
	var b strings.Builder
	b.WriteString("// Code generated from the canonical intersection registry. DO NOT EDIT.\n")
	b.WriteString("// Source: ")
	b.WriteString(filepath.ToSlash(sourcePath))
	b.WriteString("\n\n")
	b.WriteString("import '" + intersectionContractVocabularyImport + "'\n")
	b.WriteString("    show IntersectionDimension, IntersectionObjectKind;\n\n")
	b.WriteString("final class IntersectionKindDisplayMetadata {\n")
	b.WriteString("  const IntersectionKindDisplayMetadata({required this.iconKey});\n\n")
	b.WriteString("  final String iconKey;\n\n")
	b.WriteString("  static IntersectionKindDisplayMetadata? of(String? kind) {\n")
	b.WriteString("    if (kind == null) return null;\n")
	b.WriteString("    return intersectionKindDisplayMetadata[kind.trim()];\n")
	b.WriteString("  }\n")
	b.WriteString("}\n\n")
	b.WriteString("const Map<String, IntersectionKindDisplayMetadata>\n")
	b.WriteString("    intersectionKindDisplayMetadata = <String, IntersectionKindDisplayMetadata>{\n")
	kinds := append([]recintersectionmeta.KindDef(nil), r.Kinds...)
	sort.Slice(kinds, func(i, j int) bool { return kinds[i].Kind < kinds[j].Kind })
	for _, item := range kinds {
		b.WriteString(fmt.Sprintf(
			"  %q: IntersectionKindDisplayMetadata(iconKey: %q),\n",
			item.Kind,
			item.IconKey,
		))
	}
	b.WriteString("};\n\n")
	b.WriteString("const Map<String, String> intersectionVisualToneByIconKey = <String, String>{\n")
	writeSortedStringMap(&b, r.VisualToneByIcon)
	b.WriteString("};\n\n")
	b.WriteString("const Map<IntersectionDimension, String>\n")
	b.WriteString("    intersectionFallbackIconKeyByDimension = <IntersectionDimension, String>{\n")
	for _, dimension := range r.Dimensions {
		b.WriteString(fmt.Sprintf(
			"  IntersectionDimension.%s: %q,\n",
			intersectionDartEnumMemberName(dimension),
			r.IconKeyByDimension[dimension],
		))
	}
	b.WriteString("};\n\n")
	b.WriteString("const Map<IntersectionObjectKind, String> intersectionAssetKindByObjectKind =\n")
	b.WriteString("    <IntersectionObjectKind, String>{\n")
	for _, item := range r.ObjectKinds {
		if strings.TrimSpace(item.AssetKind) == "" {
			continue
		}
		b.WriteString(fmt.Sprintf(
			"  IntersectionObjectKind.%s: %q,\n",
			intersectionDartEnumMemberName(item.Kind),
			item.AssetKind,
		))
	}
	b.WriteString("};\n")
	return b.String()
}

func renderIntersectionActionKeyMetadataDart(
	sourcePath string,
	r *recintersectionmeta.Registry,
) string {
	var b strings.Builder
	b.WriteString("// Code generated from the canonical intersection registry. DO NOT EDIT.\n")
	b.WriteString("// Source: ")
	b.WriteString(filepath.ToSlash(sourcePath))
	b.WriteString("\n// ignore_for_file: prefer_const_constructors\n\n")

	actionKeys := make([]string, 0, len(r.ActionHintLegend))
	for k := range r.ActionHintLegend {
		actionKeys = append(actionKeys, k)
	}
	sort.Strings(actionKeys)
	b.WriteString("/// 行动建议 actionKey 闭集（registry.actionHintLegend，端只读分发，不按 kind 猜测）。\n")
	b.WriteString(fmt.Sprintf("const List<String> intersectionActionKeys = %s;\n\n", dartStringListLiteral(actionKeys)))

	b.WriteString("/// 单个 actionKey 的行动阶梯元数据（registry.actionKeyMeta，§24 M0.1/M0.3/M0.7）。\n")
	b.WriteString("/// 端据 requiredGates 判断「可执行 / 优雅降级」；tier 区分轻查看/重社交；\n")
	b.WriteString("/// dispatch 表示端交互 handler 路由类别（assistant|navigate|message|gathering），\n")
	b.WriteString("/// 端 navigator/徽标/助手分发读本字段，禁止端手写「哪些 actionKey 属助手/约伴」第二份枚举（M0.7）。\n")
	b.WriteString("class IntersectionActionKeyMeta {\n")
	b.WriteString("  const IntersectionActionKeyMeta({\n")
	b.WriteString("    required this.tier,\n")
	b.WriteString("    required this.requiredGates,\n")
	b.WriteString("    required this.dispatch,\n")
	b.WriteString("  });\n\n")
	b.WriteString("  final String tier;\n")
	b.WriteString("  final List<String> requiredGates;\n")
	b.WriteString("  final String dispatch;\n\n")
	b.WriteString("  bool get isHeavy => tier == 'heavy';\n")
	b.WriteString("  /// 助手类：点击打开小艺解释/追问/续写，而非导航到对象页。\n")
	b.WriteString("  bool get isAssistant => dispatch == 'assistant';\n")
	b.WriteString("  /// 同行/线下约伴类：唯一驱动「有人同行」徽标与约伴专属落点。\n")
	b.WriteString("  bool get isGathering => dispatch == 'gathering';\n")
	b.WriteString("  /// 重社交连接类（私信/约伴，需破冰阶梯/请求/建群），非简单对象下钻。\n")
	b.WriteString("  bool get isSocialConnect =>\n")
	b.WriteString("      dispatch == 'message' || dispatch == 'gathering';\n\n")
	b.WriteString("  /// 由 actionKey 查行动阶梯元数据；未知 key 返回 null（端据此安全降级）。\n")
	b.WriteString("  static IntersectionActionKeyMeta? of(String? actionKey) {\n")
	b.WriteString("    if (actionKey == null) return null;\n")
	b.WriteString("    return intersectionActionKeyMeta[actionKey.trim()];\n")
	b.WriteString("  }\n")
	b.WriteString("}\n\n")

	actionMetaKeys := make([]string, 0, len(r.ActionKeyMeta))
	for k := range r.ActionKeyMeta {
		actionMetaKeys = append(actionMetaKeys, k)
	}
	sort.Strings(actionMetaKeys)
	b.WriteString("/// actionKey → 行动阶梯元数据表（单一真相源 registry.actionKeyMeta 下发）。\n")
	b.WriteString("const Map<String, IntersectionActionKeyMeta> intersectionActionKeyMeta = <String, IntersectionActionKeyMeta>{\n")
	for _, key := range actionMetaKeys {
		meta := r.ActionKeyMeta[key]
		b.WriteString(fmt.Sprintf("  %s: IntersectionActionKeyMeta(\n", dartStringLiteral(key)))
		b.WriteString(fmt.Sprintf("    tier: %s,\n", dartStringLiteral(meta.Tier)))
		b.WriteString(fmt.Sprintf("    requiredGates: %s,\n", dartStringListLiteral(meta.RequiredGates)))
		b.WriteString(fmt.Sprintf("    dispatch: %s,\n", dartStringLiteral(meta.Dispatch)))
		b.WriteString("  ),\n")
	}
	b.WriteString("};\n")
	return b.String()
}

func renderIntersectionKindMetadataDart(sourcePath string, r *recintersectionmeta.Registry) string {
	var b strings.Builder
	b.WriteString("// Code generated by tools/codegen_app_metadata from recommendation/recommendation/recommendation_model_release/intersection_kind_registry.yaml. DO NOT EDIT.\n")
	b.WriteString("// Source: ")
	b.WriteString(filepath.ToSlash(sourcePath))
	b.WriteString("\n// ignore_for_file: prefer_const_constructors\n\n")

	// ── closed sets ──
	b.WriteString("/// §21 五维闭集（registry.dimensions，端 dimension 归一/校验唯一真相源）。\n")
	b.WriteString(fmt.Sprintf("const List<String> intersectionDimensionKeys = %s;\n\n", dartStringListLiteral(r.Dimensions)))

	b.WriteString("/// Lifecycle 状态闭集（registry.lifecycleStates，§21.3 五态 + §22.3 archived/expired）。\n")
	b.WriteString(fmt.Sprintf("const List<String> intersectionLifecycleStateKeys = %s;\n\n", dartStringListLiteral(r.LifecycleStates)))

	b.WriteString("/// 垂类闭集（registry.verticals，§23.4 三元组正交标注）。\n")
	b.WriteString(fmt.Sprintf("const List<String> intersectionVerticalKeys = %s;\n\n", dartStringListLiteral(r.Verticals)))

	b.WriteString("/// 意图时态闭集（registry.moments，§24 M0.2；retrospective|current|prospective，与 lifecycleState 正交）。\n")
	b.WriteString(fmt.Sprintf("const List<String> intersectionMomentKeys = %s;\n\n", dartStringListLiteral(r.Moments)))

	b.WriteString("/// 安全门闭集（registry.gateKeys，§24 M0.1；重行动 requiredGates 取值域）。\n")
	b.WriteString(fmt.Sprintf("const List<String> intersectionGateKeys = %s;\n\n", dartStringListLiteral(r.GateKeys)))

	b.WriteString("/// 行动路由类别闭集（registry.actionDispatch，§24 M0.7；assistant|navigate|message|gathering）。\n")
	b.WriteString("/// 端交互 handler 路由维度，与 tier 权限成本正交；端 navigator/徽标/助手分发读 actionKeyMeta.dispatch。\n")
	b.WriteString(fmt.Sprintf("const List<String> intersectionActionDispatchKeys = %s;\n\n", dartStringListLiteral(r.ActionDispatch)))

	b.WriteString(renderIntersectionActionKeyMetadataDart(sourcePath, r))
	b.WriteString("\n\n")

	b.WriteString("/// iconKey → 低饱和语义 tone（registry.visualToneByIconKey）。\n")
	b.WriteString("const Map<String, String> intersectionVisualToneByIconKey = <String, String>{\n")
	writeSortedStringMap(&b, r.VisualToneByIcon)
	b.WriteString("};\n\n")

	b.WriteString("/// dimension → iconKey 末级回退（registry.iconKeyByDimension，未登记 kind / affinity 降级用）。\n")
	b.WriteString("const Map<String, String> intersectionIconKeyByDimension = <String, String>{\n")
	writeSortedStringMap(&b, r.IconKeyByDimension)
	b.WriteString("};\n\n")

	// ── UnifiedObjectKind enum (objectKinds with role=object) ──
	b.WriteString("/// 统一对象类型（registry.objectKinds 中 roles 含 object 的主对象品牌角标类型）。\n")
	b.WriteString("/// wire = objectKind 契约值；routeId = 端路由逻辑名（空=不可导航）；assetKind = 对象视觉资产类型。\n")
	b.WriteString("enum UnifiedObjectKind {\n")
	objectRoleKinds := make([]recintersectionmeta.ObjectKindDef, 0, len(r.ObjectKinds))
	for _, ok := range r.ObjectKinds {
		if ok.HasRole("object") {
			objectRoleKinds = append(objectRoleKinds, ok)
		}
	}
	for i, ok := range objectRoleKinds {
		sep := ","
		if i == len(objectRoleKinds)-1 {
			sep = ";"
		}
		b.WriteString(fmt.Sprintf("  %s(%s, %s, %s)%s\n",
			toDartValueName(ok.Kind),
			dartStringLiteral(ok.Kind),
			dartStringLiteral(ok.RouteID),
			dartStringLiteral(ok.AssetKind),
			sep,
		))
	}
	b.WriteString("\n  const UnifiedObjectKind(this.wire, this.routeId, this.assetKind);\n\n")
	b.WriteString("  /// objectKind 契约值（与 registry.objectKinds.kind 对齐）。\n")
	b.WriteString("  final String wire;\n")
	b.WriteString("  /// 端路由逻辑名（与 app_routes 对齐；空串表示无独立可导航落点）。\n")
	b.WriteString("  final String routeId;\n")
	b.WriteString("  /// 对象视觉资产类型（avatar/circleAvatar/emblem/coverImage/logo）。\n")
	b.WriteString("  final String assetKind;\n\n")
	b.WriteString("  /// 由 objectKind 契约值解析品牌对象类型；未知/非品牌对象返回 null（端据此降级，不再 relationKind 旧词桥接）。\n")
	b.WriteString("  static UnifiedObjectKind? fromWire(String? value) {\n")
	b.WriteString("    switch (value) {\n")
	for _, ok := range objectRoleKinds {
		b.WriteString(fmt.Sprintf("      case %s:\n", dartStringLiteral(ok.Kind)))
		b.WriteString(fmt.Sprintf("        return UnifiedObjectKind.%s;\n", toDartValueName(ok.Kind)))
	}
	b.WriteString("      default:\n        return null;\n")
	b.WriteString("    }\n  }\n}\n\n")

	// ── objectKind → routeId (all objectKinds with a non-empty routeId, incl. count-only entity) ──
	b.WriteString("/// objectKind 契约值 → 端路由逻辑名（registry.objectKinds.routeId；含被计数对象可导航项）。\n")
	b.WriteString("/// 不可导航对象（content/tag 等）或未知值返回空串。\n")
	b.WriteString("String intersectionRouteIdForObjectKind(String objectKind) {\n")
	b.WriteString("  switch (objectKind) {\n")
	for _, ok := range r.ObjectKinds {
		if strings.TrimSpace(ok.RouteID) == "" {
			continue
		}
		b.WriteString(fmt.Sprintf("    case %s:\n", dartStringLiteral(ok.Kind)))
		b.WriteString(fmt.Sprintf("      return %s;\n", dartStringLiteral(ok.RouteID)))
	}
	b.WriteString("    default:\n      return '';\n")
	b.WriteString("  }\n}\n\n")

	// ── objectType → objectKind (registry.objectTypeBindings) ──
	b.WriteString("/// 开放 objectType 词汇 → objectKind 闭集（registry.objectTypeBindings）。\n")
	b.WriteString("/// 新增垂类主页只需在注册表登记并 codegen，端侧不得再写 objectType switch。\n")
	b.WriteString("/// 未登记 objectType 返回空串，端据此降级为不可导航，而不是默认当成人物。\n")
	b.WriteString("String intersectionObjectKindForObjectType(String objectType) {\n")
	b.WriteString("  switch (objectType.trim()) {\n")
	bindings := append([]recintersectionmeta.ObjectTypeBinding(nil), r.ObjectTypeBindings...)
	sort.Slice(bindings, func(i, j int) bool {
		return bindings[i].ObjectType < bindings[j].ObjectType
	})
	for _, binding := range bindings {
		b.WriteString(fmt.Sprintf("    case %s:\n", dartStringLiteral(binding.ObjectType)))
		b.WriteString(fmt.Sprintf("      return %s;\n", dartStringLiteral(binding.ObjectKind)))
	}
	b.WriteString("    default:\n      return '';\n")
	b.WriteString("  }\n}\n\n")

	// ── IntersectionKindMetadata class ──
	//
	// 只保留「端侧本地行为」真正需要的逐 kind 字段。objectKind / countObjectKind /
	// dimensions / actionHints / lifecycleApplicable / vertical / moment 全部逐条随
	// IntersectionReason 下发，编译进包只会形成第二真相源：注册表改一条，端不发版
	// 就与线上不一致。tone / iconKey 暂留为云侧未下发时的本地视觉兜底。
	b.WriteString("/// 单条交集 kind 的端可消费元数据（registry.kinds + visualToneByIconKey 合成）。\n")
	b.WriteString("/// 仅承载云侧未下发时的视觉兜底；objectKind/dimensions/actionHints/vertical/moment\n")
	b.WriteString("/// 等逐条事实一律直读 IntersectionReason，不在端侧留第二份 kind 表。\n")
	b.WriteString("class IntersectionKindMetadata {\n")
	b.WriteString("  const IntersectionKindMetadata({\n")
	b.WriteString("    required this.kind,\n")
	b.WriteString("    required this.iconKey,\n")
	b.WriteString("    required this.tone,\n")
	b.WriteString("  });\n\n")
	b.WriteString("  final String kind;\n")
	b.WriteString("  final String iconKey;\n")
	b.WriteString("  final String tone;\n\n")
	b.WriteString("  /// 由 kind 查元数据；未知 kind 返回 null（端据此安全降级）。\n")
	b.WriteString("  static IntersectionKindMetadata? of(String? kind) {\n")
	b.WriteString("    if (kind == null) return null;\n")
	b.WriteString("    return intersectionKindMetadata[kind];\n")
	b.WriteString("  }\n")
	b.WriteString("}\n\n")

	// ── kind metadata table ──
	b.WriteString("/// kind → 元数据表（单一真相源 intersection_kind_registry.yaml 下发）。\n")
	b.WriteString("const Map<String, IntersectionKindMetadata> intersectionKindMetadata = <String, IntersectionKindMetadata>{\n")
	for _, k := range r.Kinds {
		tone := r.VisualToneByIcon[k.IconKey]
		b.WriteString(fmt.Sprintf("  %s: IntersectionKindMetadata(\n", dartStringLiteral(k.Kind)))
		b.WriteString(fmt.Sprintf("    kind: %s,\n", dartStringLiteral(k.Kind)))
		b.WriteString(fmt.Sprintf("    iconKey: %s,\n", dartStringLiteral(k.IconKey)))
		b.WriteString(fmt.Sprintf("    tone: %s,\n", dartStringLiteral(tone)))
		b.WriteString("  ),\n")
	}
	b.WriteString("};\n")

	return b.String()
}
