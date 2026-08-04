package validate

import (
	"strings"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
)

func validateFieldTypes(contractGraph *graph.ContractGraph) []Issue {
	primitives := map[string]struct{}{}
	for _, primitive := range []string{
		"string", "bool", "boolean", "int", "int32", "int64", "integer", "long",
		"float", "float32", "float64", "double", "timestamp", "datetime",
		"date", "time", "ObjectId", "object", "array", "json", "jsonb",
		"embedded_list", "tag_ref", "bytes", "decimal", "duration", "url",
		"uuid",
	} {
		primitives[primitive] = struct{}{}
	}
	issues := validateTypeOwnership(contractGraph)
	aggregateRootNames := make(map[string]string, len(contractGraph.Objects))
	for _, object := range contractGraph.Objects {
		if object.Kind == ast.ObjectKindAggregateRoot {
			aggregateRootNames[object.ID] = object.Name
		}
	}
	for _, field := range contractGraph.Governance.Fields {
		if rootName, ok := aggregateRootNames[field.ObjectID]; ok &&
			field.Entity == rootName && isBareObjectType(field.Type) {
			issues = append(issues, issue(
				"CONTRACT.FIELD.AGGREGATE_ROOT_BARE_OBJECT",
				field.SourcePath,
				"aggregate root field %s.%s type %q must reference a named value type",
				field.Entity,
				field.Name,
				field.Type,
			))
		}
		issues = append(issues, validateCanonicalCollectionType(field)...)
		baseTypes := baseFieldTypes(field.Type)
		if isCanonicalEnumFieldType(field.Type) {
			if field.EnumRef == "" && len(field.InlineValues) == 0 {
				issues = append(issues, issue(
					"CONTRACT.FIELD.ENUM_WITHOUT_OWNER",
					field.SourcePath,
					"field %s.%s type %s requires enum_ref or inline values",
					field.Entity,
					field.Name,
					field.Type,
				))
			}
			baseTypes = nil
		}
		for _, base := range baseTypes {
			if !knownFieldType(contractGraph, primitives, field, base) {
				issues = append(issues, issue(
					"CONTRACT.FIELD.UNKNOWN_TYPE",
					field.SourcePath,
					"field %s.%s references unknown type %q",
					field.Entity,
					field.Name,
					base,
				))
			}
		}
		issues = append(issues, validateSemanticField(field, baseTypes)...)
	}
	return issues
}

func isCanonicalEnumFieldType(raw string) bool {
	raw = strings.TrimSpace(strings.TrimSuffix(raw, "?"))
	return raw == "enum" || raw == "[]enum"
}

func isBareObjectType(raw string) bool {
	raw = strings.TrimSpace(strings.TrimSuffix(raw, "?"))
	return raw == "object" || raw == "[]object"
}

func validateCanonicalCollectionType(field ast.FieldDefinition) []Issue {
	raw := strings.TrimSpace(strings.TrimSuffix(field.Type, "?"))
	switch raw {
	case "array", "list", "embedded_list":
		return []Issue{issue(
			"CONTRACT.FIELD.UNTYPED_COLLECTION",
			field.SourcePath,
			"field %s.%s collection type %q must declare an explicit []T element type",
			field.Entity,
			field.Name,
			field.Type,
		)}
	}
	if strings.HasSuffix(raw, "[]") ||
		strings.HasPrefix(raw, "List<") || strings.HasPrefix(raw, "list<") ||
		strings.HasPrefix(raw, "Set<") || strings.HasPrefix(raw, "set<") {
		return []Issue{issue(
			"CONTRACT.FIELD.NON_CANONICAL_COLLECTION",
			field.SourcePath,
			"field %s.%s collection type %q must use canonical []T syntax",
			field.Entity,
			field.Name,
			field.Type,
		)}
	}
	if strings.HasPrefix(raw, "[]") && strings.TrimSpace(strings.TrimPrefix(raw, "[]")) == "" {
		return []Issue{issue(
			"CONTRACT.FIELD.UNTYPED_COLLECTION",
			field.SourcePath,
			"field %s.%s collection type %q has no element type",
			field.Entity,
			field.Name,
			field.Type,
		)}
	}
	return nil
}

func validateTypeOwnership(contractGraph *graph.ContractGraph) []Issue {
	type owner struct {
		objectID   string
		sourcePath string
	}
	objectByDomainAndName := map[string]ast.Object{}
	for _, object := range contractGraph.Objects {
		objectByDomainAndName[object.Domain+"\x00"+object.Name] = object
	}
	ownersByDomainAndName := map[string]owner{}
	var issues []Issue
	for _, definition := range contractGraph.Governance.Types {
		if definition.OwnerLevel != ast.EnumOwnerObject {
			continue
		}
		key := definition.Domain + "\x00" + definition.Name
		if canonical, exists := objectByDomainAndName[key]; exists &&
			canonical.ID != definition.ObjectID {
			issues = append(issues, issue(
				"CONTRACT.TYPE.OBJECT_NAME_SHADOWED",
				definition.SourcePath,
				"object-local type %q in %s shadows canonical object %s",
				definition.Name,
				definition.ObjectID,
				canonical.ID,
			))
		}
		if first, exists := ownersByDomainAndName[key]; exists {
			if first.objectID != definition.ObjectID {
				issues = append(issues, issue(
					"CONTRACT.TYPE.DUPLICATE_OBJECT_DEFINITION",
					definition.SourcePath,
					"object-local type %q in domain %q is owned by both %s (%s) and %s (%s)",
					definition.Name,
					definition.Domain,
					first.objectID,
					first.sourcePath,
					definition.ObjectID,
					definition.SourcePath,
				))
			}
			continue
		}
		ownersByDomainAndName[key] = owner{
			objectID:   definition.ObjectID,
			sourcePath: definition.SourcePath,
		}
	}
	return issues
}

func knownFieldType(
	contractGraph *graph.ContractGraph,
	primitives map[string]struct{},
	field ast.FieldDefinition,
	name string,
) bool {
	if _, exists := primitives[name]; exists {
		return true
	}
	for _, level := range []ast.EnumOwnerLevel{
		ast.EnumOwnerObject,
		ast.EnumOwnerService,
		ast.EnumOwnerGlobal,
	} {
		for _, definition := range contractGraph.Governance.Types {
			if definition.Name != name || definition.OwnerLevel != level {
				continue
			}
			switch level {
			case ast.EnumOwnerObject:
				if definition.ObjectID == field.ObjectID {
					return true
				}
			case ast.EnumOwnerService:
				if definition.Domain == field.Domain {
					return true
				}
			case ast.EnumOwnerGlobal:
				return true
			}
		}
	}
	if resolveEnumDefinition(
		contractGraph.Governance.Enums,
		ast.EnumReference{Name: name, Domain: field.Domain, ObjectID: field.ObjectID},
	) >= 0 {
		return true
	}
	for _, object := range contractGraph.Objects {
		if object.Domain == field.Domain && object.Name == name {
			return true
		}
	}
	for _, projection := range contractGraph.Projections {
		if projection.Domain != field.Domain {
			continue
		}
		if projection.ReadModel == name {
			return true
		}
	}
	return false
}

func baseFieldTypes(raw string) []string {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return []string{""}
	}
	raw = strings.TrimSuffix(raw, "?")
	if strings.HasPrefix(raw, "[]") {
		return baseFieldTypes(strings.TrimPrefix(raw, "[]"))
	}
	if strings.HasSuffix(raw, "[]") {
		return baseFieldTypes(strings.TrimSuffix(raw, "[]"))
	}
	for _, prefix := range []string{"List<", "list<", "Set<", "set<"} {
		if strings.HasPrefix(raw, prefix) && strings.HasSuffix(raw, ">") {
			return baseFieldTypes(raw[len(prefix) : len(raw)-1])
		}
	}
	for _, prefix := range []string{"Map<", "map<"} {
		if strings.HasPrefix(raw, prefix) && strings.HasSuffix(raw, ">") {
			inner := raw[len(prefix) : len(raw)-1]
			parts := strings.SplitN(inner, ",", 2)
			if len(parts) == 2 {
				return append(baseFieldTypes(parts[0]), baseFieldTypes(parts[1])...)
			}
		}
	}
	return []string{strings.TrimSpace(raw)}
}

func validateSemanticField(
	field ast.FieldDefinition,
	baseTypes []string,
) []Issue {
	baseSet := map[string]struct{}{}
	for _, value := range baseTypes {
		baseSet[value] = struct{}{}
	}
	hasAny := func(values ...string) bool {
		for _, value := range values {
			if _, exists := baseSet[value]; exists {
				return true
			}
		}
		return false
	}
	var issues []Issue
	if strings.HasSuffix(field.Name, "At") &&
		!hasAny("timestamp", "datetime") {
		issues = append(issues, issue(
			"CONTRACT.FIELD.INVALID_INSTANT_TYPE",
			field.SourcePath,
			"field %s.%s ends with At and must use timestamp or datetime, got %q",
			field.Entity,
			field.Name,
			field.Type,
		))
	}
	if field.SemanticType == "" {
		return issues
	}
	valid := false
	switch field.SemanticType {
	case "instant", "watermark_time":
		valid = hasAny("timestamp", "datetime")
	case "aggregate_version", "sequence", "watermark_sequence":
		valid = hasAny("int", "int32", "int64", "long")
	case "release_version", "cursor":
		valid = hasAny("string")
	case "identifier":
		valid = hasAny("string", "ObjectId", "uuid")
	default:
		return append(issues, issue(
			"CONTRACT.FIELD.UNKNOWN_SEMANTIC_TYPE",
			field.SourcePath,
			"field %s.%s declares unknown semantic_type %q",
			field.Entity,
			field.Name,
			field.SemanticType,
		))
	}
	if !valid {
		issues = append(issues, issue(
			"CONTRACT.FIELD.SEMANTIC_TYPE_MISMATCH",
			field.SourcePath,
			"field %s.%s semantic_type %q is incompatible with %q",
			field.Entity,
			field.Name,
			field.SemanticType,
			field.Type,
		))
	}
	return issues
}
