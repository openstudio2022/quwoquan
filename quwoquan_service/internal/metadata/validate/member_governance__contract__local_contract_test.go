package validate

import (
	"encoding/json"
	"path/filepath"
	"reflect"
	"testing"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
)

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-001
func TestMemberSchemasKeepIndependentRootsAndTypedMembersDisjoint(t *testing.T) {
	schemaRoot := repositorySchemaRoot(t)
	wantRootKinds := []string{
		"aggregate_root",
		"append_only_fact",
		"process_manager",
		"projection",
		"external_reference",
		"runtime_session",
	}
	objectSchema := readJSONDocument(t, filepath.Join(schemaRoot, "object.schema.json"))
	if got := schemaStringList(t, memberSchemaValue(t, objectSchema, "properties", "kind", "enum")); !reflect.DeepEqual(got, wantRootKinds) {
		t.Fatalf("object root kinds = %v, want %v", got, wantRootKinds)
	}
	member := memberSchemaValue(t, objectSchema, "$defs", "member").(map[string]any)
	if got := schemaStringList(t, memberSchemaValue(t, member, "properties", "kind", "enum")); !reflect.DeepEqual(got, []string{"owned_entity", "value_object"}) {
		t.Fatalf("member kinds = %v", got)
	}
	if memberSchemaValue(t, member, "properties", "append_only", "const") != true {
		t.Fatal("object member append_only must be the explicit true marker")
	}
	if required := schemaStringList(t, member["required"]); !containsSchemaString(required, "description") {
		t.Fatalf("member required fields omit description: %v", required)
	}

	contractGraphSchema := readJSONDocument(
		t,
		filepath.Join(schemaRoot, "contract_graph.schema.json"),
	)
	if got := schemaStringList(t, memberSchemaValue(
		t,
		contractGraphSchema,
		"properties",
		"objects",
		"items",
		"properties",
		"kind",
		"enum",
	)); !reflect.DeepEqual(got, wantRootKinds) {
		t.Fatalf("ContractGraph root kinds = %v, want %v", got, wantRootKinds)
	}
	if got := memberSchemaValue(
		t,
		contractGraphSchema,
		"properties",
		"objects",
		"items",
		"properties",
		"members",
		"items",
		"$ref",
	); got != "#/$defs/member" {
		t.Fatalf("ContractGraph members must use the typed member definition, got %v", got)
	}
	graphMember := memberSchemaValue(t, contractGraphSchema, "$defs", "member").(map[string]any)
	for _, field := range []string{
		"name", "kind", "cardinality", "maxCardinality", "ownership", "aggregateOwner", "description",
	} {
		if !containsSchemaString(schemaStringList(t, graphMember["required"]), field) {
			t.Fatalf("ContractGraph member required fields omit %q", field)
		}
	}

	fieldsSchema := readJSONDocument(t, filepath.Join(schemaRoot, "fields.schema.json"))
	constraints := memberSchemaValue(
		t,
		fieldsSchema,
		"$defs",
		"field",
		"properties",
		"constraints",
	).(map[string]any)
	if constraints["type"] != "array" || constraints["uniqueItems"] != true {
		t.Fatalf("member field constraints are not typed and unique: %#v", constraints)
	}
}

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-001
func TestMemberGovernanceAcceptsSingleSourceMemberShapes(t *testing.T) {
	contractGraph := memberGovernanceGraph(
		ast.ObjectKindAggregateRoot,
		[]ast.Member{
			{
				Name: "Line", Kind: ast.ObjectKindOwnedEntity,
				Identity: []string{"lineId"}, Cardinality: "many", MaxCardinality: 16,
				Ownership: "aggregate", WriteAccess: "aggregate_facade_only", AggregateOwner: "Post",
				Description: "aggregate-owned line",
			},
			{
				Name: "Summary", Kind: ast.ObjectKindValueObject,
				Cardinality: "zero_or_one", MaxCardinality: 1,
				Ownership: "aggregate", AggregateOwner: "Post", Description: "optional summary",
			},
		},
		`{"members":{"Line":{"kind":"owned_entity","fields":[{"name":"lineId","type":"string","constraints":["NOT_BLANK"]}]},"Summary":{"kind":"value_object","fields":[{"name":"title","type":"string","constraints":["NULLABLE"]}]}}}`,
	)
	if issues := Run(contractGraph, ProfileBaseline); len(issues) != 0 {
		t.Fatalf("valid member governance issues = %+v", issues)
	}
}

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-001
func TestMemberGovernanceRejectsRootAndFieldShapeDrift(t *testing.T) {
	contractGraph := memberGovernanceGraph(
		ast.ObjectKindProjection,
		[]ast.Member{{
			Name: "Line", Kind: ast.ObjectKindOwnedEntity,
			Identity: []string{"lineId"}, Cardinality: "many", MaxCardinality: 16,
			Ownership: "aggregate", WriteAccess: "aggregate_facade_only", AggregateOwner: "Post",
			Description: "aggregate-owned line",
		}},
		`{"members":{"Orphan":{"kind":"owned_entity","fields":[{"name":"id","type":"string","constraints":["NOT_NULL"]}]}}}`,
	)
	issues := Run(contractGraph, ProfileBaseline)
	for _, code := range []string{
		"CONTRACT.MEMBER.INVALID_ROOT_KIND",
		"CONTRACT.MEMBER.FIELD_SHAPE_MISSING",
		"CONTRACT.MEMBER.ORPHAN_FIELD_SHAPE",
	} {
		if !hasMemberIssue(issues, code) {
			t.Fatalf("missing %s in %+v", code, issues)
		}
	}
}

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-001
func TestMemberGovernanceRejectsMemberKindsAsIndependentRoots(t *testing.T) {
	for _, kind := range []ast.ObjectKind{
		ast.ObjectKindOwnedEntity,
		ast.ObjectKindValueObject,
	} {
		contractGraph := memberGovernanceGraph(kind, nil, `{}`)
		if issues := Run(contractGraph, ProfileBaseline); !hasMemberIssue(
			issues,
			"CONTRACT.OBJECT.INVALID_ROOT_KIND",
		) {
			t.Fatalf("independent root kind %q was accepted: %+v", kind, issues)
		}
	}
}

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-001
func TestMemberGovernanceRejectsIndependentValueObjectAndInvalidBounds(t *testing.T) {
	contractGraph := memberGovernanceGraph(
		ast.ObjectKindAggregateRoot,
		[]ast.Member{{
			Name: "Summary", Kind: ast.ObjectKindValueObject,
			Identity: []string{"id"}, Cardinality: "1:N", MaxCardinality: 0,
			Ownership: "aggregate", WriteAccess: "aggregate_facade_only", AggregateOwner: "Post",
			Description: "summary value",
		}},
		`{"types":{"Summary":{"fields":[{"name":"id","type":"string","constraints":["NOT_NULL"]}]}}}`,
	)
	contractGraph.Objects = append(contractGraph.Objects, ast.Object{
		ID: "content.summary", Domain: "content", Name: "Summary",
		Kind: ast.ObjectKindAggregateRoot, KindExplicit: true,
		SourcePath: "content/content/summary/object.yaml",
	})
	issues := Run(contractGraph, ProfileBaseline)
	for _, code := range []string{
		"CONTRACT.MEMBER.INVALID_CARDINALITY",
		"CONTRACT.MEMBER.VALUE_OBJECT_INDEPENDENT_ENTRY_FORBIDDEN",
		"CONTRACT.MEMBER.INDEPENDENT_OBJECT",
	} {
		if !hasMemberIssue(issues, code) {
			t.Fatalf("missing %s in %+v", code, issues)
		}
	}
}

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-001
func TestMemberGovernanceFailsClosedOnMissingFieldsAndDuplicateIdentity(t *testing.T) {
	contractGraph := memberGovernanceGraph(
		ast.ObjectKindAggregateRoot,
		[]ast.Member{{
			Name: "Line", Kind: ast.ObjectKindOwnedEntity,
			Identity: []string{"lineId", "lineId"}, Cardinality: "many", MaxCardinality: 1,
			Ownership: "aggregate", WriteAccess: "aggregate_facade_only", AggregateOwner: "Post",
			Description: "aggregate-owned line",
		}},
		`{}`,
	)
	contractGraph.Documents = nil
	issues := Run(contractGraph, ProfileBaseline)
	for _, code := range []string{
		"CONTRACT.MEMBER.FIELDS_DOCUMENT_MISSING",
		"CONTRACT.MEMBER.DUPLICATE_IDENTITY_FIELD",
		"CONTRACT.MEMBER.UNBOUNDED_COLLECTION",
	} {
		if !hasMemberIssue(issues, code) {
			t.Fatalf("missing %s in %+v", code, issues)
		}
	}
}

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-001
func TestMemberGovernanceDeepComparesMembersAndTypes(t *testing.T) {
	member := ast.Member{
		Name: "Line", Kind: ast.ObjectKindOwnedEntity,
		Identity: []string{"lineId"}, Cardinality: "many", MaxCardinality: 16,
		Ownership: "aggregate", WriteAccess: "aggregate_facade_only", AggregateOwner: "Post",
		Description: "aggregate-owned line",
	}
	for name, fields := range map[string]string{
		"type":        `{"members":{"Line":{"kind":"owned_entity","fields":[{"name":"lineId","type":"string","constraints":["NOT_NULL"]}]}},"types":{"Line":{"fields":[{"name":"lineId","type":"int","constraints":["NOT_NULL"]}]}}}`,
		"required":    `{"members":{"Line":{"kind":"owned_entity","fields":[{"name":"lineId","type":"string","constraints":["NOT_NULL"]}]}},"types":{"Line":{"fields":[{"name":"lineId","type":"string","constraints":["NULLABLE"]}]}}}`,
		"enum":        `{"members":{"Line":{"kind":"owned_entity","fields":[{"name":"lineId","type":"enum","enum_ref":"LineId","constraints":["NOT_NULL"]}]}},"types":{"Line":{"fields":[{"name":"lineId","type":"enum","enum_ref":"OtherId","constraints":["NOT_NULL"]}]}}}`,
		"semantic":    `{"members":{"Line":{"kind":"owned_entity","fields":[{"name":"lineId","type":"string","semantic_type":"identifier","constraints":["NOT_NULL"]}]}},"types":{"Line":{"fields":[{"name":"lineId","type":"string","constraints":["NOT_NULL"]}]}}}`,
		"constraints": `{"members":{"Line":{"kind":"owned_entity","fields":[{"name":"lineId","type":"string","constraints":["NOT_NULL","PK"]}]}},"types":{"Line":{"fields":[{"name":"lineId","type":"string","constraints":["NOT_NULL"]}]}}}`,
	} {
		t.Run(name, func(t *testing.T) {
			issues := Run(
				memberGovernanceGraph(ast.ObjectKindAggregateRoot, []ast.Member{member}, fields),
				ProfileBaseline,
			)
			if !hasMemberIssue(issues, "CONTRACT.MEMBER.FIELD_SHAPE_DRIFT") {
				t.Fatalf("shape drift %s was accepted: %+v", name, issues)
			}
		})
	}
}

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-001
func TestMemberGovernanceRejectsIncompleteMemberFieldShape(t *testing.T) {
	contractGraph := memberGovernanceGraph(
		ast.ObjectKindAggregateRoot,
		[]ast.Member{{
			Name: "Line", Kind: ast.ObjectKindOwnedEntity,
			Identity: []string{"lineId"}, Cardinality: "many", MaxCardinality: 16,
			Ownership: "aggregate", WriteAccess: "aggregate_facade_only", AggregateOwner: "Post",
			Description: "aggregate-owned line",
		}},
		`{"members":{"Line":{"kind":"owned_entity","fields":[{"name":"lineId","constraints":["NULLABLE"]},{"name":"lineId","type":"string","constraints":["NULLABLE"]}]}}}`,
	)
	issues := Run(contractGraph, ProfileBaseline)
	for _, code := range []string{
		"CONTRACT.MEMBER.FIELD_TYPE_REQUIRED",
		"CONTRACT.MEMBER.DUPLICATE_FIELD_NAME",
		"CONTRACT.MEMBER.IDENTITY_FIELD_OPTIONAL",
	} {
		if !hasMemberIssue(issues, code) {
			t.Fatalf("missing %s in %+v", code, issues)
		}
	}
}

func memberGovernanceGraph(
	kind ast.ObjectKind,
	members []ast.Member,
	fields string,
) *graph.ContractGraph {
	return &graph.ContractGraph{
		Objects: []ast.Object{{
			ID: "content.post", Domain: "content", Name: "Post", Kind: kind,
			KindExplicit: true, SourcePath: "content/content/post/object.yaml", Members: members,
		}},
		Documents: []ast.SourceDocument{{
			Path: "content/content/post/fields.yaml", Content: json.RawMessage(fields),
		}},
	}
}

func hasMemberIssue(issues []Issue, code string) bool {
	for _, candidate := range issues {
		if candidate.Code == code {
			return true
		}
	}
	return false
}

func schemaStringList(t *testing.T, value any) []string {
	t.Helper()
	raw, ok := value.([]any)
	if !ok {
		t.Fatalf("schema value is %T, want []any", value)
	}
	result := make([]string, 0, len(raw))
	for _, item := range raw {
		text, ok := item.(string)
		if !ok {
			t.Fatalf("schema list item is %T, want string", item)
		}
		result = append(result, text)
	}
	return result
}

func containsSchemaString(values []string, expected string) bool {
	for _, value := range values {
		if value == expected {
			return true
		}
	}
	return false
}

func memberSchemaValue(t *testing.T, document map[string]any, segments ...string) any {
	t.Helper()
	var current any = document
	for _, segment := range segments {
		mapping, ok := current.(map[string]any)
		if !ok {
			t.Fatalf("schema path %v is not addressable at %q", segments, segment)
		}
		next, exists := mapping[segment]
		if !exists {
			t.Fatalf("schema path %v has no %q member", segments, segment)
		}
		current = next
	}
	return current
}
