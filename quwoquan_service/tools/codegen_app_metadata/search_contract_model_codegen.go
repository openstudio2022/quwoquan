package main

import (
	"fmt"
	"path/filepath"
	"reflect"
	"strings"
)

type canonicalSearchClientModel struct {
	className  string
	fileName   string
	sourcePath string
	fields     []projectionFieldDef
}

// generateCanonicalSearchClientModels derives the public Search hit ABI from
// search-service metadata. The App package must never restate this field graph
// or reconstruct content hits from an arbitrary payload map.
func generateCanonicalSearchClientModels(metadataDir, appDir string) error {
	searchIndexDir := filepath.Join(metadataDir, "search", "search", "search_index_view")
	searchFields, err := readFields(filepath.Join(searchIndexDir, "fields.yaml"))
	if err != nil {
		return fmt.Errorf("read canonical Search value types: %w", err)
	}
	hitProjectionPath, err := projectionPathByReadModel(metadataDir, "CanonicalSearchHit")
	if err != nil {
		return fmt.Errorf("resolve CanonicalSearchHit projection: %w", err)
	}
	hitProjection, err := readProjection(hitProjectionPath)
	if err != nil {
		return fmt.Errorf("read CanonicalSearchHit projection: %w", err)
	}
	payloadProjectionPath, err := projectionPathByReadModel(metadataDir, "CanonicalSearchPayload")
	if err != nil {
		return fmt.Errorf("resolve CanonicalSearchPayload projection: %w", err)
	}
	payloadProjection, err := readProjection(payloadProjectionPath)
	if err != nil {
		return fmt.Errorf("read CanonicalSearchPayload projection: %w", err)
	}

	models := make([]canonicalSearchClientModel, 0, 12)
	for _, definition := range []struct {
		className string
		fileName  string
	}{
		{className: "CanonicalSearchEvidence", fileName: "canonical_search_evidence.g.dart"},
		{className: "CanonicalSearchRankReason", fileName: "canonical_search_rank_reason.g.dart"},
		{className: "CanonicalSearchGeoPoint", fileName: "canonical_search_geo_point.g.dart"},
		{className: "CanonicalSearchIntersectionReason", fileName: "canonical_search_intersection_reason.g.dart"},
		{className: "CanonicalSearchContentHit", fileName: "canonical_search_content_hit.g.dart"},
		{className: "CanonicalSearchCitation", fileName: "canonical_search_citation.g.dart"},
		{className: "CanonicalSearchFacet", fileName: "canonical_search_facet.g.dart"},
		{className: "CanonicalSearchDegradeSignal", fileName: "canonical_search_degrade_signal.g.dart"},
		{className: "CanonicalSearchProvenance", fileName: "canonical_search_provenance.g.dart"},
	} {
		entity, exists := searchFields.Entities[definition.className]
		if !exists {
			return fmt.Errorf("%s is absent from search/search/search_index_view/fields.yaml", definition.className)
		}
		fields, convertErr := canonicalSearchEntityFields(entity.Fields)
		if convertErr != nil {
			return fmt.Errorf("derive %s client fields: %w", definition.className, convertErr)
		}
		models = append(models, canonicalSearchClientModel{
			className:  definition.className,
			fileName:   definition.fileName,
			sourcePath: "search/search/search_index_view/fields.yaml#types." + definition.className,
			fields:     fields,
		})
	}

	payloadFields, err := canonicalSearchProjectionFields(payloadProjection.Fields)
	if err != nil {
		return fmt.Errorf("derive CanonicalSearchPayload client fields: %w", err)
	}
	models = append(models, canonicalSearchClientModel{
		className:  "CanonicalSearchPayload",
		fileName:   "canonical_search_payload.g.dart",
		sourcePath: "search/search/search_index_view/projections/canonical_search_payload.yaml",
		fields:     payloadFields,
	})

	hitFields, err := canonicalSearchProjectionFields(hitProjection.Fields)
	if err != nil {
		return fmt.Errorf("derive CanonicalSearchHit client fields: %w", err)
	}
	models = append(models, canonicalSearchClientModel{
		className:  "CanonicalSearchHit",
		fileName:   "canonical_search_hit.g.dart",
		sourcePath: "search/search/search_index_view/projections/canonical_search_hit.yaml",
		fields:     hitFields,
	})
	responseProjectionPath, err := projectionPathByReadModel(metadataDir, "SearchResponseView")
	if err != nil {
		return fmt.Errorf("resolve SearchResponseView projection: %w", err)
	}
	responseProjection, err := readProjection(responseProjectionPath)
	if err != nil {
		return fmt.Errorf("read SearchResponseView projection: %w", err)
	}
	responseFields, err := canonicalSearchProjectionFields(responseProjection.Fields)
	if err != nil {
		return fmt.Errorf("derive SearchResponseView client fields: %w", err)
	}
	models = append(models, canonicalSearchClientModel{
		className:  "SearchResponseView",
		fileName:   "search_response_view.g.dart",
		sourcePath: "search/search/search_index_view/projections/search_response_view.yaml",
		fields:     responseFields,
	})
	models, err = canonicalSearchModelClosure(models, searchFields)
	if err != nil {
		return fmt.Errorf("derive canonical Search nested client model closure: %w", err)
	}

	fileByClass := make(map[string]string, len(models))
	for _, model := range models {
		fileByClass[model.className] = model.fileName
	}
	outputDir := filepath.Join(
		appDir,
		"packages",
		"quwoquan_cloud_contracts",
		"lib",
		"src",
		"generated",
		"search",
	)
	for _, model := range models {
		imports, importErr := canonicalSearchModelImports(model, fileByClass)
		if importErr != nil {
			return fmt.Errorf("derive %s client imports: %w", model.className, importErr)
		}
		content := renderStandaloneDtoDart(clientProjection{
			DartClass:   model.className,
			Strict:      true,
			DartImports: imports,
			Fields:      model.fields,
		}, model.sourcePath)
		if model.className == "CanonicalSearchHit" {
			content += canonicalSearchHitSingleTrackValidatorDart()
		}
		if model.className == "SearchResponseView" {
			content += searchResponseViewDecoderDart()
		}
		writeFile(filepath.Join(outputDir, model.fileName), content)
	}
	writeFile(
		filepath.Join(outputDir, "canonical_search_mode.g.dart"),
		canonicalSearchModeDart(),
	)
	return nil
}

func canonicalSearchHitSingleTrackValidatorDart() string {
	return `
void validateCanonicalSearchHitSingleTrack(CanonicalSearchHit hit) {
  final contentTarget = switch (hit.target) {
    'article' || 'photo' || 'video' => true,
    _ => false,
  };
  if (contentTarget && (hit.content == null || hit.payload != null)) {
    throw const FormatException(
      'content Search hit must use content and must not use payload',
    );
  }
  if (!contentTarget && hit.content != null) {
    throw const FormatException('non-content Search hit must not use content');
  }
}
`
}

func searchResponseViewDecoderDart() string {
	return `
SearchResponseView decodeSearchResponseView(Object? value) {
  if (value is! Map || value.keys.any((key) => key is! String)) {
    throw const FormatException('SearchResponseView must be an object');
  }
  final response = SearchResponseView.fromMap(
    Map<String, dynamic>.from(value),
  );
  for (final hit in response.hits) {
    validateCanonicalSearchHitSingleTrack(hit);
  }
  return response;
}
`
}

func canonicalSearchModeDart() string {
	return `// Code generated by tools/codegen_app_metadata from search/search/search_index_view/fields.yaml#enums.CanonicalSearchMode. DO NOT EDIT.

enum CanonicalSearchMode {
  suggest('suggest'),
  result('result');

  const CanonicalSearchMode(this.wireValue);
  final String wireValue;
}
`
}

func canonicalSearchEntityFields(fields []fieldDef) ([]projectionFieldDef, error) {
	result := make([]projectionFieldDef, 0, len(fields))
	for _, field := range fields {
		name := strings.TrimSpace(field.ClientDartName)
		if name == "" {
			name = strings.TrimSpace(field.Name)
		}
		wireName := strings.TrimSpace(field.ClientWireName)
		if wireName == "" {
			wireName = strings.TrimSpace(field.Name)
		}
		converted, err := canonicalSearchClientField(
			name,
			wireName,
			field.Type,
			field.EnumRef,
			hasConstraint(field.Constraints, "NULLABLE"),
		)
		if err != nil {
			return nil, fmt.Errorf("field %s: %w", field.Name, err)
		}
		result = append(result, converted)
	}
	return result, nil
}

func canonicalSearchProjectionFields(fields []projectionFieldDef) ([]projectionFieldDef, error) {
	result := make([]projectionFieldDef, 0, len(fields))
	for _, field := range fields {
		converted, err := canonicalSearchClientField(
			field.Name,
			field.Name,
			field.WireType,
			field.EnumRef,
			field.Nullable,
		)
		if err != nil {
			return nil, fmt.Errorf("field %s: %w", field.Name, err)
		}
		result = append(result, converted)
	}
	return result, nil
}

func canonicalSearchClientField(
	name, wireName, wireType, enumRef string,
	nullable bool,
) (projectionFieldDef, error) {
	field := projectionFieldDef{
		Name:     strings.TrimSpace(name),
		WireName: strings.TrimSpace(wireName),
		WireType: strings.TrimSpace(wireType),
		EnumRef:  strings.TrimSpace(enumRef),
		Nullable: nullable,
	}
	if field.Name == "" || field.WireName == "" {
		return field, fmt.Errorf("name and wire name are required")
	}
	if field.WireType == "enum" {
		if field.EnumRef == "" {
			return field, fmt.Errorf("enum_ref is required")
		}
		field.DartType = field.EnumRef
		switch field.EnumRef {
		// MediaDeliveryAccessMode 的唯一真相源是 contracts/metadata/_shared/
		// types.yaml：搜索结果卡要按 coverAssetId 换短签，就必须能声明该封面
		// 是不是私有交付，否则 research 相位的搜索封面只能按公开 URL 直连。
		case "ContentType", "ContentIdentity", "MediaDeliveryAccessMode":
			field.DartEnumDecoderWithPath = true
			field.DartEnumWireGetter = "wireName"
		default:
			return field, fmt.Errorf(
				"enum_ref %s has no canonical Search enum owner",
				field.EnumRef,
			)
		}
		return field, nil
	}
	switch field.WireType {
	case "string":
		field.DartType = "String"
	case "int", "int32", "int64":
		field.DartType = "int"
	case "float", "float64", "double", "number":
		field.DartType = "double"
	case "timestamp", "datetime":
		field.DartType = "DateTime"
	case "bool", "boolean":
		field.DartType = "bool"
	case "[]string", "string[]":
		field.DartType = "List<String>"
	default:
		if strings.HasPrefix(field.WireType, "[]") {
			element := strings.TrimSpace(strings.TrimPrefix(field.WireType, "[]"))
			if element == "" {
				return field, fmt.Errorf("invalid list type %q", field.WireType)
			}
			field.DartType = "List<" + element + ">"
			field.ListElementDartClass = element
			return field, nil
		}
		if !strings.HasPrefix(field.WireType, "CanonicalSearch") &&
			!strings.HasPrefix(field.WireType, "OwnerSearch") {
			return field, fmt.Errorf("unsupported canonical Search type %q", field.WireType)
		}
		field.DartType = field.WireType
		field.MapFromStringKeyClass = field.WireType
	}
	return field, nil
}

func canonicalSearchModelClosure(
	models []canonicalSearchClientModel,
	fields *fieldsFile,
) ([]canonicalSearchClientModel, error) {
	if fields == nil {
		return nil, fmt.Errorf("schema-owned Search fields are required")
	}
	result := append([]canonicalSearchClientModel(nil), models...)
	known := make(map[string]bool, len(result))
	for _, model := range result {
		if model.className == "" || known[model.className] {
			return nil, fmt.Errorf("duplicate or blank Search client model %q", model.className)
		}
		known[model.className] = true
	}
	visiting := map[string]bool{}
	var visit func(canonicalSearchClientModel) error
	visit = func(model canonicalSearchClientModel) error {
		if visiting[model.className] {
			return fmt.Errorf("recursive canonical Search type %s is forbidden", model.className)
		}
		visiting[model.className] = true
		defer delete(visiting, model.className)
		for _, field := range model.fields {
			for _, dependency := range []string{field.MapFromStringKeyClass, field.ListElementDartClass} {
				dependency = strings.TrimSpace(dependency)
				if dependency == "" {
					continue
				}
				if visiting[dependency] {
					return fmt.Errorf("recursive canonical Search type %s -> %s is forbidden", model.className, dependency)
				}
				if known[dependency] {
					continue
				}
				entity, sourceSection, err := canonicalSearchSchemaEntity(fields, dependency)
				if err != nil {
					return err
				}
				converted, err := canonicalSearchEntityFields(entity.Fields)
				if err != nil {
					return fmt.Errorf("derive schema-owned Search type %s: %w", dependency, err)
				}
				nested := canonicalSearchClientModel{
					className: dependency,
					fileName:  searchDartFileName(dependency),
					sourcePath: "search/search/search_index_view/fields.yaml#" +
						sourceSection + "." + dependency,
					fields: converted,
				}
				known[dependency] = true
				result = append(result, nested)
				if err := visit(nested); err != nil {
					return err
				}
			}
		}
		return nil
	}
	for index := 0; index < len(result); index++ {
		if err := visit(result[index]); err != nil {
			return nil, err
		}
	}
	return result, nil
}

func canonicalSearchSchemaEntity(fields *fieldsFile, name string) (entityDef, string, error) {
	// readFields deliberately projects types/members into Entities so aggregate
	// callers can use one lookup. Treat only byte-equivalent projected entries as
	// aliases; a genuinely conflicting same-name definition remains fail-closed.
	sections := []struct {
		name    string
		entries map[string]entityDef
	}{
		{name: "types", entries: fields.Types},
		{name: "value_objects", entries: fields.ValueObjects},
		{name: "members", entries: fields.Members},
		{name: "entities", entries: fields.Entities},
	}
	var selected entityDef
	selectedSection := ""
	for _, section := range sections {
		entries := section.entries
		if entity, exists := entries[name]; exists {
			if selectedSection == "" {
				selected = entity
				selectedSection = section.name
				continue
			}
			if !reflect.DeepEqual(selected, entity) {
				return entityDef{}, "", fmt.Errorf(
					"nested Search type %s has conflicting schema-owned definitions in %s and %s",
					name,
					selectedSection,
					section.name,
				)
			}
		}
	}
	if selectedSection == "" || len(selected.Fields) == 0 {
		return entityDef{}, "", fmt.Errorf(
			"nested Search type %s must have one non-empty schema-owned definition",
			name,
		)
	}
	return selected, selectedSection, nil
}

func searchDartFileName(className string) string {
	var result strings.Builder
	for index, character := range className {
		if character >= 'A' && character <= 'Z' {
			if index > 0 {
				result.WriteByte('_')
			}
			result.WriteRune(character + ('a' - 'A'))
			continue
		}
		result.WriteRune(character)
	}
	result.WriteString(".g.dart")
	return result.String()
}

func canonicalSearchModelImports(
	model canonicalSearchClientModel,
	fileByClass map[string]string,
) ([]string, error) {
	seen := map[string]struct{}{}
	imports := make([]string, 0)
	add := func(value string) {
		if value == "" {
			return
		}
		if _, exists := seen[value]; exists {
			return
		}
		seen[value] = struct{}{}
		imports = append(imports, value)
	}
	for _, field := range model.fields {
		if field.EnumRef != "" {
			switch field.EnumRef {
			case "ContentType", "ContentIdentity":
				add("../../content/content_operation_contracts.g.dart")
			case "MediaDeliveryAccessMode":
				// 跨服务共享 enum 直接引 shared owner，不经某个业务域中转：
				// 搜索命中与 content/entity 引用的是同一个 canonical 定义。
				add("../shared_operation_enums.g.dart")
			default:
				return nil, fmt.Errorf(
					"enum_ref %s has no canonical Search import owner",
					field.EnumRef,
				)
			}
		}
		for _, className := range []string{
			field.MapFromStringKeyClass,
			field.ListElementDartClass,
		} {
			if className == "" || className == model.className {
				continue
			}
			fileName := fileByClass[className]
			if fileName == "" {
				return nil, fmt.Errorf("nested Search type %s has no generated model", className)
			}
			add(fileName)
		}
	}
	return imports, nil
}

func hasConstraint(constraints []string, expected string) bool {
	for _, constraint := range constraints {
		if strings.EqualFold(strings.TrimSpace(constraint), expected) {
			return true
		}
	}
	return false
}
