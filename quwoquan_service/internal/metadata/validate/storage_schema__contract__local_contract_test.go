package validate

import (
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"runtime"
	"sort"
	"strings"
	"testing"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/storagecontract"

	"github.com/santhosh-tekuri/jsonschema/v6"
	"gopkg.in/yaml.v3"
)

func TestAllServiceStorageDocumentsMatchClosedNestedSchema(t *testing.T) {
	t.Parallel()

	schema := compileStorageSchema(t)
	_, thisFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("cannot resolve test file path")
	}
	servicesRoot := filepath.Join(filepath.Dir(thisFile), "..", "..", "..", "services")
	count := 0
	err := filepath.WalkDir(servicesRoot, func(path string, entry os.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() || entry.Name() != "storage.yaml" ||
			!strings.Contains(filepath.ToSlash(path), "/contracts/") {
			return nil
		}
		data, readErr := os.ReadFile(path)
		if readErr != nil {
			return readErr
		}
		if _, decodeErr := storagecontract.DecodeYAML(data); decodeErr != nil {
			t.Errorf("%s does not match canonical StorageDocument: %v", path, decodeErr)
			return nil
		}
		var instance any
		if decodeErr := yaml.Unmarshal(data, &instance); decodeErr != nil {
			t.Errorf("decode %s: %v", path, decodeErr)
			return nil
		}
		if validateErr := schema.Validate(instance); validateErr != nil {
			t.Errorf("%s does not match closed storage schema: %v", path, validateErr)
		}
		count++
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	if count < 100 {
		t.Fatalf("storage schema covered %d documents, want repository inventory", count)
	}
}

func TestStorageSchemaRejectsEveryRetiredAlias(t *testing.T) {
	t.Parallel()

	schema := compileStorageSchema(t)
	for name, storage := range map[string]any{
		"primary_key":               map[string]any{"tables": map[string]any{"records": map[string]any{"primary_key": "id"}}},
		"singular fk":               map[string]any{"tables": map[string]any{"records": map[string]any{"fk": map[string]any{"column": "owner_id"}}}},
		"index predicate":           map[string]any{"tables": map[string]any{"records": map[string]any{"indexes": []any{map[string]any{"name": "idx", "columns": []any{"status"}, "predicate": "status = 'open'"}}}}},
		"collection ttl":            map[string]any{"collections": map[string]any{"records": map[string]any{"ttl": map[string]any{"field": "createdAt", "seconds": 60}}}},
		"camel ttl":                 map[string]any{"collections": map[string]any{"records": map[string]any{"indexes": []any{map[string]any{"name": "ttl", "keys": map[string]any{"createdAt": 1}, "expireAfterSeconds": 60}}}}},
		"index ttl_seconds":         map[string]any{"collections": map[string]any{"records": map[string]any{"indexes": []any{map[string]any{"name": "ttl", "keys": map[string]any{"createdAt": 1}, "ttl_seconds": 60}}}}},
		"unnamed unique constraint": map[string]any{"tables": map[string]any{"records": map[string]any{"unique_constraints": []any{[]any{"owner_id", "key"}}}}},
		"collection search_indexes": map[string]any{"collections": map[string]any{"records": map[string]any{"search_indexes": []any{}}}},
		"lifecycle timers": map[string]any{"lifecycle_timers": map[string]any{"ring_timeout": map[string]any{
			"owner": "rtc-service", "mechanism": "in_process_sweeper", "interval_seconds": 5,
		}}},
		"unknown collection index direction": map[string]any{"collections": map[string]any{"records": map[string]any{"indexes": []any{map[string]any{"name": "idx", "keys": map[string]any{"ownerId": "ascending"}}}}}},
	} {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			storage.(map[string]any)["backend"] = "mongodb"
			storage.(map[string]any)["role"] = "authoritative"
			if err := schema.Validate(storage); err == nil {
				t.Fatal("storage schema accepted retired alias")
			}
		})
	}
}

func TestStorageSchemaOwnsCollectionWriterShape(t *testing.T) {
	t.Parallel()

	schema := compileStorageSchema(t)
	valid := map[string]any{
		"backend": "mongodb",
		"role":    "projection",
		"collections": map[string]any{
			"shared_projection": map[string]any{
				"entity":  "SharedProjection",
				"role":    "projection",
				"writers": []any{"content-service"},
			},
		},
	}
	if err := schema.Validate(valid); err != nil {
		t.Fatalf("schema rejected canonical collection writers: %v", err)
	}

	for name, writers := range map[string]any{
		"empty":            []any{},
		"duplicate":        []any{"content-service", "content-service"},
		"invalid identity": []any{"Content_Service"},
		"scalar":           "content-service",
	} {
		t.Run(name, func(t *testing.T) {
			invalid := map[string]any{
				"backend": "mongodb",
				"role":    "projection",
				"collections": map[string]any{
					"shared_projection": map[string]any{
						"entity":  "SharedProjection",
						"role":    "projection",
						"writers": writers,
					},
				},
			}
			if err := schema.Validate(invalid); err == nil {
				t.Fatalf("schema accepted invalid collection writers %#v", writers)
			}
		})
	}

	unknownField := map[string]any{
		"backend": "mongodb",
		"role":    "projection",
		"collections": map[string]any{
			"shared_projection": map[string]any{
				"entity":          "SharedProjection",
				"role":            "projection",
				"writer_services": []any{"content-service"},
			},
		},
	}
	if err := schema.Validate(unknownField); err == nil {
		t.Fatal("schema accepted noncanonical collection writer alias")
	}
}

func TestStorageSchemaAndTypedDocumentHaveRecursiveKeyParity(t *testing.T) {
	t.Parallel()

	root := loadStorageSchemaDocument(t)
	tests := []struct {
		name   string
		typeOf reflect.Type
		node   map[string]any
	}{
		{"document", reflect.TypeOf(ast.StorageDocument{}), root},
		{"resource", reflect.TypeOf(ast.StorageResource{}), schemaDefinition(t, root, "storageResource")},
		{"table", reflect.TypeOf(ast.StorageTable{}), schemaDefinition(t, root, "storageTable")},
		{"column", reflect.TypeOf(ast.StorageColumn{}), schemaDefinition(t, root, "storageColumn")},
		{"table index", reflect.TypeOf(ast.StorageTableIndex{}), schemaDefinition(t, root, "storageTableIndex")},
		{"unique constraint", reflect.TypeOf(ast.StorageUniqueConstraint{}), schemaDefinition(t, root, "storageUniqueConstraint")},
		{"foreign key", reflect.TypeOf(ast.StorageForeignKey{}), schemaDefinition(t, root, "storageForeignKey")},
		{"table search index", reflect.TypeOf(ast.StorageTableSearchIndex{}), schemaDefinition(t, root, "storageTableSearchIndex")},
		{"collection", reflect.TypeOf(ast.StorageCollection{}), schemaDefinition(t, root, "storageCollection")},
		{"collection index", reflect.TypeOf(ast.StorageCollectionIndex{}), schemaDefinition(t, root, "storageCollectionIndex")},
		{"stream", reflect.TypeOf(ast.StorageStream{}), nestedSchemaNode(t, root, "properties", "streams", "additionalProperties")},
		{"transaction", reflect.TypeOf(ast.StorageTransaction{}), nestedSchemaNode(t, root, "properties", "transaction")},
		{"transaction participant", reflect.TypeOf(ast.StorageTransactionParticipant{}), schemaDefinition(t, root, "storageTransactionParticipant")},
		{"Redis cache", reflect.TypeOf(ast.StorageRedisCache{}), nestedSchemaNode(t, root, "properties", "redis_cache", "items")},
		{"environment backend", reflect.TypeOf(ast.StorageEnvironmentBackend{}), nestedSchemaNode(t, root, "properties", "environment_backends", "additionalProperties")},
		{"logstore", reflect.TypeOf(ast.StorageLogstore{}), nestedSchemaNode(t, root, "properties", "logstores", "additionalProperties")},
		{"codegen", reflect.TypeOf(ast.StorageCodegen{}), nestedSchemaNode(t, root, "properties", "codegen")},
		{"codegen cache override", reflect.TypeOf(ast.StorageCodegenCacheOverride{}), nestedSchemaNode(t, root, "properties", "codegen", "properties", "cache_overrides", "additionalProperties")},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			assertSchemaStructKeyParity(t, test.typeOf, test.node)
		})
	}
}

func compileStorageSchema(t *testing.T) *jsonschema.Schema {
	t.Helper()
	path := storageSchemaPath(t)
	schema, err := jsonschema.NewCompiler().Compile(path)
	if err != nil {
		t.Fatalf("compile storage schema: %v", err)
	}
	return schema
}

func loadStorageSchemaDocument(t *testing.T) map[string]any {
	t.Helper()
	data, err := os.ReadFile(storageSchemaPath(t))
	if err != nil {
		t.Fatal(err)
	}
	var document map[string]any
	if err := json.Unmarshal(data, &document); err != nil {
		t.Fatal(err)
	}
	return document
}

func storageSchemaPath(t *testing.T) string {
	t.Helper()
	_, thisFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("cannot resolve test file path")
	}
	return filepath.Join(filepath.Dir(thisFile), "..", "..", "..", "contracts", "metadata", "_schemas", "storage.schema.json")
}

func schemaDefinition(t *testing.T, root map[string]any, name string) map[string]any {
	t.Helper()
	return nestedSchemaNode(t, root, "$defs", name)
}

func nestedSchemaNode(t *testing.T, root map[string]any, path ...string) map[string]any {
	t.Helper()
	current := any(root)
	for _, segment := range path {
		mapping, ok := current.(map[string]any)
		if !ok {
			t.Fatalf("schema path %v reaches %T before %q", path, current, segment)
		}
		current, ok = mapping[segment]
		if !ok {
			t.Fatalf("schema path %v has no %q", path, segment)
		}
	}
	node, ok := current.(map[string]any)
	if !ok {
		t.Fatalf("schema path %v = %T, want object", path, current)
	}
	return node
}

func assertSchemaStructKeyParity(t *testing.T, typeOf reflect.Type, schema map[string]any) {
	t.Helper()
	if closed, ok := schema["additionalProperties"].(bool); !ok || closed {
		t.Fatalf("schema for %s must declare additionalProperties:false", typeOf.Name())
	}
	properties, ok := schema["properties"].(map[string]any)
	if !ok {
		t.Fatalf("schema for %s has no properties", typeOf.Name())
	}
	var structKeys []string
	for index := 0; index < typeOf.NumField(); index++ {
		key := strings.Split(typeOf.Field(index).Tag.Get("json"), ",")[0]
		if key == "" || key == "-" {
			t.Fatalf("%s.%s has no JSON key", typeOf.Name(), typeOf.Field(index).Name)
		}
		yamlKey := strings.Split(typeOf.Field(index).Tag.Get("yaml"), ",")[0]
		if yamlKey != key {
			t.Fatalf("%s.%s JSON key %q differs from YAML key %q", typeOf.Name(), typeOf.Field(index).Name, key, yamlKey)
		}
		structKeys = append(structKeys, key)
	}
	var schemaKeys []string
	for key := range properties {
		schemaKeys = append(schemaKeys, key)
	}
	sort.Strings(structKeys)
	sort.Strings(schemaKeys)
	if !reflect.DeepEqual(structKeys, schemaKeys) {
		t.Fatalf("%s keys = %v, schema = %v", typeOf.Name(), structKeys, schemaKeys)
	}
}

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-001
func TestStorageSchemaClosesEnginesAndTypesNamedResources(t *testing.T) {
	t.Parallel()

	schema := compileStorageSchema(t)
	valid := map[string]any{
		"backend": "elasticsearch",
		"role":    "projection",
		"resources": map[string]any{
			"search_documents": map[string]any{
				"engine": "elasticsearch",
				"role":   "query_projection",
			},
			"projection_checkpoints": map[string]any{
				"engine":   "mongodb",
				"role":     "runtime",
				"required": false,
			},
		},
	}
	if err := schema.Validate(valid); err != nil {
		t.Fatalf("schema rejected canonical named resources: %v", err)
	}

	for name, mutate := range map[string]func(map[string]any){
		"retired postgresql alias":      func(document map[string]any) { document["backend"] = "postgresql" },
		"composite ES Mongo backend":    func(document map[string]any) { document["backend"] = "elasticsearch+mongodb" },
		"composite Mongo Redis backend": func(document map[string]any) { document["backend"] = "mongodb+redis" },
		"unknown environment backend": func(document map[string]any) {
			document["environment_backends"] = map[string]any{"alpha": map[string]any{"adapter": "ext.search.provider", "backend": "cockroachdb"}}
		},
		"resource missing engine": func(document map[string]any) {
			document["resources"] = map[string]any{"projection_checkpoints": map[string]any{"role": "runtime"}}
		},
		"resource missing role": func(document map[string]any) {
			document["resources"] = map[string]any{"projection_checkpoints": map[string]any{"engine": "mongodb"}}
		},
		"resource contains cluster ref": func(document map[string]any) {
			document["resources"] = map[string]any{"projection_checkpoints": map[string]any{"engine": "mongodb", "role": "runtime", "clusterRef": "mongo-a"}}
		},
		"invalid resource local name": func(document map[string]any) {
			document["resources"] = map[string]any{"ProjectionCheckpoints": map[string]any{"engine": "mongodb", "role": "runtime"}}
		},
		"logical backend cannot be object resource engine": func(document map[string]any) {
			document["resources"] = map[string]any{"catalog": map[string]any{"engine": "service_resource", "role": "query_projection"}}
		},
		"observability sink cannot be object resource engine": func(document map[string]any) {
			document["resources"] = map[string]any{"events": map[string]any{"engine": "observability_log_sink", "role": "append_only_fact"}}
		},
	} {
		name, mutate := name, mutate
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			document := map[string]any{"backend": "elasticsearch", "role": "projection"}
			mutate(document)
			if err := schema.Validate(document); err == nil {
				t.Fatalf("schema accepted invalid storage document: %#v", document)
			}
		})
	}
}

// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/spec.md#sit-001
func TestStorageSchemaTypesMinimalEngineMechanisms(t *testing.T) {
	t.Parallel()

	schema := compileStorageSchema(t)
	valid := map[string]any{
		"backend": "mongodb",
		"role":    "authoritative",
		"transaction": map[string]any{
			"scope": []any{"records"}, "isolation": "mongo_transaction",
			"guarantees": []any{"versioned_write"}, "mechanism": "version_cas",
		},
		"redis_cache": []any{map[string]any{
			"key":                  "probe:{scope}:value:<id>",
			"key_prefix":           "probe:",
			"hash_tag":             "scope",
			"atomic_keys":          []any{"probe:{scope}:value:<id>", "probe:{scope}:fence"},
			"fence":                "token_value",
			"eviction_consequence": "reconstruct",
			"durability":           "aof",
		}},
	}
	if err := schema.Validate(valid); err != nil {
		t.Fatalf("schema rejected typed storage mechanisms: %v", err)
	}
	for _, test := range []struct {
		name, field string
		value       any
	}{
		{"unknown transaction mechanism", "mechanism", "universal_transaction"},
		{"unknown eviction consequence", "eviction_consequence", "best_effort"},
		{"unknown Redis durability", "durability", "durable"},
		{"invalid Redis key prefix", "key_prefix", "Probe"},
		{"invalid Redis hash tag identity", "hash_tag", "scope:value"},
		{"singleton Redis atomic key set", "atomic_keys", []any{"probe:{scope}:value:<id>"}},
		{"unknown Redis fence role", "fence", "best_effort"},
	} {
		test := test
		t.Run(test.name, func(t *testing.T) {
			t.Parallel()
			invalid := map[string]any{"backend": "mongodb", "role": "authoritative"}
			if test.field == "mechanism" {
				invalid["transaction"] = map[string]any{"scope": []any{"records"}, "isolation": "mongo_transaction", "guarantees": []any{"versioned_write"}, test.field: test.value}
			} else {
				invalid["redis_cache"] = []any{map[string]any{"key": "probe:<id>", test.field: test.value}}
			}
			if err := schema.Validate(invalid); err == nil {
				t.Fatal("schema accepted unknown mechanism value")
			}
		})
	}
}
