package validate

import (
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"runtime"
	"strings"
	"testing"
)

// projections/*.yaml 是 ContractGraph source 的一类，却曾经是唯一没有 JSON Schema
// 把关的一类：形态变化（例如已退役的 client_projection 段）在声明位无从表达，也
// 无从发现。这一组测试锁定投影声明位的 fail-closed 判别力，以及它与
// fields.schema.json 的同源表达位。

// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/metadata-driven-client-data-contract/spec.md
func TestRepositoryProjectionsConformToCanonicalSchema(t *testing.T) {
	t.Parallel()

	metadataDir := t.TempDir()
	linkSharedSchemas(t, metadataDir)

	paths := repositoryProjectionPaths(t)
	if len(paths) == 0 {
		t.Fatal("no repository projections/*.yaml files found")
	}
	compiled, err := compileMetadataSchemas(metadataDir)
	if err != nil {
		t.Fatalf("compile metadata schemas: %v", err)
	}
	schema, ok := compiled[projectionSchemaFilename]
	if !ok {
		t.Fatalf("%s is not registered in MetadataSchemas", projectionSchemaFilename)
	}
	for _, path := range paths {
		instance, decodeErr := decodeYAMLAsJSON(path)
		if decodeErr != nil {
			t.Errorf("decode %s: %v", path, decodeErr)
			continue
		}
		if validateErr := schema.Validate(instance); validateErr != nil {
			t.Errorf("validate %s: %v", path, validateErr)
		}
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/metadata-driven-client-data-contract/spec.md
func TestMetadataSchemasRejectInvalidProjectionDeclarations(t *testing.T) {
	t.Parallel()

	for name, document := range map[string]string{
		"unknown top-level key": `
read_model: GateProbeSlice
unknown_declaration_slot: true
fields:
- name: probeId
  type: string
`,
		"unknown field key": `
read_model: GateProbeSlice
fields:
- name: probeId
  type: string
  unknown_field_slot: true
`,
		"illegal max_utf8_bytes type": `
read_model: GateProbeSlice
fields:
- name: probeId
  type: string
  max_utf8_bytes: many
`,
		"illegal nullable type": `
read_model: GateProbeSlice
fields:
- name: probeId
  type: string
  nullable: "yes"
`,
		"illegal fields shape": `
read_model: GateProbeSlice
fields:
  probeId: string
`,
		"retired client_projection section": `
read_model: GateProbeSlice
fields:
- name: probeId
  type: string
client_projection:
  dart_class: GateProbeDto
  output_path: lib/gate_probe.dart
`,
		"missing projection identity": `
name: GateProbeSlice
source:
  object: GateProbe
fields:
- name: probeId
  type: string
`,
		"empty enum_ref": `
read_model: GateProbeSlice
fields:
- name: probeId
  type: string
  enum_ref: ""
`,
		"dangling co_present_with": `
read_model: GateProbeSlice
fields:
- name: nextCursor
  type: string
  nullable: true
  co_present_with:
  - noSuchSiblingField
`,
		"self referencing co_present_with": `
read_model: GateProbeSlice
fields:
- name: nextCursor
  type: string
  nullable: true
  co_present_with:
  - nextCursor
`,
	} {
		name, document := name, document
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			issues := projectionIssuesFor(t, document)
			if len(issues) == 0 {
				t.Fatalf("projection declaration accepted invalid document:\n%s", document)
			}
		})
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/metadata-driven-client-data-contract/spec.md
func TestMetadataSchemasAcceptCanonicalProjectionShapes(t *testing.T) {
	t.Parallel()

	for name, document := range map[string]string{
		"mapping fields with admission slots": `
read_model: GateProbeSlice
description: canonical probe
source_entities:
- GateProbe
consumers:
- app
fields:
- name: items
  type: '[]string'
  max_items: 8
- name: nextCursor
  type: string
  nullable: true
  co_present_with:
  - paginationExpiresAt
- name: paginationExpiresAt
  type: timestamp
  nullable: true
- name: policyDigest
  type: string
  format: canonical_sha256
  max_utf8_bytes: 64
`,
		"name only scalar fields": `
read_model: GateProbeOpsSlice
fields:
- id
- status
`,
		"name only mapping fields": `
read_model: GateProbeWire
fields:
- {name: schema}
- {name: eventId}
`,
	} {
		name, document := name, document
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			if issues := projectionIssuesFor(t, document); len(issues) != 0 {
				t.Fatalf("canonical projection rejected: %v", issues)
			}
		})
	}
}

// 反第二真相源：投影字段的信封准入表达位必须与 fields.yaml 字段消费同一份定义。
// 一旦有人把 format / co_present_with / max_utf8_bytes / max_items / enum_ref 复制
// 成投影专属的第二份 JSON Schema 片段，这条断言立刻失败。
//
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/metadata-driven-client-data-contract/spec.md
func TestProjectionSchemaSharesFieldExpressionSlotsWithFieldsSchema(t *testing.T) {
	t.Parallel()

	schemaRoot := repositorySchemaRoot(t)
	fieldsDocument := readJSONDocument(t, filepath.Join(schemaRoot, "fields.schema.json"))
	projectionDocument := readJSONDocument(
		t, filepath.Join(schemaRoot, projectionSchemaFilename),
	)

	fieldsID, _ := fieldsDocument["$id"].(string)
	if fieldsID == "" {
		t.Fatal("fields.schema.json must declare $id")
	}
	fieldProperties := jsonPointer(
		t, fieldsDocument, "$defs", "field", "properties",
	).(map[string]any)
	projectionProperties := jsonPointer(
		t, projectionDocument, "$defs", "projectionFieldCore", "properties",
	).(map[string]any)

	for _, slot := range []string{
		"name",
		"type",
		"enum_ref",
		"max_utf8_bytes",
		"max_items",
		"format",
		"co_present_with",
	} {
		declared, exists := projectionProperties[slot]
		if !exists {
			t.Fatalf("projection schema does not declare shared slot %q", slot)
		}
		mapping, ok := declared.(map[string]any)
		if !ok {
			t.Fatalf("projection slot %q must be a schema object, got %T", slot, declared)
		}
		want := fieldsID + "#/$defs/field/properties/" + slot
		if got := mapping["$ref"]; got != want {
			t.Fatalf(
				"projection slot %q must $ref the fields.schema.json definition %q, got %#v",
				slot, want, mapping,
			)
		}
		if len(mapping) != 1 {
			t.Fatalf(
				"projection slot %q must reuse the shared definition verbatim, got %#v",
				slot, mapping,
			)
		}
		if _, exists := fieldProperties[slot]; !exists {
			t.Fatalf("fields.schema.json no longer owns shared slot %q", slot)
		}
	}

	// 同一编译器解析出来的两个 schema 对象必须是同一个指针，光看 $ref 字符串不够。
	metadataDir := t.TempDir()
	linkSharedSchemas(t, metadataDir)
	compiled, err := compileMetadataSchemas(metadataDir)
	if err != nil {
		t.Fatalf("compile metadata schemas: %v", err)
	}
	fieldsSchema, ok := compiled["fields.schema.json"]
	if !ok {
		t.Fatal("fields.schema.json is not registered in MetadataSchemas")
	}
	projectionSchema, ok := compiled[projectionSchemaFilename]
	if !ok {
		t.Fatalf("%s is not registered in MetadataSchemas", projectionSchemaFilename)
	}
	if fieldsSchema == nil || projectionSchema == nil {
		t.Fatal("metadata schemas must compile")
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/metadata-driven-client-data-contract/spec.md
func TestProjectionDocumentsAreRoutedToTheProjectionSchema(t *testing.T) {
	t.Parallel()

	metadataDir := t.TempDir()
	linkSharedSchemas(t, metadataDir)
	objectDir := linkHostObjectPacket(t, metadataDir)
	writeFixture(
		t,
		filepath.Join(objectDir, "projections", "gate_probe_slice.yaml"),
		"read_model: GateProbeSlice\nunknown_declaration_slot: true\nfields:\n- name: probeId\n  type: string\n",
	)

	issues, err := MetadataSchemas(metadataDir)
	if err != nil {
		t.Fatalf("MetadataSchemas: %v", err)
	}
	scoped := projectionScopedIssues(issues)
	if len(scoped) == 0 {
		t.Fatal("MetadataSchemas did not validate projections/*.yaml at all")
	}
}

// linkHostObjectPacket 复用仓库里一份真实 object.yaml 作为宿主对象包，
// 避免为了测试再造第二种 object packet 形态。
func linkHostObjectPacket(t *testing.T, metadataDir string) string {
	t.Helper()
	objectDir := filepath.Join(metadataDir, "content", "content", "post")
	if err := os.MkdirAll(objectDir, 0o755); err != nil {
		t.Fatalf("create %s: %v", objectDir, err)
	}
	realObject := filepath.Join(
		serviceRootFromProjectionSchemaTest(t),
		"services", "content-service", "contracts", "content", "post", "object.yaml",
	)
	if _, err := os.Stat(realObject); err != nil {
		t.Fatalf("host object packet is missing: %v", err)
	}
	if err := os.Symlink(realObject, filepath.Join(objectDir, "object.yaml")); err != nil {
		t.Fatalf("link object.yaml: %v", err)
	}
	return objectDir
}

func projectionIssuesFor(t *testing.T, document string) []Issue {
	t.Helper()
	metadataDir := t.TempDir()
	linkSharedSchemas(t, metadataDir)
	objectDir := linkHostObjectPacket(t, metadataDir)
	writeFixture(
		t,
		filepath.Join(objectDir, "projections", "probe.yaml"),
		strings.TrimPrefix(document, "\n"),
	)
	issues, err := MetadataSchemas(metadataDir)
	if err != nil {
		t.Fatalf("MetadataSchemas: %v", err)
	}
	return projectionScopedIssues(issues)
}

func projectionScopedIssues(issues []Issue) []Issue {
	var scoped []Issue
	for _, candidate := range issues {
		if strings.Contains(candidate.SourcePath, "/projections/") {
			scoped = append(scoped, candidate)
		}
	}
	return scoped
}

func writeFixture(t *testing.T, path, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatalf("create %s: %v", filepath.Dir(path), err)
	}
	if err := os.WriteFile(path, []byte(content), 0o644); err != nil {
		t.Fatalf("write %s: %v", path, err)
	}
}

// linkSharedSchemas 让临时 metadata 树消费仓库里唯一那份 _schemas，
// 避免测试复制出第二份 schema 副本。
func linkSharedSchemas(t *testing.T, metadataDir string) {
	t.Helper()
	if err := os.Symlink(
		repositorySchemaRoot(t), filepath.Join(metadataDir, "_schemas"),
	); err != nil {
		t.Fatalf("link _schemas: %v", err)
	}
}

func repositorySchemaRoot(t *testing.T) string {
	t.Helper()
	return filepath.Join(
		serviceRootFromProjectionSchemaTest(t), "contracts", "metadata", "_schemas",
	)
}

func repositoryProjectionPaths(t *testing.T) []string {
	t.Helper()
	paths, err := filepath.Glob(filepath.Join(
		serviceRootFromProjectionSchemaTest(t),
		"services", "*", "contracts", "*", "*", "projections", "*.yaml",
	))
	if err != nil {
		t.Fatalf("glob repository projections: %v", err)
	}
	return paths
}

func readJSONDocument(t *testing.T, path string) map[string]any {
	t.Helper()
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read %s: %v", path, err)
	}
	var document map[string]any
	if err := json.Unmarshal(data, &document); err != nil {
		t.Fatalf("decode %s: %v", path, err)
	}
	return document
}

func jsonPointer(t *testing.T, document map[string]any, segments ...string) any {
	t.Helper()
	var current any = document
	for _, segment := range segments {
		mapping, ok := current.(map[string]any)
		if !ok {
			t.Fatalf("pointer %v is not addressable at %q", segments, segment)
		}
		next, exists := mapping[segment]
		if !exists {
			t.Fatalf("pointer %v has no %q member", segments, segment)
		}
		current = next
	}
	if reflect.ValueOf(current).Kind() != reflect.Map {
		t.Fatalf("pointer %v must resolve to an object", segments)
	}
	return current
}

func serviceRootFromProjectionSchemaTest(t *testing.T) string {
	t.Helper()
	_, thisFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("cannot resolve test file path")
	}
	return filepath.Clean(filepath.Join(filepath.Dir(thisFile), "..", "..", ".."))
}
