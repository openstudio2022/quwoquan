package main

import (
	"fmt"
	"path/filepath"
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
		imports := canonicalSearchModelImports(model, fileByClass)
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
		if !strings.HasPrefix(field.WireType, "CanonicalSearch") {
			return field, fmt.Errorf("unsupported canonical Search type %q", field.WireType)
		}
		field.DartType = field.WireType
		field.MapFromStringKeyClass = field.WireType
	}
	return field, nil
}

func canonicalSearchModelImports(
	model canonicalSearchClientModel,
	fileByClass map[string]string,
) []string {
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
			add("../content_contract_enums.g.dart")
		}
		for _, className := range []string{
			field.MapFromStringKeyClass,
			field.ListElementDartClass,
		} {
			if className == "" || className == model.className {
				continue
			}
			add(fileByClass[className])
		}
	}
	return imports
}

func hasConstraint(constraints []string, expected string) bool {
	for _, constraint := range constraints {
		if strings.EqualFold(strings.TrimSpace(constraint), expected) {
			return true
		}
	}
	return false
}
