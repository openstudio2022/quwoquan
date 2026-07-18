package openapi

import (
	"testing"

	"quwoquan_service/internal/metadata/ast"

	"gopkg.in/yaml.v3"
)

func commandOperation(
	id string,
	localID string,
	domain string,
	objectID string,
	method string,
	path string,
	requestEntity string,
	responseEntity string,
) ast.Operation {
	return ast.Operation{
		ID:               id,
		LocalID:          localID,
		Domain:           domain,
		ObjectID:         objectID,
		Method:           method,
		PathTemplate:     path,
		Kind:             ast.OperationKindCommand,
		KindExplicit:     true,
		Facet:            localID + "CommandFacade",
		FacadeMethod:     "execute",
		AggregateOwner:   "Post",
		ActorRequirement: "persona",
		RequestEntity:    requestEntity,
		ResponseEntity:   responseEntity,
	}
}

func queryOperation(
	id string,
	localID string,
	domain string,
	objectID string,
	path string,
	responseBody string,
	responseBodyKind string,
) ast.Operation {
	return ast.Operation{
		ID:               id,
		LocalID:          localID,
		Domain:           domain,
		ObjectID:         objectID,
		Method:           "GET",
		PathTemplate:     path,
		Kind:             ast.OperationKindQuery,
		KindExplicit:     true,
		Facet:            localID + "QueryFacade",
		FacadeMethod:     "get",
		Reader:           localID + "Reader",
		Slice:            localID + "Slice",
		ActorRequirement: "persona_or_device",
		ResponseBody:     responseBody,
		ResponseBodyKind: responseBodyKind,
	}
}

func decodeSnapshot(t *testing.T, snapshot Snapshot) map[string]any {
	t.Helper()
	var document map[string]any
	if err := yaml.Unmarshal(snapshot.Content, &document); err != nil {
		t.Fatalf("decode %s: %v\n%s", snapshot.RelativePath, err, snapshot.Content)
	}
	return document
}

func operationAt(
	t *testing.T,
	document map[string]any,
	path string,
	method string,
) map[string]any {
	t.Helper()
	paths := document["paths"].(map[string]any)
	pathItem, exists := paths[path].(map[string]any)
	if !exists {
		t.Fatalf("missing OpenAPI path %s", path)
	}
	operation, exists := pathItem[method].(map[string]any)
	if !exists {
		t.Fatalf("missing OpenAPI operation %s %s", method, path)
	}
	return operation
}

func assertOperationBinding(
	t *testing.T,
	document map[string]any,
	path string,
	method string,
	localID string,
	objectID string,
	actor string,
	kind string,
) {
	t.Helper()
	operation := operationAt(t, document, path, method)
	if got := operation["operationId"]; got != localID {
		t.Fatalf("%s %s operationId = %v, want %s", method, path, got, localID)
	}
	if got := operation["x-object-id"]; got != objectID {
		t.Fatalf("%s %s x-object-id = %v, want %s", method, path, got, objectID)
	}
	if got := operation["x-actor"]; got != actor {
		t.Fatalf("%s %s x-actor = %v, want %s", method, path, got, actor)
	}
	application := operation["x-application"].(map[string]any)
	if got := application["kind"]; got != kind {
		t.Fatalf("%s %s x-application.kind = %v, want %s", method, path, got, kind)
	}
}

func assertPathParameter(
	t *testing.T,
	document map[string]any,
	path string,
	method string,
	name string,
) {
	t.Helper()
	operation := operationAt(t, document, path, method)
	for _, raw := range operation["parameters"].([]any) {
		parameter := raw.(map[string]any)
		if parameter["name"] == name &&
			parameter["in"] == "path" &&
			parameter["required"] == true {
			return
		}
	}
	t.Fatalf("%s %s missing required path parameter %s", method, path, name)
}

func assertHeaderParameter(
	t *testing.T,
	document map[string]any,
	path string,
	method string,
	name string,
	required bool,
) {
	t.Helper()
	operation := operationAt(t, document, path, method)
	for _, raw := range operation["parameters"].([]any) {
		parameter := raw.(map[string]any)
		if parameter["name"] == name &&
			parameter["in"] == "header" &&
			parameter["required"] == required {
			return
		}
	}
	t.Fatalf(
		"%s %s missing header parameter %s required=%t",
		method,
		path,
		name,
		required,
	)
}

func assertSchemaRef(
	t *testing.T,
	container map[string]any,
	contentKey string,
	want string,
) {
	t.Helper()
	content := container[contentKey].(map[string]any)
	mediaType := content["application/json"].(map[string]any)
	if got := mediaType["schema"].(map[string]any)["$ref"]; got != want {
		t.Fatalf("schema ref = %v, want %s", got, want)
	}
}

func assertDriftKind(
	t *testing.T,
	drifts []Drift,
	kind DriftKind,
	relativePath string,
) {
	t.Helper()
	for _, drift := range drifts {
		if drift.Kind == kind && drift.RelativePath == relativePath {
			return
		}
	}
	t.Fatalf("missing drift %s for %s: %+v", kind, relativePath, drifts)
}
