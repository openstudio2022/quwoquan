package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"sort"
	"strings"
	"testing"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/storagecontract"
)

// storage.yaml has one closed wire shape. The generator may use only part of
// the document, but it must still decode the complete canonical type so a new
// or misspelled nested key cannot disappear behind a consumer-specific subset.

func repoRootForTest(t *testing.T) string {
	t.Helper()
	root, err := filepath.Abs(filepath.Join("..", ".."))
	if err != nil {
		t.Fatalf("resolve quwoquan_service root: %v", err)
	}
	return root
}

func loadStorageSchema(t *testing.T) map[string]any {
	t.Helper()
	path := filepath.Join(repoRootForTest(t), "contracts/metadata/_schemas/storage.schema.json")
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatalf("read storage schema: %v", err)
	}
	var schema map[string]any
	if err := json.Unmarshal(raw, &schema); err != nil {
		t.Fatalf("decode storage schema: %v", err)
	}
	return schema
}

func schemaTopLevelKeys(t *testing.T, schema map[string]any) map[string]bool {
	t.Helper()
	properties, ok := schema["properties"].(map[string]any)
	if !ok {
		t.Fatal("storage schema has no top-level properties object")
	}
	keys := make(map[string]bool, len(properties))
	for key := range properties {
		keys[key] = true
	}
	return keys
}

func storageDocumentTags(t *testing.T) map[string]bool {
	t.Helper()
	typ := reflect.TypeOf(ast.StorageDocument{})
	tags := make(map[string]bool, typ.NumField())
	for index := 0; index < typ.NumField(); index++ {
		jsonName := strings.Split(typ.Field(index).Tag.Get("json"), ",")[0]
		yamlName := strings.Split(typ.Field(index).Tag.Get("yaml"), ",")[0]
		if jsonName == "" || jsonName == "-" || yamlName != jsonName {
			t.Fatalf("StorageDocument.%s JSON/YAML tags differ: %q / %q", typ.Field(index).Name, jsonName, yamlName)
		}
		tags[jsonName] = true
	}
	return tags
}

func sortedKeys(set map[string]bool) []string {
	result := make([]string, 0, len(set))
	for key := range set {
		result = append(result, key)
	}
	sort.Strings(result)
	return result
}

func TestStorageSchemaKeepsTopLevelKeySetClosed(t *testing.T) {
	t.Parallel()
	schema := loadStorageSchema(t)
	additional, present := schema["additionalProperties"]
	if !present || additional != false {
		t.Fatalf("storage schema additionalProperties = %v, want false", additional)
	}
}

func TestCodegenStorageUsesCanonicalDocumentWithSchemaKeyParity(t *testing.T) {
	t.Parallel()
	if reflect.TypeOf(StorageYAML{}) != reflect.TypeOf(ast.StorageDocument{}) {
		t.Fatal("StorageYAML must remain an alias of ast.StorageDocument")
	}
	schemaKeys := sortedKeys(schemaTopLevelKeys(t, loadStorageSchema(t)))
	typedKeys := sortedKeys(storageDocumentTags(t))
	if !reflect.DeepEqual(typedKeys, schemaKeys) {
		t.Fatalf("StorageDocument keys = %v, schema keys = %v", typedKeys, schemaKeys)
	}
}

func TestCodegenStorageStrictDecoderCoversEveryAuthoredDocument(t *testing.T) {
	t.Parallel()
	root := repoRootForTest(t)
	count := 0
	for _, area := range []string{"services", "control-plane"} {
		base := filepath.Join(root, area)
		err := filepath.WalkDir(base, func(path string, entry os.DirEntry, walkErr error) error {
			if walkErr != nil {
				return walkErr
			}
			if entry.IsDir() || entry.Name() != "storage.yaml" || !strings.Contains(filepath.ToSlash(path), "/contracts/") {
				return nil
			}
			raw, err := os.ReadFile(path)
			if err != nil {
				return err
			}
			if _, err := storagecontract.DecodeYAML(raw); err != nil {
				t.Errorf("%s does not match canonical StorageDocument: %v", path, err)
			}
			count++
			return nil
		})
		if err != nil && !os.IsNotExist(err) {
			t.Fatalf("walk %s: %v", area, err)
		}
	}
	if count < 100 {
		t.Fatalf("strict storage reader covered %d documents, want repository inventory", count)
	}
}

func TestCodegenStorageRejectsUnknownNestedKey(t *testing.T) {
	t.Parallel()
	_, err := storagecontract.DecodeYAML([]byte(`backend: mongodb
role: projection
collections:
  views:
    indexes:
      - name: by_owner
        keys: {ownerId: 1}
        undocumented_hint: true
`))
	if err == nil {
		t.Fatal("canonical storage decoder accepted an unknown nested key")
	}
}
