package validate

import (
	"encoding/json"
	"path"
	"reflect"
	"regexp"
	"sort"
	"strings"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
)

// validateMemberGovernance derives member ownership directly from Object and
// fields.yaml. It deliberately has no registry: object.yaml is the only
// declaration of membership and fields.yaml is the only declaration of the
// member's shape.
func validateMemberGovernance(contractGraph *graph.ContractGraph) []Issue {
	documents := make(map[string]ast.SourceDocument, len(contractGraph.Documents))
	for _, document := range contractGraph.Documents {
		documents[document.Path] = document
	}
	objects := make(map[string]ast.Object, len(contractGraph.Objects))
	for _, object := range contractGraph.Objects {
		objects[domainObjectKey(object.Domain, object.Name)] = object
	}

	owners := map[string]string{}
	issues := make([]Issue, 0)
	for _, object := range contractGraph.Objects {
		if !validIndependentObjectKind(object.Kind) {
			issues = append(issues, issue(
				"CONTRACT.OBJECT.INVALID_ROOT_KIND",
				object.SourcePath,
				"object %q kind %q is not one of the six independent root kinds",
				object.ID,
				object.Kind,
			))
		}
		if len(object.Members) == 0 {
			continue
		}
		if object.Kind != ast.ObjectKindAggregateRoot {
			issues = append(issues, issue(
				"CONTRACT.MEMBER.INVALID_ROOT_KIND",
				object.SourcePath,
				"object %q kind %q cannot declare members; only aggregate_root may own members",
				object.ID,
				object.Kind,
			))
		}
		fields, fieldsOK := memberFieldsDocument(documents, object.SourcePath, &issues)
		for _, member := range object.Members {
			memberID := domainObjectKey(object.Domain, member.Name)
			if previous, exists := owners[memberID]; exists {
				issues = append(issues, issue(
					"CONTRACT.MEMBER.DUPLICATE_ID",
					object.SourcePath,
					"member %q is owned by both %q and %q",
					memberID,
					previous,
					object.ID,
				))
			} else {
				owners[memberID] = object.ID
			}
			if standalone, exists := objects[memberID]; exists {
				issues = append(issues, issue(
					"CONTRACT.MEMBER.INDEPENDENT_OBJECT",
					object.SourcePath,
					"member %s.%s cannot also be independent object %q declared by %s",
					object.ID,
					member.Name,
					standalone.ID,
					standalone.SourcePath,
				))
			}
			issues = append(issues, validateMemberDeclaration(object, member)...)
			if fieldsOK {
				issues = append(issues, validateMemberFieldShape(object, member, fields)...)
			}
		}
		if fieldsOK {
			issues = append(issues, validateNoOrphanMemberFields(object, fields)...)
		}
	}
	return issues
}

func validateMemberDeclaration(object ast.Object, member ast.Member) []Issue {
	issues := make([]Issue, 0)
	if !memberTypeNamePattern.MatchString(strings.TrimSpace(member.Name)) {
		issues = append(issues, issue(
			"CONTRACT.MEMBER.INVALID_NAME",
			object.SourcePath,
			"member %s.%s name must be canonical PascalCase",
			object.ID,
			member.Name,
		))
	}
	if strings.TrimSpace(member.Description) == "" {
		issues = append(issues, issue(
			"CONTRACT.MEMBER.DESCRIPTION_REQUIRED",
			object.SourcePath,
			"member %s.%s must declare a non-empty description",
			object.ID,
			member.Name,
		))
	}
	if member.Kind != ast.ObjectKindOwnedEntity && member.Kind != ast.ObjectKindValueObject {
		return append(issues, issue(
			"CONTRACT.MEMBER.INVALID_KIND",
			object.SourcePath,
			"member %s.%s has kind %q; members may only be owned_entity or value_object",
			object.ID,
			member.Name,
			member.Kind,
		))
	}
	if member.AggregateOwner != object.Name || member.Ownership != "aggregate" {
		issues = append(issues, issue(
			"CONTRACT.MEMBER.INVALID_AGGREGATE_OWNER",
			object.SourcePath,
			"member %s.%s must be owned only by aggregate %q",
			object.ID,
			member.Name,
			object.Name,
		))
	}
	switch member.Cardinality {
	case "one", "zero_or_one":
		if member.MaxCardinality != 1 {
			issues = append(issues, issue(
				"CONTRACT.MEMBER.INVALID_CARDINALITY_BOUND",
				object.SourcePath,
				"member %s.%s cardinality %q requires max_cardinality 1",
				object.ID,
				member.Name,
				member.Cardinality,
			))
		}
	case "many":
		if member.MaxCardinality < 2 {
			issues = append(issues, issue(
				"CONTRACT.MEMBER.UNBOUNDED_COLLECTION",
				object.SourcePath,
				"member %s.%s cardinality many requires max_cardinality of at least 2",
				object.ID,
				member.Name,
			))
		}
	default:
		issues = append(issues, issue(
			"CONTRACT.MEMBER.INVALID_CARDINALITY",
			object.SourcePath,
			"member %s.%s must use canonical cardinality one, zero_or_one, or many; got %q",
			object.ID,
			member.Name,
			member.Cardinality,
		))
	}
	if member.Kind == ast.ObjectKindOwnedEntity {
		if len(member.Identity) == 0 {
			issues = append(issues, issue(
				"CONTRACT.MEMBER.OWNED_IDENTITY_REQUIRED",
				object.SourcePath,
				"owned member %s.%s must declare identity",
				object.ID,
				member.Name,
			))
		}
		seenIdentity := make(map[string]struct{}, len(member.Identity))
		for _, identity := range member.Identity {
			identity = strings.TrimSpace(identity)
			if !memberFieldNamePattern.MatchString(identity) {
				issues = append(issues, issue(
					"CONTRACT.MEMBER.INVALID_IDENTITY_FIELD",
					object.SourcePath,
					"owned member %s.%s identity field %q must be canonical lowerCamelCase",
					object.ID,
					member.Name,
					identity,
				))
			}
			if _, duplicate := seenIdentity[identity]; duplicate {
				issues = append(issues, issue(
					"CONTRACT.MEMBER.DUPLICATE_IDENTITY_FIELD",
					object.SourcePath,
					"owned member %s.%s repeats identity field %q",
					object.ID,
					member.Name,
					identity,
				))
			}
			seenIdentity[identity] = struct{}{}
		}
		if member.WriteAccess != "aggregate_facade_only" {
			issues = append(issues, issue(
				"CONTRACT.MEMBER.OWNED_WRITE_ACCESS_REQUIRED",
				object.SourcePath,
				"owned member %s.%s write_access must be aggregate_facade_only",
				object.ID,
				member.Name,
			))
		}
		if member.AppendOnly {
			issues = append(issues, issue(
				"CONTRACT.MEMBER.OWNED_APPEND_ONLY_FORBIDDEN",
				object.SourcePath,
				"owned member %s.%s cannot declare append_only",
				object.ID,
				member.Name,
			))
		}
	} else if len(member.Identity) != 0 || member.WriteAccess != "" {
		issues = append(issues, issue(
			"CONTRACT.MEMBER.VALUE_OBJECT_INDEPENDENT_ENTRY_FORBIDDEN",
			object.SourcePath,
			"value member %s.%s cannot declare identity or write_access",
			object.ID,
			member.Name,
		))
	}
	return issues
}

func memberFieldsDocument(
	documents map[string]ast.SourceDocument,
	objectSourcePath string,
	issues *[]Issue,
) (fieldsDocument, bool) {
	fieldsPath := path.Join(path.Dir(objectSourcePath), "fields.yaml")
	document, exists := documents[fieldsPath]
	if !exists {
		*issues = append(*issues, issue(
			"CONTRACT.MEMBER.FIELDS_DOCUMENT_MISSING",
			fieldsPath,
			"object with aggregate members requires an object-local fields.yaml",
		))
		return fieldsDocument{}, false
	}
	var fields fieldsDocument
	if err := json.Unmarshal(document.Content, &fields); err != nil {
		*issues = append(*issues, issue(
			"CONTRACT.MEMBER.INVALID_FIELDS_DOCUMENT",
			fieldsPath,
			"cannot decode member fields: %v",
			err,
		))
		return fieldsDocument{}, false
	}
	return fields, true
}

func validateMemberFieldShape(
	object ast.Object,
	member ast.Member,
	fields fieldsDocument,
) []Issue {
	issues := make([]Issue, 0)
	memberDefinition, inMembers := fields.Members[member.Name]
	typeDefinition, inTypes := fields.Types[member.Name]
	if !inMembers && !inTypes {
		return append(issues, issue(
			"CONTRACT.MEMBER.FIELD_SHAPE_MISSING",
			object.SourcePath,
			"member %s.%s must have a same-name fields.members or fields.types definition",
			object.ID,
			member.Name,
		))
	}
	if inMembers && memberDefinition.Kind != member.Kind {
		issues = append(issues, issue(
			"CONTRACT.MEMBER.FIELD_KIND_MISMATCH",
			object.SourcePath,
			"member %s.%s kind %q does not match fields.members kind %q",
			object.ID,
			member.Name,
			member.Kind,
			memberDefinition.Kind,
		))
	}
	var memberShape, typeShape []normalizedMemberField
	if inMembers {
		var shapeIssues []Issue
		memberShape, shapeIssues = normalizeMemberFields(
			object,
			member,
			"fields.members",
			memberDefinition.Fields,
		)
		issues = append(issues, shapeIssues...)
	}
	if inTypes {
		var shapeIssues []Issue
		typeShape, shapeIssues = normalizeMemberFields(
			object,
			member,
			"fields.types",
			typeDefinition.Fields,
		)
		issues = append(issues, shapeIssues...)
	}
	if inMembers && inTypes && !reflect.DeepEqual(memberShape, typeShape) {
		issues = append(issues, issue(
			"CONTRACT.MEMBER.FIELD_SHAPE_DRIFT",
			object.SourcePath,
			"member %s.%s fields.members and fields.types must match name/type/required/enum/semantic/constraints/identity and bounds",
			object.ID,
			member.Name,
		))
	}
	return issues
}

type normalizedMemberField struct {
	Name             string
	Type             string
	Required         bool
	EnumRef          string
	SemanticType     string
	Constraints      []string
	Identity         bool
	MaxUTF8Bytes     int
	MaxItems         int
	ItemMaxUTF8Bytes int
	Format           string
	CoPresentWith    []string
}

var (
	memberTypeNamePattern  = regexp.MustCompile(`^[A-Z][A-Za-z0-9]*$`)
	memberFieldNamePattern = regexp.MustCompile(`^[a-z][A-Za-z0-9]*$`)
)

func validIndependentObjectKind(kind ast.ObjectKind) bool {
	switch kind {
	case ast.ObjectKindAggregateRoot,
		ast.ObjectKindProcessManager,
		ast.ObjectKindProjection,
		ast.ObjectKindExternalReference,
		ast.ObjectKindAppendOnlyFact,
		ast.ObjectKindRuntimeSession:
		return true
	default:
		return false
	}
}

func normalizeMemberFields(
	object ast.Object,
	member ast.Member,
	source string,
	fields []fieldDocument,
) ([]normalizedMemberField, []Issue) {
	issues := make([]Issue, 0)
	if len(fields) == 0 {
		return nil, append(issues, issue(
			"CONTRACT.MEMBER.FIELD_SHAPE_EMPTY",
			object.SourcePath,
			"member %s.%s %s must declare at least one field",
			object.ID,
			member.Name,
			source,
		))
	}
	identity := make(map[string]struct{}, len(member.Identity))
	for _, name := range member.Identity {
		identity[strings.TrimSpace(name)] = struct{}{}
	}
	seenNames := make(map[string]struct{}, len(fields))
	normalized := make([]normalizedMemberField, 0, len(fields))
	for _, field := range fields {
		name := strings.TrimSpace(field.Name)
		fieldType := strings.TrimSpace(field.Type)
		if !memberFieldNamePattern.MatchString(name) {
			issues = append(issues, issue(
				"CONTRACT.MEMBER.INVALID_FIELD_NAME",
				object.SourcePath,
				"member %s.%s %s field %q must be canonical lowerCamelCase",
				object.ID,
				member.Name,
				source,
				name,
			))
		}
		if _, duplicate := seenNames[name]; duplicate {
			issues = append(issues, issue(
				"CONTRACT.MEMBER.DUPLICATE_FIELD_NAME",
				object.SourcePath,
				"member %s.%s %s repeats field %q",
				object.ID,
				member.Name,
				source,
				name,
			))
		}
		seenNames[name] = struct{}{}
		if fieldType == "" {
			issues = append(issues, issue(
				"CONTRACT.MEMBER.FIELD_TYPE_REQUIRED",
				object.SourcePath,
				"member %s.%s %s field %q requires a typed field",
				object.ID,
				member.Name,
				source,
				name,
			))
		}
		constraints, duplicateConstraint := normalizedUniqueStrings(field.Constraints)
		if duplicateConstraint {
			issues = append(issues, issue(
				"CONTRACT.MEMBER.DUPLICATE_FIELD_CONSTRAINT",
				object.SourcePath,
				"member %s.%s %s field %q repeats a constraint",
				object.ID,
				member.Name,
				source,
				name,
			))
		}
		required := hasMemberConstraint(constraints, "PK") ||
			hasMemberConstraint(constraints, "NOT_NULL") ||
			hasMemberConstraint(constraints, "NOT_BLANK")
		nullable := hasMemberConstraint(constraints, "NULLABLE")
		if required == nullable {
			issues = append(issues, issue(
				"CONTRACT.MEMBER.INVALID_FIELD_REQUIREDNESS",
				object.SourcePath,
				"member %s.%s %s field %q must declare exactly one required or NULLABLE constraint",
				object.ID,
				member.Name,
				source,
				name,
			))
		}
		_, identityField := identity[name]
		if identityField && !required {
			issues = append(issues, issue(
				"CONTRACT.MEMBER.IDENTITY_FIELD_OPTIONAL",
				object.SourcePath,
				"member %s.%s identity field %q must be required",
				object.ID,
				member.Name,
				name,
			))
		}
		enumRef := strings.TrimSpace(field.EnumRef)
		if (fieldType == "enum") != (enumRef != "") {
			issues = append(issues, issue(
				"CONTRACT.MEMBER.INVALID_FIELD_ENUM",
				object.SourcePath,
				"member %s.%s %s field %q must bind enum type and enum_ref together",
				object.ID,
				member.Name,
				source,
				name,
			))
		}
		if (field.MaxUTF8Bytes < 0 || field.MaxItems < 0 || field.ItemMaxUTF8Bytes < 0) ||
			(field.MaxItems > 0 && !strings.HasPrefix(fieldType, "[]")) ||
			(field.ItemMaxUTF8Bytes > 0 && fieldType != "[]string") {
			issues = append(issues, issue(
				"CONTRACT.MEMBER.ILLEGAL_FIELD_BOUND",
				object.SourcePath,
				"member %s.%s %s field %q has bounds incompatible with type %q",
				object.ID,
				member.Name,
				source,
				name,
				fieldType,
			))
		}
		coPresentWith, duplicateCoPresent := normalizedUniqueStrings(field.CoPresentWith)
		if duplicateCoPresent {
			issues = append(issues, issue(
				"CONTRACT.MEMBER.DUPLICATE_CO_PRESENT_FIELD",
				object.SourcePath,
				"member %s.%s %s field %q repeats co_present_with targets",
				object.ID,
				member.Name,
				source,
				name,
			))
		}
		normalized = append(normalized, normalizedMemberField{
			Name:             name,
			Type:             fieldType,
			Required:         required,
			EnumRef:          enumRef,
			SemanticType:     strings.TrimSpace(field.SemanticType),
			Constraints:      constraints,
			Identity:         identityField,
			MaxUTF8Bytes:     field.MaxUTF8Bytes,
			MaxItems:         field.MaxItems,
			ItemMaxUTF8Bytes: field.ItemMaxUTF8Bytes,
			Format:           strings.TrimSpace(field.Format),
			CoPresentWith:    coPresentWith,
		})
	}
	for identityName := range identity {
		if _, exists := seenNames[identityName]; !exists {
			issues = append(issues, issue(
				"CONTRACT.MEMBER.IDENTITY_FIELD_MISSING",
				object.SourcePath,
				"member %s.%s identity field %q is absent from %s",
				object.ID,
				member.Name,
				identityName,
				source,
			))
		}
	}
	sort.Slice(normalized, func(left, right int) bool {
		return normalized[left].Name < normalized[right].Name
	})
	return normalized, issues
}

func normalizedUniqueStrings(values []string) ([]string, bool) {
	seen := make(map[string]struct{}, len(values))
	normalized := make([]string, 0, len(values))
	duplicate := false
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, exists := seen[value]; exists {
			duplicate = true
			continue
		}
		seen[value] = struct{}{}
		normalized = append(normalized, value)
	}
	sort.Strings(normalized)
	return normalized, duplicate
}

func hasMemberConstraint(constraints []string, expected string) bool {
	index := sort.SearchStrings(constraints, expected)
	return index < len(constraints) && constraints[index] == expected
}

func validateNoOrphanMemberFields(object ast.Object, fields fieldsDocument) []Issue {
	declared := map[string]struct{}{}
	for _, member := range object.Members {
		declared[member.Name] = struct{}{}
	}
	names := make([]string, 0, len(fields.Members))
	for name := range fields.Members {
		names = append(names, name)
	}
	sort.Strings(names)
	issues := make([]Issue, 0)
	for _, name := range names {
		if _, exists := declared[name]; !exists {
			issues = append(issues, issue(
				"CONTRACT.MEMBER.ORPHAN_FIELD_SHAPE",
				object.SourcePath,
				"fields.members.%s has no object.yaml member declaration",
				name,
			))
		}
	}
	return issues
}
