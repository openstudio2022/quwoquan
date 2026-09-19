package main

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"github.com/vektah/gqlparser/v2/ast"
	"github.com/vektah/gqlparser/v2/parser"
	"path/filepath"
	"sort"
	"strings"
)

type persistedRequestSpec struct {
	Schema        string `yaml:"schema"`
	OperationID   string `yaml:"canonicalOperationId"`
	OperationName string `yaml:"operationName"`
	OperationType string `yaml:"operationType"`
	Document      string `yaml:"document"`
	Hash          string `yaml:"sha256Hash"`
	Variables     struct {
		Bindings  map[string]string `yaml:"bindings"`
		Constants map[string]any    `yaml:"constants"`
	} `yaml:"variables"`
}

func loadGraphQLRequestSpec(operation appExposedOperation, model requestModelSpec) (*persistedRequestSpec, error) {
	prefix := filepath.ToSlash(filepath.Join(filepath.Dir(operation.SourcePath), "persisted_queries")) + "/"
	var selected *persistedRequestSpec
	for _, path := range activeMetadataSource.Paths(prefix, ".yaml") {
		var descriptor persistedRequestSpec
		if err := activeMetadataSource.Decode(path, &descriptor); err != nil {
			return nil, err
		}
		if descriptor.OperationID != operation.CanonicalOperationID {
			continue
		}
		if selected != nil {
			return nil, fmt.Errorf("%s has multiple persisted request owners", operation.CanonicalOperationID)
		}
		if descriptor.Schema != "qwq.object-owned-internal-persisted-graphql" || descriptor.OperationType != "query" || filepath.Base(descriptor.Document) != descriptor.Document {
			return nil, fmt.Errorf("invalid persisted descriptor")
		}
		documentPath := filepath.ToSlash(filepath.Join(prefix, descriptor.Document))
		raw, err := activeMetadataSource.Content(documentPath)
		if err != nil {
			return nil, err
		}
		sum := sha256.Sum256(raw)
		if hex.EncodeToString(sum[:]) != descriptor.Hash {
			return nil, fmt.Errorf("persisted request document hash drift")
		}
		document, err := parser.ParseQuery(&ast.Source{Input: string(raw)})
		if err != nil {
			return nil, err
		}
		if len(document.Operations) != 1 || document.Operations[0].Operation != ast.Query || document.Operations[0].Name != descriptor.OperationName {
			return nil, fmt.Errorf("persisted request operation mismatch")
		}
		if err := validateGraphQLRequestVariables(model, document.Operations[0].VariableDefinitions, descriptor.Variables.Bindings, descriptor.Variables.Constants); err != nil {
			return nil, fmt.Errorf("%s: %w", operation.CanonicalOperationID, err)
		}
		selected = &descriptor
	}
	if selected == nil {
		return nil, fmt.Errorf("%s GraphQL request requires exact persisted variables descriptor", operation.CanonicalOperationID)
	}
	return selected, nil
}
func validateGraphQLRequestVariables(model requestModelSpec, variables ast.VariableDefinitionList, bindings map[string]string, constants map[string]any) error {
	fields := map[string]fieldDef{}
	for _, field := range model.Fields {
		fields[field.Name] = field
	}
	seen := map[string]bool{}
	declared := map[string]bool{}
	for _, variable := range variables {
		declared[variable.Variable] = true
		fieldName, bound := bindings[variable.Variable]
		value, constant := constants[variable.Variable]
		if bound == constant {
			return fmt.Errorf("variable %s requires exactly one binding or constant", variable.Variable)
		}
		if constant {
			switch variable.Type.Name() {
			case "Int":
				switch value.(type) {
				case int, int64:
				default:
					return fmt.Errorf("constant %s must be integer", variable.Variable)
				}
			case "String", "ID":
				if _, ok := value.(string); !ok {
					return fmt.Errorf("constant string type")
				}
			default:
				return fmt.Errorf("unsupported constant variable type")
			}
			continue
		}
		field, ok := fields[fieldName]
		if !ok || seen[fieldName] {
			return fmt.Errorf("unknown or repeated request field %s", fieldName)
		}
		seen[fieldName] = true
		if variable.Type.NonNull == isRequestFieldNullable(field) {
			return fmt.Errorf("variable %s nullable mismatch", variable.Variable)
		}
		expected := map[string]string{"string": "String", "int": "Int", "int64": "Int", "bool": "Boolean"}[field.Type]
		actual := variable.Type.Name()
		if actual == "ID" {
			actual = "String"
		}
		if expected == "" || expected != actual || variable.Type.Elem != nil {
			return fmt.Errorf("variable %s type mismatch", variable.Variable)
		}
	}
	for name := range bindings {
		if !declared[name] {
			return fmt.Errorf("extra variable binding %s", name)
		}
	}
	for name := range constants {
		if !declared[name] {
			return fmt.Errorf("extra variable constant %s", name)
		}
	}
	if len(seen) != len(fields) {
		return fmt.Errorf("request entity has unbound persisted fields")
	}
	return nil
}
func renderGraphQLRequestEncoder(out *strings.Builder, operation requestOperationSpec, model requestModelSpec, enumValues map[string][]string) error {
	spec := operation.Persisted
	fmt.Fprintf(out, "CloudOperationRequestPayload %s(%s request) {\n return CloudOperationRequestPayload(body: <String,Object?>{'operationName': %q, 'variables': <String,Object?>{\n", generatedOperationRequestEncoder(operation.CanonicalOperationID), operation.RequestType, spec.OperationName)
	fields := map[string]fieldDef{}
	for _, field := range model.Fields {
		fields[field.Name] = field
	}
	names := []string{}
	for name := range spec.Variables.Bindings {
		names = append(names, name)
	}
	sort.Strings(names)
	for _, name := range names {
		field := fields[spec.Variables.Bindings[name]]
		access := "request." + requestFieldDartName(field)
		value, err := requestFieldWireExpression(access, field, false, enumValues)
		if err != nil {
			return err
		}
		if isRequestFieldNullable(field) {
			fmt.Fprintf(out, "if (%s != null) ", access)
		}
		fmt.Fprintf(out, "%q: %s,\n", name, value)
	}
	names = nil
	for name := range spec.Variables.Constants {
		names = append(names, name)
	}
	sort.Strings(names)
	for _, name := range names {
		raw, err := json.Marshal(spec.Variables.Constants[name])
		if err != nil {
			return err
		}
		fmt.Fprintf(out, "%q: %s,\n", name, raw)
	}
	fmt.Fprintf(out, "}, 'extensions': <String,Object?>{'persistedQuery': <String,Object?>{'version':1,'sha256Hash':%q}}});\n}\n", spec.Hash)
	return nil
}
