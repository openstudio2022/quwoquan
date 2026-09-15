package main

import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	goast "go/ast"
	"go/parser"
	"go/token"
	"gopkg.in/yaml.v3"
	"os"
	"path/filepath"
	contractcodegen "quwoquan_service/internal/metadata/codegen"
	"quwoquan_service/internal/metadata/validate"
	"strconv"
	"strings"
	"testing"
)

func TestProvenanceManifestBindsSortedExactOutputBytes(t *testing.T) {
	root := t.TempDir()
	first := filepath.Join(root, "generated", "b.py")
	second := filepath.Join(root, "generated", "a", "payload.g.go")
	for path, body := range map[string]string{first: "b\n", second: "a\n"} {
		if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(path, []byte(body), 0o644); err != nil {
			t.Fatal(err)
		}
	}
	manifestPath := filepath.Join(root, "rec_model_python_manifest.json")
	if err := writeProvenanceManifest(manifestPath, []string{filepath.Dir(first)}); err != nil {
		t.Fatal(err)
	}
	var manifest struct {
		Generator string             `json:"generator"`
		Outputs   []provenanceOutput `json:"outputs"`
	}
	body, err := os.ReadFile(manifestPath)
	if err != nil {
		t.Fatal(err)
	}
	if err := json.Unmarshal(body, &manifest); err != nil {
		t.Fatal(err)
	}
	if manifest.Generator != "tools/codegen_rec_model_python" || len(manifest.Outputs) != 2 {
		t.Fatalf("unexpected provenance manifest: %+v", manifest)
	}
	if manifest.Outputs[0].Path != filepath.ToSlash(second) || manifest.Outputs[1].Path != filepath.ToSlash(first) {
		t.Fatalf("manifest outputs are not sorted exact paths: %+v", manifest.Outputs)
	}
	for _, current := range manifest.Outputs {
		want, err := os.ReadFile(filepath.FromSlash(current.Path))
		if err != nil {
			t.Fatal(err)
		}
		if current.SHA256 != fmt.Sprintf("%x", sha256.Sum256(want)) || current.Bytes != len(want) {
			t.Fatalf("manifest does not bind exact bytes: %+v", current)
		}
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
func TestReleaseTransportDependencyClosure(t *testing.T) {
	shared := map[string]entityDef{
		"Release": {Fields: []fieldDef{{Name: "releaseId", Type: "string", Constraints: []string{"NOT_NULL"}}}},
		"Fence":   {Fields: []fieldDef{{Name: "release", Type: "Release", Constraints: []string{"NULLABLE"}}, {Name: "revision", Type: "int64", Constraints: []string{"NOT_NULL"}}}},
		"Proof":   {Fields: []fieldDef{{Name: "fences", Type: "[]Fence", Constraints: []string{"NULLABLE"}}}},
	}
	fields := &fieldsFile{Entities: map[string]entityDef{"ReadReadinessQuery": {Fields: []fieldDef{{Name: "contentFence", Type: "Fence", Constraints: []string{"NOT_NULL"}}}}}}
	ops := &operationsFile{APIRoutes: []routeDef{{Method: "POST", Path: "/readiness:query", Operation: "ReadReadiness", RequestEntity: "ReadReadinessQuery", ResponseEntity: "Proof"}}}
	order, err := resolveTransportClosure(fields, shared, ops)
	if err != nil {
		t.Fatal(err)
	}
	python := generateRequestResponsePyForNames(fields, order)
	goSource := generateRankedWindowGoTransport(fields, ops)
	for _, want := range []string{"contentFence: Fence", "release: Release | None = None", "fences: list[Fence] | None = None", "class Proof(BaseModel):"} {
		if !strings.Contains(python, want) {
			t.Fatalf("Python lost %q: %s", want, python)
		}
	}
	for _, want := range []string{"ContentFence Fence", "Release *Release", "Fences *[]Fence", "type Proof struct", "ReadReadinessMethod = \"POST\""} {
		if !strings.Contains(goSource, want) {
			t.Fatalf("Go lost %q: %s", want, goSource)
		}
	}
	if strings.Index(python, "class Release(") > strings.Index(python, "class Fence(") {
		t.Fatal("dependencies must precede users")
	}
	again, err := resolveTransportClosure(fields, shared, ops)
	if err != nil || strings.Join(order, ",") != strings.Join(again, ",") {
		t.Fatal("closure is not deterministic", err)
	}
	if len(shared) != 3 {
		t.Fatal("shared authoring was mutated")
	}
	bad := &fieldsFile{Entities: map[string]entityDef{"ReadReadinessQuery": {Fields: []fieldDef{{Name: "missing", Type: "[]Unknown", Constraints: []string{"NULLABLE"}}}}}}
	if _, err := resolveTransportClosure(bad, shared, ops); err == nil {
		t.Fatal("missing type must fail closed, not become a Map")
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
func TestTransportClosureRejectsCyclesAndDoesNotPartiallyPublish(t *testing.T) {
	f := &fieldsFile{Entities: map[string]entityDef{"A": {Fields: []fieldDef{{Name: "b", Type: "B"}}}}}
	shared := map[string]entityDef{"B": {Fields: []fieldDef{{Name: "a", Type: "[]A"}}}}
	if _, err := resolveTransportClosure(f, shared, &operationsFile{}); err == nil || !strings.Contains(err.Error(), "TYPE_CYCLE") {
		t.Fatalf("cycle must fail: %v", err)
	}
	if len(f.Entities) != 1 || f.Order != nil {
		t.Fatal("failed resolution partially published types")
	}
	if _, err := resolveTransportClosure(f, map[string]entityDef{"A": {}}, &operationsFile{}); err == nil || !strings.Contains(err.Error(), "TYPE_CONFLICT") {
		t.Fatalf("conflicting shared type: %v", err)
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
func TestCanonicalReleaseReadinessEmission(t *testing.T) {
	read := func(path string, out any) {
		data, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		if err := yaml.Unmarshal(data, out); err != nil {
			t.Fatal(err)
		}
	}
	var f, shared fieldsFile
	var ops operationsFile
	root := filepath.Join("..", "..")
	base := filepath.Join(root, "services/recommendation-service/contracts/recommendation/ranked_recommendation_window")
	read(filepath.Join(base, "fields.yaml"), &f)
	f.Entities = f.Types
	read(filepath.Join(root, "contracts/metadata/_shared/types.yaml"), &shared)
	read(filepath.Join(base, "operations.yaml"), &ops)
	order, err := resolveTransportClosure(&f, shared.Types, &ops)
	if err != nil {
		t.Fatal(err)
	}
	goText := generateRankedWindowGoTransport(&f, &ops)
	pyText := generateRequestResponsePyForNames(&f, order)
	for _, name := range []string{"ReleaseCandidateBinding", "ReleasePinnedQueryFence", "ReleaseQueryReadinessProof", "ReleaseQueryClassEvidence", "ReadRecommendationReleaseReadinessQuery"} {
		if !strings.Contains(goText, "type "+name+" struct") || !strings.Contains(pyText, "class "+name+"(BaseModel)") {
			t.Fatalf("missing reachable type %s", name)
		}
	}
	if !strings.Contains(goText, "ContentFence ReleasePinnedQueryFence") || !strings.Contains(pyText, "queryClasses: list[ReleaseQueryClassEvidence]") {
		t.Fatal("shared types degraded")
	}
	if _, err := parser.ParseFile(token.NewFileSet(), "generated.go", goText, parser.AllErrors); err != nil {
		t.Fatal(err)
	}
	if goText != generateRankedWindowGoTransport(&f, &ops) || pyText != generateRequestResponsePyForNames(&f, order) {
		t.Fatal("nondeterministic emission")
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
func TestConsumerEventPayloadClosure(t *testing.T) {
	f := &fieldsFile{Entities: map[string]entityDef{"Prepared": {Fields: []fieldDef{{Name: "snapshot", Type: "Snapshot", Constraints: []string{"NOT_NULL"}}}}}}
	shared := map[string]entityDef{"Snapshot": {Fields: []fieldDef{{Name: "items", Type: "[]Item", Constraints: []string{"NOT_NULL"}}}}, "Item": {Fields: []fieldDef{{Name: "id", Type: "string", Constraints: []string{"NOT_NULL"}}}}}
	order, err := resolveEventPayloadClosure(f, shared, "Prepared", []string{"snapshot"})
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(generateRequestResponsePyForNames(f, order), "items: list[Item]") {
		t.Fatal("event shared payload degraded")
	}
	if _, err := resolveEventPayloadClosure(f, shared, "Prepared", nil); err == nil {
		t.Fatal("empty event cannot emit empty green DTO")
	}
	if _, err := resolveEventPayloadClosure(f, shared, "Prepared", []string{"missing"}); err == nil {
		t.Fatal("missing payload field accepted")
	}
	semantic := &fieldsFile{Entities: map[string]entityDef{"Lifecycle": {Fields: []fieldDef{{Name: "semanticDocument", Type: "semantic_document", Constraints: []string{"NULLABLE"}}}}}}
	semanticOrder, err := resolveEventPayloadClosure(semantic, nil, "Lifecycle", []string{"semanticDocument"})
	if err != nil {
		t.Fatalf("semantic_document must remain an external structured payload: %v", err)
	}
	generated := generateRequestResponsePyForNames(semantic, semanticOrder)
	if !strings.Contains(generated, "semanticDocument: dict[str, Any] | None = None") {
		t.Fatalf("semantic_document Python wire type degraded: %s", generated)
	}
	if got := goTransportType("semantic_document", false, nil); got != "map[string]any" {
		t.Fatalf("semantic_document Go wire type = %s, want map[string]any", got)
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
func TestCanonicalConsumedEventProducesPreparedSource(t *testing.T) {
	view := os.Getenv("QWQ_TEST_CONTRACT_VIEW")
	if view == "" {
		t.Skip("explicit current canonical view required")
	}
	source, err := contractcodegen.NewSource(view, validate.ProfileBaseline)
	if err != nil {
		t.Fatal(err)
	}
	out := t.TempDir()
	err = generateConsumedEvents(source, "recommendation/recommendation/recommendation_candidate_index_view", out)
	if err != nil {
		t.Fatalf("canonical producer payloads must resolve completely: %v", err)
	}
	prepared, err := os.ReadFile(filepath.Join(out, "content_post_PostReleaseCandidatePrepared.py"))
	if err != nil {
		t.Fatal(err)
	}
	for _, typ := range []string{"PostReleaseCandidatePrepared", "ReleasePostCandidateSnapshot", "ReleasePostPublicSnapshot", "ReleaseHomepagePublicSnapshot"} {
		if !strings.Contains(string(prepared), "class "+typ+"(BaseModel)") {
			t.Fatal("missing", typ)
		}
	}
	candidate, err := os.ReadFile(filepath.Join(out, "candidate_contracts.py"))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(candidate), "class ReleasePremiumAdmission(BaseModel)") {
		t.Fatal("missing typed premium source")
	}
	premium, err := os.ReadFile(filepath.Join(out, "ops_premium_pool_entry_PremiumPoolEntryUpserted.py"))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(premium), "releaseAdmissions: list[ReleasePremiumAdmission]") {
		t.Fatal("premium authority source lost")
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
func TestPostPayloadFieldsCoverActualProducerMaps(t *testing.T) {
	root := filepath.Join("..", "..")
	var fields fieldsFile
	data, err := os.ReadFile(filepath.Join(root, "services/content-service/contracts/content/post/fields.yaml"))
	if err != nil {
		t.Fatal(err)
	}
	if err := yaml.Unmarshal(data, &fields); err != nil {
		t.Fatal(err)
	}
	for _, test := range []struct{ path, function, payload string }{
		{"services/content-service/internal/content/post/application/post_service_helpers.go", "projectionPayloadForPost", "PostLifecycleProjectionPayload"},
		{"services/content-service/internal/content/post/application/post_service_lifecycle.go", "DeletePost", "PostDeletedPayload"},
	} {
		node, err := parser.ParseFile(token.NewFileSet(), filepath.Join(root, test.path), nil, 0)
		if err != nil {
			t.Fatal(err)
		}
		declared := map[string]bool{}
		for _, f := range fields.Types[test.payload].Fields {
			declared[f.Name] = true
		}
		count := 0
		for _, decl := range node.Decls {
			fn, ok := decl.(*goast.FuncDecl)
			if !ok || fn.Name.Name != test.function {
				continue
			}
			goast.Inspect(fn.Body, func(n goast.Node) bool {
				lit, ok := n.(*goast.CompositeLit)
				if !ok {
					return true
				}
				if _, ok := lit.Type.(*goast.MapType); !ok {
					return true
				}
				for _, elt := range lit.Elts {
					kv, ok := elt.(*goast.KeyValueExpr)
					if !ok {
						continue
					}
					key, ok := kv.Key.(*goast.BasicLit)
					if !ok || key.Kind != token.STRING {
						continue
					}
					name, _ := strconv.Unquote(key.Value)
					if name == "actorId" {
						continue
					}
					count++
					if !declared[name] {
						t.Errorf("%s producer field %s absent from %s", test.function, name, test.payload)
					}
				}
				return false
			})
		}
		if count < 6 {
			t.Fatal("producer map scan empty", test.path)
		}
	}
}

func TestGenerateModelsInitProjectionExports(t *testing.T) {
	t.Run("empty projections do not import retired models", func(t *testing.T) {
		generated := generateModelsInit(nil)
		if strings.Contains(generated, "from .projections") {
			t.Fatalf("empty projection metadata must not emit projection imports:\n%s", generated)
		}
	})

	t.Run("current projections define the exported classes", func(t *testing.T) {
		generated := generateModelsInit([]projectionSpec{
			{ReadModel: "ModelRegistry"},
			{ReadModel: "TrainingSamples"},
		})
		for _, expected := range []string{"ModelRegistryEntry", "TrainingSample"} {
			if !strings.Contains(generated, expected) {
				t.Fatalf("generated exports missing %q:\n%s", expected, generated)
			}
		}
	})
}

func TestGenerateRankedWindowGoTransportExcludesInjectedRequestFields(t *testing.T) {
	generated := generateRankedWindowGoTransport(
		&fieldsFile{Entities: map[string]entityDef{
			"CreateRankedRecommendationWindowCommand": {
				Fields: []fieldDef{
					{Name: "idempotencyKey", Type: "string", Constraints: []string{"NOT_NULL"}},
					{Name: "subjectId", Type: "string", Constraints: []string{"NOT_NULL"}},
					{Name: "limit", Type: "int", Constraints: []string{"NOT_NULL"}},
				},
			},
		}},
		&operationsFile{APIRoutes: []routeDef{
			{
				Method:        "POST",
				Path:          "/internal/recommendation/ranked-pages",
				Operation:     "CreateRankedRecommendationWindow",
				RequestEntity: "CreateRankedRecommendationWindowCommand",
				RequestBindings: requestBindings{Injected: []bindingDef{
					{Name: "Idempotency-Key", Field: "idempotencyKey"},
				}},
			},
		}},
	)
	bodyStart := strings.Index(generated, "type CreateRankedRecommendationWindowRequestBody struct")
	if bodyStart < 0 {
		t.Fatalf("generated transport is missing request body type:\n%s", generated)
	}
	body := generated[bodyStart:]
	if strings.Contains(body, "IdempotencyKey") {
		t.Fatalf("injected idempotency key must not be emitted in the JSON body:\n%s", body)
	}
	for _, expected := range []string{"SubjectId string", "Limit int"} {
		if !strings.Contains(body, expected) {
			t.Fatalf("generated request body missing %q:\n%s", expected, body)
		}
	}
}

func TestGenerateRankedWindowTransportIncludesObjectOwnedCardSnapshot(t *testing.T) {
	fields := &fieldsFile{Entities: map[string]entityDef{
		"RecommendationObjectCard": {
			Fields: []fieldDef{
				{Name: "objectKind", Type: "string", Constraints: []string{"NOT_NULL"}},
				{Name: "objectId", Type: "string", Constraints: []string{"NOT_NULL"}},
			},
		},
		"RankedRecommendationPage": {
			Fields: []fieldDef{
				{Name: "objectCards", Type: "[]RecommendationObjectCard", Constraints: []string{"NOT_NULL"}},
			},
		},
		"GetRankedRecommendationPageQuery": {
			Fields: []fieldDef{
				{Name: "subjectId", Type: "string", Constraints: []string{"NOT_NULL"}},
				{Name: "windowId", Type: "string", Constraints: []string{"NOT_NULL"}},
				{Name: "fromOrdinal", Type: "int", Constraints: []string{"NULLABLE"}},
				{Name: "limit", Type: "int", Constraints: []string{"NULLABLE"}},
			},
		},
	}}

	python := generateRequestResponsePyForNames(fields, transportOrder(fields))
	for _, expected := range []string{
		"class RecommendationObjectCard(BaseModel):",
		"class GetRankedRecommendationPageQuery(BaseModel):",
		"subjectId: str",
		"objectCards: list[RecommendationObjectCard]",
	} {
		if !strings.Contains(python, expected) {
			t.Fatalf("generated Python transport missing %q:\n%s", expected, python)
		}
	}

	goTransport := generateRankedWindowGoTransport(fields, &operationsFile{})
	for _, expected := range []string{
		"type RecommendationObjectCard struct",
		"type GetRankedRecommendationPageQuery struct",
		"SubjectId string",
		"ObjectCards []RecommendationObjectCard",
	} {
		if !strings.Contains(goTransport, expected) {
			t.Fatalf("generated Go transport missing %q:\n%s", expected, goTransport)
		}
	}
}

func TestFeatureProfileTransportUsesObjectLocalIntersectionProjectionTypes(t *testing.T) {
	fields := &fieldsFile{Entities: map[string]entityDef{
		"IntersectionTarget": {Fields: []fieldDef{
			{Name: "objectId", Type: "string", Constraints: []string{"NOT_NULL"}},
		}},
		"IntersectionReason": {Fields: []fieldDef{
			{Name: "intersectionId", Type: "string", Constraints: []string{"NOT_NULL"}},
			{Name: "typeVisual", Type: "IntersectionTarget", Constraints: []string{"NULLABLE"}},
		}},
		"RecommendationIntersectionReasonSlice": {Fields: []fieldDef{
			{Name: "subjectId", Type: "string", Constraints: []string{"NOT_NULL"}},
			{Name: "reasons", Type: "[]IntersectionReason", Constraints: []string{"NOT_NULL"}},
		}},
	}}

	python := generateRequestResponsePyForNames(fields, featureProfileTransportOrder)
	for _, expected := range []string{
		"class IntersectionReason(BaseModel):",
		"typeVisual: IntersectionTarget | None = None",
		"reasons: list[IntersectionReason]",
	} {
		if !strings.Contains(python, expected) {
			t.Fatalf("generated feature-profile Python missing %q:\n%s", expected, python)
		}
	}

	goTransport := generateFeatureProfileGoTransport(fields, &operationsFile{})
	for _, expected := range []string{
		"type IntersectionReason struct",
		"TypeVisual *IntersectionTarget",
		"Reasons []IntersectionReason",
	} {
		if !strings.Contains(goTransport, expected) {
			t.Fatalf("generated feature-profile Go missing %q:\n%s", expected, goTransport)
		}
	}
}
