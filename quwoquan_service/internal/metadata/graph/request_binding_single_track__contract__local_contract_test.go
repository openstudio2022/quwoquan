package graph_test

import (
	"bytes"
	"encoding/json"
	"reflect"
	"regexp"
	"sort"
	"strings"
	"testing"

	"quwoquan_service/internal/metadata/ast"
	contractgraph "quwoquan_service/internal/metadata/graph"
	"quwoquan_service/internal/metadata/load"
	"quwoquan_service/internal/testsupport/contractsview"
)

var repositoryPathPlaceholderPattern = regexp.MustCompile(`\{([^{}]+)\}`)

// spec_ref: specs/feature-tree/runtime/runtime-codegen/spec.md#sit-001
//
// This repository-level contract test deliberately consumes the compiler's
// ContractGraph instead of parsing operations.yaml again. It proves that the
// checked-in operation packets use the canonical request binding track and
// that the assertion cannot pass on an empty operation set. App request types,
// codecs and positional binding lists are generated from request_entity plus
// request_bindings; client_contract owns only the response-side ABI.
func TestRepositoryRequestBindingsUseCanonicalSingleTrack(t *testing.T) {
	t.Parallel()

	catalog, err := load.Load(contractsview.Build(t))
	if err != nil {
		t.Fatalf("load repository contract packets: %v", err)
	}
	graph := contractgraph.Build(catalog)

	operations := graph.Operations
	if len(operations) == 0 {
		t.Fatal("empty-green: ContractGraph contains no operations")
	}

	canonicalBindingOperations := 0
	clientContractOperations := 0
	for _, operation := range operations {
		if len(operation.LegacyRequestKeys) != 0 {
			t.Errorf(
				"%s retains editable legacy request keys: %v",
				operation.ID,
				operation.LegacyRequestKeys,
			)
		}
		if len(operation.ClientBindingOverrides) != 0 {
			t.Errorf(
				"%s retains client-owned binding inputs: %v",
				operation.ID,
				operation.ClientBindingOverrides,
			)
		}

		pathBindings := map[string]string{}
		if operation.RequestBindings != nil {
			canonicalBindingOperations++
			pathBindings = repositoryBindingMap(
				t,
				operation,
				"path",
				operation.RequestBindings.Path,
			)
			repositoryBindingMap(
				t,
				operation,
				"query",
				operation.RequestBindings.Query,
			)
			repositoryBindingMap(
				t,
				operation,
				"header",
				operation.RequestBindings.Header,
			)
			repositoryBindingMap(
				t,
				operation,
				"injected",
				operation.RequestBindings.Injected,
			)
		}

		placeholders := repositoryPathPlaceholders(operation.PathTemplate)
		if !reflect.DeepEqual(placeholders, sortedMapKeys(pathBindings)) {
			t.Errorf(
				"%s path placeholders %v do not equal canonical path bindings %v",
				operation.ID,
				placeholders,
				sortedMapKeys(pathBindings),
			)
		}

		if operation.ClientContract == nil {
			continue
		}
		clientContractOperations++
		if strings.TrimSpace(operation.RequestEntity) == "" ||
			(operation.RequestBodyKind != "object" &&
				operation.RequestBodyKind != "none") {
			t.Errorf(
				"%s App client operation has no complete generated request model/body kind",
				operation.ID,
			)
		}
	}

	if canonicalBindingOperations == 0 {
		t.Fatal("empty-green: no operation consumes canonical request_bindings")
	}
	if clientContractOperations == 0 {
		t.Fatal("empty-green: no App client_contract operation was inspected")
	}

	// SourceDocument intentionally preserves every canonical document field,
	// including non-route contract_test vocabulary such as query_params. Inspect
	// the typed operation projection here so similarly named test vocabulary is
	// not mistaken for a retired api_routes input.
	encoded, err := json.Marshal(operations)
	if err != nil {
		t.Fatalf("marshal ContractGraph operations: %v", err)
	}
	if !bytes.Contains(encoded, []byte(`"requestBindings"`)) {
		t.Fatal("ContractGraph omitted every canonical requestBindings projection")
	}
	for _, retired := range []string{
		`"request_fields"`,
		`"path_params"`,
		`"query_params"`,
		`"headers"`,
		`"requestType"`,
		`"requestEncoder"`,
		`"pathBindings"`,
		`"queryBindings"`,
		`"headerBindings"`,
	} {
		if bytes.Contains(encoded, []byte(retired)) {
			t.Errorf("ContractGraph exposes retired editable request key %s", retired)
		}
	}
}

func repositoryBindingMap(
	t *testing.T,
	operation ast.Operation,
	location string,
	bindings []ast.RequestBinding,
) map[string]string {
	t.Helper()
	result := make(map[string]string, len(bindings))
	for _, binding := range bindings {
		name := strings.TrimSpace(binding.Name)
		field := strings.TrimSpace(binding.Field)
		if name == "" || field == "" {
			t.Errorf(
				"%s request_bindings.%s contains an empty name/field: %+v",
				operation.ID,
				location,
				binding,
			)
			continue
		}
		if previous, exists := result[name]; exists {
			t.Errorf(
				"%s request_bindings.%s maps %s to both %s and %s",
				operation.ID,
				location,
				name,
				previous,
				field,
			)
		}
		result[name] = field
	}
	return result
}

func repositoryPathPlaceholders(path string) []string {
	values := make([]string, 0)
	seen := map[string]struct{}{}
	for _, match := range repositoryPathPlaceholderPattern.FindAllStringSubmatch(path, -1) {
		name := strings.TrimSpace(match[1])
		if _, exists := seen[name]; exists {
			continue
		}
		seen[name] = struct{}{}
		values = append(values, name)
	}
	sort.Strings(values)
	return values
}

func sortedMapKeys(values map[string]string) []string {
	keys := make([]string, 0, len(values))
	for key := range values {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}
