package validate

import (
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"runtime"
	"testing"

	"quwoquan_service/internal/metadata/ast"

	"github.com/santhosh-tekuri/jsonschema/v6"
)

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001
func TestRepositoryPrivacyDocumentsMatchCanonicalSchema(t *testing.T) {
	t.Parallel()

	schema := compilePrivacySchema(t)
	paths, err := filepath.Glob(filepath.Join(
		privacyServiceRoot(t), "services", "*", "contracts", "*", "*", "privacy.yaml",
	))
	if err != nil {
		t.Fatal(err)
	}
	if len(paths) != 2 {
		t.Fatalf("privacy corpus = %d documents, want current repository inventory 2", len(paths))
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

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001
func TestPrivacySchemaAndTypedDocumentHaveRecursiveKeyParity(t *testing.T) {
	t.Parallel()

	root := loadPrivacySchemaDocument(t)
	tests := []struct {
		name   string
		typeOf reflect.Type
		node   map[string]any
	}{
		{"document", reflect.TypeOf(ast.PrivacyDocument{}), root},
		{"app log policy", reflect.TypeOf(ast.PrivacyAppLogPolicy{}), schemaDefinition(t, root, "appLogPolicy")},
		{"data lifecycle", reflect.TypeOf(ast.PrivacyDataLifecycle{}), schemaDefinition(t, root, "dataLifecycle")},
		{"deletion cascade", reflect.TypeOf(ast.PrivacyDeletionCascade{}), schemaDefinition(t, root, "deletionCascade")},
		{"anonymization", reflect.TypeOf(ast.PrivacyAnonymization{}), schemaDefinition(t, root, "anonymization")},
		{"field visibility", reflect.TypeOf(ast.PrivacyFieldVisibility{}), schemaDefinition(t, root, "fieldVisibility")},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			assertSchemaStructKeyParity(t, test.typeOf, test.node)
		})
	}
}

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001
func TestPrivacySchemaAcceptsFirstPartyServiceInternalAsAConsumerCategory(t *testing.T) {
	t.Parallel()

	document := canonicalPrivacyDocument()
	firstVisibility(document)["visibility"] = []any{"platform-ops", "first_party_service_internal"}
	if err := compilePrivacySchema(t).Validate(document); err != nil {
		t.Fatalf("privacy schema rejected canonical first-party service consumer category: %v", err)
	}
}

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001
func TestPrivacySchemaRejectsRetiredAliasesUnknownKeysAndIncompletePolicies(t *testing.T) {
	t.Parallel()

	schema := compilePrivacySchema(t)
	tests := map[string]func(map[string]any){
		"authored aggregate identity": func(document map[string]any) {
			document["aggregate"] = "Post"
		},
		"unknown root key": func(document map[string]any) {
			document["runtime_redactor"] = "generated"
		},
		"unknown app log key": func(document map[string]any) {
			firstAppLog(document)["formatter"] = "legacy"
		},
		"mask without strategy": func(document map[string]any) {
			delete(firstAppLog(document), "mask_strategy")
		},
		"mask with truncate parameter": func(document map[string]any) {
			firstAppLog(document)["truncate_chars"] = 10
		},
		"truncate without length": func(document map[string]any) {
			entry := firstAppLog(document)
			entry["app_log"] = "truncate"
			delete(entry, "mask_strategy")
		},
		"drop with mask strategy": func(document map[string]any) {
			firstAppLog(document)["app_log"] = "drop"
		},
		"retired user deletion hook": func(document map[string]any) {
			lifecycle(document)["user_deletion_hook"] = true
		},
		"retired deletion entity": func(document map[string]any) {
			firstDeletion(document)["entity"] = "Comment"
			delete(firstDeletion(document), "object_id")
		},
		"ambiguous deletion object id": func(document map[string]any) {
			firstDeletion(document)["object_id"] = "Comment"
		},
		"CDN purge without delay": func(document map[string]any) {
			delete(firstDeletion(document), "cdn_purge_delay_hours")
		},
		"hard delete with CDN controls": func(document map[string]any) {
			firstDeletion(document)["strategy"] = "hard_delete"
		},
		"replacement without placeholder": func(document map[string]any) {
			delete(firstAnonymization(document), "placeholder")
		},
		"drop with placeholder": func(document map[string]any) {
			firstAnonymization(document)["strategy"] = "drop"
		},
		"deletion disabled with work": func(document map[string]any) {
			lifecycle(document)["deletion_on_user_request"] = false
		},
		"visibility scalar alias": func(document map[string]any) {
			firstVisibility(document)["visibility"] = "never_expose"
		},
		"retired visibility note": func(document map[string]any) {
			firstVisibility(document)["note"] = "legacy"
		},
		"unknown visibility": func(document map[string]any) {
			firstVisibility(document)["visibility"] = []any{"everyone"}
		},
		"unknown visibility item key": func(document map[string]any) {
			firstVisibility(document)["route"] = "/post"
		},
	}
	for name, mutate := range tests {
		name := name
		mutate := mutate
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			document := canonicalPrivacyDocument()
			mutate(document)
			if err := schema.Validate(document); err == nil {
				t.Fatalf("privacy schema accepted invalid document: %#v", document)
			}
		})
	}

	if err := schema.Validate(map[string]any{"description": "documentation only"}); err == nil {
		t.Fatal("privacy schema accepted a document without any enforceable policy")
	}
}

func canonicalPrivacyDocument() map[string]any {
	return map[string]any{
		"description": "fixture privacy",
		"app_log_policy": []any{map[string]any{
			"field": "location", "classification": "PII", "app_log": "mask",
			"mask_strategy": "city_level_only",
		}},
		"data_lifecycle": map[string]any{
			"retention_days": 30, "deletion_on_user_request": true,
			"deletion_cascade": []any{map[string]any{
				"object_id": "content.media_asset", "strategy": "soft_delete_then_cdn_purge",
				"soft_delete_first": true, "cdn_purge_delay_hours": 24,
			}},
			"anonymization_on_delete": []any{map[string]any{
				"field": "authorId", "strategy": "replace_with_placeholder",
				"placeholder": "[deleted_user]",
			}},
		},
		"field_visibility": []any{map[string]any{
			"field": "_id", "visibility": []any{"never_expose"},
		}},
	}
}

func firstAppLog(document map[string]any) map[string]any {
	return document["app_log_policy"].([]any)[0].(map[string]any)
}

func lifecycle(document map[string]any) map[string]any {
	return document["data_lifecycle"].(map[string]any)
}

func firstDeletion(document map[string]any) map[string]any {
	return lifecycle(document)["deletion_cascade"].([]any)[0].(map[string]any)
}

func firstAnonymization(document map[string]any) map[string]any {
	return lifecycle(document)["anonymization_on_delete"].([]any)[0].(map[string]any)
}

func firstVisibility(document map[string]any) map[string]any {
	return document["field_visibility"].([]any)[0].(map[string]any)
}

func compilePrivacySchema(t *testing.T) *jsonschema.Schema {
	t.Helper()
	schema, err := jsonschema.NewCompiler().Compile(privacySchemaPath(t))
	if err != nil {
		t.Fatalf("compile privacy schema: %v", err)
	}
	return schema
}

func loadPrivacySchemaDocument(t *testing.T) map[string]any {
	t.Helper()
	data, err := os.ReadFile(privacySchemaPath(t))
	if err != nil {
		t.Fatal(err)
	}
	var document map[string]any
	if err := json.Unmarshal(data, &document); err != nil {
		t.Fatal(err)
	}
	return document
}

func privacySchemaPath(t *testing.T) string {
	t.Helper()
	return filepath.Join(
		privacyServiceRoot(t), "contracts", "metadata", "_schemas", "privacy.schema.json",
	)
}

func privacyServiceRoot(t *testing.T) string {
	t.Helper()
	_, thisFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("cannot resolve test file path")
	}
	return filepath.Clean(filepath.Join(filepath.Dir(thisFile), "..", "..", ".."))
}
