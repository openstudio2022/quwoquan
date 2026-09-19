package main

import (
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"strings"
	"testing"

	contractcodegen "quwoquan_service/internal/metadata/codegen"
)

// spec_ref: specs/feature-tree/discovery-content/content-type-framework/spec.md#sit-001
func enumFixture(t *testing.T) (*fieldsFile, []string) {
	t.Helper()
	root := t.TempDir()
	documents := map[string]string{
		"owner/fields.yaml": `types:
  Query:
    fields:
      - {name: envelope, type: Envelope, constraints: [NOT_NULL]}
      - {name: capabilities, type: '[]enum', enum_ref: ContentType, constraints: [NOT_NULL]}
      - {name: optionalKinds, type: '[]enum', enum_ref: ContentType, constraints: [NULLABLE]}
      - {name: count, type: int64, constraints: [NOT_NULL]}
      - {name: at, type: timestamp, constraints: [NULLABLE]}
      - {name: legacy, type: enum, values: [yes, no], constraints: [NULLABLE]}
enums:
  ContentType:
    values: [image, video, article]
`,
		"_shared/types.yaml": `types:
  Envelope:
    fields:
      - {name: nested, type: Nested, constraints: [NOT_NULL]}
  Nested:
    fields:
      - {name: contentType, type: enum, enum_ref: ContentType, constraints: [NOT_NULL]}
      - {name: recipe, type: enum, enum_ref: Recipe, constraints: [NULLABLE]}
enums:
  ContentType: [image, video, article]
  Recipe: [cover_media_card, article_excerpt_card]
  Unused: [unused]
`,
	}
	paths := []string{}
	for path, body := range documents {
		writeEnumFixtureFile(t, filepath.Join(root, path), []byte(body))
		paths = append(paths, path)
	}
	source, err := contractcodegen.NewDocumentSource(root, paths)
	if err != nil {
		t.Fatal(err)
	}
	fields, err := loadFields(source, "owner/fields.yaml")
	if err != nil {
		t.Fatal(err)
	}
	order, err := resolveTransportClosure(fields, fields.Shared, &operationsFile{APIRoutes: []routeDef{{RequestEntity: "Query"}}})
	if err != nil {
		t.Fatal(err)
	}
	return fields, order
}

func writeEnumFixtureFile(t *testing.T, path string, body []byte) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, body, 0644); err != nil {
		t.Fatal(err)
	}
}

// spec_ref: specs/feature-tree/discovery-content/content-type-framework/spec.md#sit-001
func TestEnumTransportRecursiveClosureAndDeterminism(t *testing.T) {
	fields, order := enumFixture(t)
	if !reflect.DeepEqual(order, []string{"Nested", "Envelope", "Query"}) {
		t.Fatal(order)
	}
	python := generateRequestResponsePyForNames(fields, order)
	goCode, err := renderConsumedEventGo(fields, order, "owner/events.yaml", "owner.Event")
	if err != nil {
		t.Fatal(err)
	}
	for _, want := range []string{"contentType: ContentType", "recipe: Recipe | None = None", "capabilities: list[ContentType]", "optionalKinds: list[ContentType] | None = None", "count: int", "at: datetime | None = None", "legacy: str | None = None"} {
		if !strings.Contains(python, want) {
			t.Fatalf("missing %s: %s", want, python)
		}
	}
	for _, want := range []string{"ContentType ContentType", "Recipe *Recipe", "Capabilities []ContentType", "OptionalKinds *[]ContentType", "Count int64", "At *time.Time", "Legacy *string"} {
		if !strings.Contains(strings.Join(strings.Fields(string(goCode)), " "), want) {
			t.Fatalf("missing %s: %s", want, goCode)
		}
	}
	if strings.Count(python, "class ContentType(") != 1 || strings.Count(string(goCode), "type ContentType string") != 1 || strings.Contains(python, "class Unused(") || strings.Contains(string(goCode), "type Unused ") {
		t.Fatal("enum definitions duplicated or unreachable enum emitted")
	}
	again, err := renderConsumedEventGo(fields, order, "owner/events.yaml", "owner.Event")
	if err != nil || string(again) != string(goCode) || python != generateRequestResponsePyForNames(fields, order) {
		t.Fatal("nondeterministic output", err)
	}
}

// spec_ref: specs/feature-tree/discovery-content/content-type-framework/spec.md#sit-001
func TestEnumMemberNamesAvoidNormalizationCollisions(t *testing.T) {
	for _, python := range []bool{false, true} {
		members := enumMemberNames("Kind", []string{"cover_media", "cover-media", "", "Value"}, python)
		seen := map[string]bool{}
		for _, member := range members {
			if seen[member] || member == "Kind" {
				t.Fatal("colliding enum declaration", members)
			}
			seen[member] = true
		}
	}
}

// spec_ref: specs/feature-tree/discovery-content/content-type-framework/spec.md#sit-002
func TestEnumTransportRejectsInvalidReferences(t *testing.T) {
	for _, mode := range []string{"missing", "empty", "duplicate", "type-conflict", "values-conflict", "wrong-type"} {
		t.Run(mode, func(t *testing.T) {
			f := &fieldsFile{Enums: map[string][]string{"Kind": {"image", "article"}}, Entities: map[string]entityDef{"Root": {Fields: []fieldDef{{Name: "kind", Type: "[]enum", EnumRef: "Kind"}}}}}
			switch mode {
			case "missing":
				delete(f.Enums, "Kind")
			case "empty":
				f.Enums["Kind"] = nil
			case "duplicate":
				f.Enums["Kind"] = []string{"image", "image"}
			case "type-conflict":
				f.Entities["Kind"] = entityDef{}
			case "values-conflict":
				f.Entities["Root"] = entityDef{Fields: []fieldDef{{Name: "kind", Type: "enum", EnumRef: "Kind", Values: []string{"video"}}}}
			case "wrong-type":
				f.Entities["Root"] = entityDef{Fields: []fieldDef{{Name: "kind", Type: "string", EnumRef: "Kind"}}}
			}
			if _, err := resolveTransportClosure(f, nil, &operationsFile{APIRoutes: []routeDef{{RequestEntity: "Root"}}}); err == nil {
				t.Fatal("invalid enum accepted")
			}
			if f.Order != nil {
				t.Fatal("failed closure published output order")
			}
		})
	}
	f := &fieldsFile{Enums: map[string][]string{"Kind": {"image"}}}
	if err := mergeSharedEnums(f, &fieldsFile{Enums: map[string][]string{"Kind": {"video"}}}); err == nil {
		t.Fatal("conflicting enum accepted")
	}
}

// spec_ref: specs/feature-tree/discovery-content/content-type-framework/spec.md#sit-002
func TestEnumTransportGoJSONBoundary(t *testing.T) {
	fields, order := enumFixture(t)
	raw, err := renderConsumedEventGo(fields, order, "owner/events.yaml", "owner.Event")
	if err != nil {
		t.Fatal(err)
	}
	outputs := map[string][]byte{
		"event":   raw,
		"ranked":  []byte(strings.Replace(generateRankedWindowGoTransport(fields, &operationsFile{}), "package feeddeliverypage", "package eventpayload", 1)),
		"feature": []byte(strings.Replace(generateFeatureProfileGoTransport(fields, &operationsFile{}), "package generated", "package eventpayload", 1)),
	}
	for name, raw := range outputs {
		t.Run(name, func(t *testing.T) {
			root := t.TempDir()
			writeEnumFixtureFile(t, filepath.Join(root, "go.mod"), []byte("module enumfixture\n\ngo 1.23\n"))
			writeEnumFixtureFile(t, filepath.Join(root, "payload.go"), raw)
			writeEnumFixtureFile(t, filepath.Join(root, "payload_test.go"), []byte(`package eventpayload
import ("encoding/json"; "testing")
func TestBoundary(t *testing.T) {
    valid := []byte("{\"envelope\":{\"nested\":{\"contentType\":\"image\",\"recipe\":null}},\"capabilities\":[\"video\",\"article\"],\"optionalKinds\":null,\"count\":2,\"at\":null,\"legacy\":null}")
    var query Query
    if err := json.Unmarshal(valid, &query); err != nil { t.Fatal(err) }
    if query.Envelope.Nested.ContentType != ContentType("image") { t.Fatal(query) }
    if _, err := json.Marshal(query); err != nil { t.Fatal(err) }
    for _, wire := range []string{"\"future\"", "null", "2", "true", "{}", "[]", "\"\""} {
        value := ContentType("image")
        if err := json.Unmarshal([]byte(wire), &value); err == nil { t.Fatalf("accepted %s", wire) }
        if value != ContentType("image") { t.Fatal("failed decode mutated receiver") }
    }
    for _, wire := range []string{"{\"capabilities\":[\"future\"]}", "{\"capabilities\":[null]}", "{\"envelope\":{\"nested\":{\"contentType\":\"future\"}}}"} {
        if err := json.Unmarshal([]byte(wire), &query); err == nil { t.Fatal(wire) }
    }
    query.Envelope.Nested.ContentType = ContentType("future")
    if _, err := json.Marshal(query); err == nil { t.Fatal("unknown scalar serialized") }
    query.Envelope.Nested.ContentType = ContentType("image")
    query.Capabilities = []ContentType{ContentType("future")}
    if _, err := json.Marshal(query); err == nil { t.Fatal("unknown array serialized") }
}
`))
			command := exec.Command("go", "test", "-count=1", "./...")
			command.Dir = root
			command.Env = append(os.Environ(), "GOWORK=off")
			if output, err := command.CombinedOutput(); err != nil {
				t.Fatalf("generated Go boundary: %v\n%s", err, output)
			}
		})
	}
}

// spec_ref: specs/feature-tree/discovery-content/content-type-framework/spec.md#sit-002
func TestEnumTransportPythonPydanticBoundary(t *testing.T) {
	python := os.Getenv("QWQ_TEST_PYTHON")
	if python == "" {
		python = "python3"
	}
	if output, err := exec.Command(python, "-B", "-c", "import pydantic; assert pydantic.__version__.startswith('2.')").CombinedOutput(); err != nil {
		t.Skipf("Pydantic v2 required; set QWQ_TEST_PYTHON: %v %s", err, output)
	}
	fields, order := enumFixture(t)
	for _, strict := range []bool{false, true} {
		root := t.TempDir()
		writeEnumFixtureFile(t, filepath.Join(root, "contracts.py"), []byte(generateRequestResponsePyForNames(fields, order, strict)))
		script := `import json
from contracts import Query, ContentType
from pydantic import ValidationError
payload = dict(envelope=dict(nested=dict(contentType="image", recipe=None)), capabilities=["article", "video"], optionalKinds=None, count=2, at=None, legacy=None)
for validate in (Query.model_validate, lambda v: Query.model_validate_json(json.dumps(v))):
    query = validate(payload)
    assert isinstance(query.envelope.nested.contentType, ContentType)
    assert all(isinstance(value, ContentType) for value in query.capabilities)
    assert json.loads(query.model_dump_json()) == payload
    for bad in ("future", "", 2, True, {}, [], None):
        for key in ("contentType", "capabilities", "optionalKinds"):
            wire = json.loads(json.dumps(payload))
            if key == "contentType": wire["envelope"]["nested"][key] = bad
            else: wire[key] = [bad]
            try: validate(wire)
            except ValidationError: pass
            else: raise AssertionError((key, bad))
assert Query.model_json_schema()["$defs"]["ContentType"]["enum"] == ["image", "video", "article"]
from pydantic_core import PydanticSerializationError
for field in ("scalar", "array"):
    query = Query.model_validate(payload)
    if field == "scalar": query.envelope.nested.contentType = "future"
    else: query.capabilities = ["future"]
    try: query.model_dump_json()
    except PydanticSerializationError: pass
    else: raise AssertionError("unknown enum serialized")
`
		command := exec.Command(python, "-B", "-c", script)
		command.Dir = root
		if output, err := command.CombinedOutput(); err != nil {
			t.Fatalf("generated Pydantic boundary strict=%v: %v\n%s", strict, err, output)
		}
	}
}
