package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"quwoquan_service/internal/metadata/ast"
	"quwoquan_service/internal/metadata/graph"
	"quwoquan_service/internal/metadata/storagecontract"
)

func TestSourceRoutesGeneratedOwnershipToObjectPacket(t *testing.T) {
	t.Parallel()

	source := Source{
		ObjectPath: "persona/profile_update_proposal",
		DomainPkg:  "profile_update_proposal",
		DomainPath: "model",
	}
	ctx := &genContext{
		manifest: &Manifest{OutputDir: "services/user-service/generated", ModulePath: "example/generated"},
		source:   source,
	}
	if got, want := source.modelImport(ctx.modulePath()), "example/generated/persona/profile_update_proposal/contract/model"; got != want {
		t.Fatalf("model import = %q, want %q", got, want)
	}
	if got, want := filepath.ToSlash(source.infrastructurePath("persistence")), "persistence/model/persistence"; got != want {
		t.Fatalf("persistence path = %q, want %q", got, want)
	}
	if got, want := filepath.ToSlash(ctx.outputDir()), "services/user-service/generated/persona/profile_update_proposal"; got != want {
		t.Fatalf("object output = %q, want %q", got, want)
	}
	if got, want := filepath.ToSlash(ctx.migrationDir()), "services/user-service/resources/migrations/persona/profile_update_proposal"; got != want {
		t.Fatalf("object migration directory = %q, want %q", got, want)
	}
}

func TestFieldTypeToGoTypeAcceptsCanonicalStringSlice(t *testing.T) {
	t.Parallel()

	if got := fieldTypeToGoType(nil, "OverriddenProfileFields", "[]string", false); got != "[]string" {
		t.Fatalf("canonical []string mapped to %q, want []string", got)
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-governance/spec.md#sit-003
func TestEventConstantValueUsesAuthoredOutboxWireIdentity(t *testing.T) {
	t.Parallel()

	got, err := (eventDef{
		Name:              "MediaUploadCompleted",
		DeliverySemantics: "transactional_outbox",
		WireEventType:     "content.media_upload.completed",
	}).ConstantValue()
	if err != nil {
		t.Fatal(err)
	}
	if got != "content.media_upload.completed" {
		t.Fatalf("wire value = %q, want authored wire_event_type", got)
	}
}

func TestEventConstantValueFailsClosedForMissingOutboxWireIdentity(t *testing.T) {
	t.Parallel()

	if _, err := (eventDef{
		Name:              "MediaUploadCompleted",
		DeliverySemantics: "transactional_outbox",
	}).ConstantValue(); err == nil {
		t.Fatal("missing wire_event_type must fail")
	}
	got, err := (eventDef{
		Name:              "LocalAuditRecorded",
		DeliverySemantics: "transactional_event_log",
	}).ConstantValue()
	if err != nil || got != "LocalAuditRecorded" {
		t.Fatalf("non-outbox wire value = %q, err=%v", got, err)
	}
}

// spec_ref: specs/feature-tree/runtime/runtime-governance/spec.md#sit-003
func TestGenerateMergedEventConstantsEmitsAuthoredWireIdentity(t *testing.T) {
	t.Parallel()

	const metadataPath = "media/media_upload_session"
	outputDir := t.TempDir()
	manifest := &Manifest{
		Service: "content-service", OutputDir: outputDir,
		ModulePath: "quwoquan_service/services/content-service/generated",
		Sources: []Source{{
			Metadata: metadataPath, ObjectPath: metadataPath,
			DomainPkg: "media_upload_session",
		}},
	}
	contractGraph := &graph.ContractGraph{
		Objects: []ast.Object{{
			ID: "content.media_upload_session", Name: "MediaUploadSession",
			SourcePath: metadataPath + "/object.yaml",
		}},
		Governance: ast.MetadataGovernance{Objects: []ast.ObjectGovernance{{
			ObjectID: "content.media_upload_session",
			Events: []ast.EventDefinition{{
				ObjectID: "content.media_upload_session", Name: "MediaUploadCompleted",
				DeliverySemantics: "transactional_outbox",
				WireEventType:     "content.media_upload.completed",
				SourcePath:        metadataPath + "/events.yaml",
			}},
		}}},
		Documents: []ast.SourceDocument{{
			Path: metadataPath + "/events.yaml",
			Content: json.RawMessage(`{
				"events":[{
					"name":"MediaUploadCompleted",
					"delivery_semantics":"transactional_outbox",
					"wire_event_type":"content.media_upload.completed"
				}]
			}`),
		}},
	}
	if err := generateMergedEventConstants(manifest, contractGraph); err != nil {
		t.Fatal(err)
	}
	generated, err := os.ReadFile(filepath.Join(
		outputDir,
		metadataPath,
		"contract",
		"media_upload_session",
		"event",
		"events.g.go",
	))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(
		string(generated),
		`MediaUploadCompleted = "content.media_upload.completed"`,
	) {
		t.Fatalf("generated event constant did not preserve wire_event_type:\n%s", generated)
	}
}

func TestStorageYAMLAcceptsCanonicalPrimaryKeyList(t *testing.T) {
	t.Parallel()

	storage, err := storagecontract.DecodeYAML([]byte(`
backend: postgres
role: authoritative
tables:
  user_profiles:
    entity: UserAccount
    pk:
      - user_id
`))
	if err != nil {
		t.Fatal(err)
	}
	primaryKey := storage.Tables["user_profiles"].PK
	if len(primaryKey) != 1 || primaryKey[0] != "user_id" {
		t.Fatalf("primary key = %#v, want [user_id]", primaryKey)
	}
}

func TestGeneratedStoreForeignKeyUsesCanonicalForeignKeysShape(t *testing.T) {
	t.Parallel()
	table := TableDef{ForeignKeys: []ForeignKeyDef{{
		Columns: []string{"owner_id"}, References: "owners(id)", OnDelete: "CASCADE",
	}}}
	foreignKey := generatedStoreForeignKey(table)
	if foreignKey == nil || len(foreignKey.Columns) != 1 || foreignKey.Columns[0] != "owner_id" {
		t.Fatalf("foreign key = %#v", foreignKey)
	}
	if got := generatedStoreForeignKey(TableDef{ForeignKeys: []ForeignKeyDef{{
		Columns: []string{"owner_id", "device_id"}, References: "owners(owner_id, device_id)",
	}}}); got != nil {
		t.Fatalf("composite foreign key must require an object-owned query facade, got %#v", got)
	}
}

func TestMongoStoreGenerationPreservesCanonicalTTLIndex(t *testing.T) {
	t.Parallel()
	expiration := int64(0)
	ctx := &genContext{
		manifest: &Manifest{OutputDir: t.TempDir(), ModulePath: "example/generated"},
		source:   Source{ObjectPath: "catalog/item", DomainPkg: "catalog"},
		fields: &FieldsYAML{Entities: map[string]EntityFieldsDef{
			"Item": {},
		}},
	}
	collection := CollectionDef{
		Entity: "Item",
		Indexes: []MongoIdx{{
			Name: "idx_item_expire", Keys: map[string]any{"expireAt": 1},
			ExpireAfterSeconds: &expiration,
		}},
	}
	if err := generateMongoStore(ctx, "items", collection); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(
		ctx.outputDir(), ctx.source.infrastructurePath("persistence"), "mongo_item_store.g.go",
	)
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(data), ".SetExpireAfterSeconds(0)") {
		t.Fatalf("generated index dropped expire_after_seconds:\n%s", data)
	}
}

func TestMongoStoreGenerationRejectsUnsupportedIndexUnion(t *testing.T) {
	t.Parallel()
	ctx := &genContext{
		manifest: &Manifest{OutputDir: t.TempDir(), ModulePath: "example/generated"},
		source:   Source{ObjectPath: "catalog/item", DomainPkg: "catalog"},
		fields:   &FieldsYAML{Entities: map[string]EntityFieldsDef{"Item": {}}},
	}
	for name, index := range map[string]MongoIdx{
		"text":    {Name: "idx_text", Type: "text", Fields: []string{"title"}},
		"partial": {Name: "idx_partial", Keys: map[string]any{"status": 1}, PartialFilter: map[string]any{"status": "open"}},
	} {
		t.Run(name, func(t *testing.T) {
			if err := generateMongoStore(ctx, "items", CollectionDef{Entity: "Item", Indexes: []MongoIdx{index}}); err == nil {
				t.Fatal("generator silently accepted an index shape it cannot preserve")
			}
		})
	}
}

func TestFieldTypeToGoTypeResolvesSharedCompositeInsteadOfDegradingToString(t *testing.T) {
	t.Parallel()

	nested := newNestedCollector(&genContext{
		fields: &FieldsYAML{},
		sharedTypes: map[string]EntityFieldsDef{
			"TagHeatWindow": {
				Description: "标签的热度生效窗口。\n第二行说明不进注释。",
				Fields: []FieldDef{
					{Name: "startAt", Type: "timestamp"},
					{Name: "endAt", Type: "timestamp"},
					{Name: "recurrence", Type: "enum"},
				},
			},
		},
	})

	if got := fieldTypeToGoType(nested, "heatWindow", "TagHeatWindow", false); got != "*TagHeatWindow" {
		t.Fatalf("nullable composite mapped to %q, want *TagHeatWindow", got)
	}
	if got := fieldTypeToGoType(nested, "heatWindow", "TagHeatWindow", true); got != "TagHeatWindow" {
		t.Fatalf("non-null composite mapped to %q, want TagHeatWindow", got)
	}

	types, needsTime := nested.materialize()
	if len(types) != 1 {
		t.Fatalf("materialized %d composite types, want 1", len(types))
	}
	if !needsTime {
		t.Fatal("composite carrying a timestamp must pull in the time import")
	}
	if got, want := types[0].Description, "标签的热度生效窗口。"; got != want {
		t.Fatalf("description = %q, want %q", got, want)
	}
	if got, want := types[0].Fields[0].GoType, "time.Time"; got != want {
		t.Fatalf("startAt = %q, want %q", got, want)
	}
	if got, want := types[0].Fields[2].GoType, "string"; got != want {
		t.Fatalf("recurrence = %q, want %q", got, want)
	}
}

func TestNestedCollectorLeavesUnknownTypeToScalarFallback(t *testing.T) {
	t.Parallel()

	nested := newNestedCollector(&genContext{fields: &FieldsYAML{}})
	if got := fieldTypeToGoType(nested, "lifecycleStatus", "enum", false); got != "string" {
		t.Fatalf("enum mapped to %q, want string", got)
	}
	if types, _ := nested.materialize(); len(types) != 0 {
		t.Fatalf("materialized %d composite types, want 0", len(types))
	}
}

func TestFieldTypeToGoTypePreservesInt64ProjectionVersion(t *testing.T) {
	t.Parallel()

	if got := fieldTypeToGoType(
		nil,
		"sourceAggregateVersion",
		"int64",
		false,
	); got != "int64" {
		t.Fatalf("canonical int64 mapped to %q, want int64", got)
	}
}

func TestEntityHasFieldDoesNotInventCreatedAtForAppendOnlyFact(t *testing.T) {
	t.Parallel()

	ctx := &genContext{fields: &FieldsYAML{Entities: map[string]EntityFieldsDef{
		"DeletedPostTombstone": {Fields: []FieldDef{
			{Name: "deletedAt"},
			{Name: "expireAt"},
		}},
	}}}
	if entityHasField(ctx, "DeletedPostTombstone", "createdAt") {
		t.Fatal("Mongo codegen must not assign an undeclared createdAt field")
	}
}

func TestGenerationPlanIsDerivedFromObjectStorageContract(t *testing.T) {
	t.Parallel()

	serviceDir := filepath.Join(t.TempDir(), "sample-service")
	writeStorageTestFile(t, filepath.Join(serviceDir, "contracts", "domain.yaml"), "domain: sample\n")
	writeStorageTestFile(t, filepath.Join(serviceDir, "contracts", "catalog", "item_view", "storage.yaml"), `
backend: mongodb
role: projection
collections:
  items:
    entity: ItemView
codegen:
  enabled: true
`)

	plan, err := deriveGenerationPlan(serviceDir)
	if err != nil {
		t.Fatal(err)
	}
	if got, want := plan.Service, "sample-service"; got != want {
		t.Fatalf("service = %q, want %q", got, want)
	}
	if len(plan.Sources) != 1 {
		t.Fatalf("sources = %d, want 1", len(plan.Sources))
	}
	source := plan.Sources[0]
	if got, want := source.Metadata, "sample/catalog/item_view"; got != want {
		t.Fatalf("metadata = %q, want %q", got, want)
	}
	if got, want := source.ObjectPath, "catalog/item_view"; got != want {
		t.Fatalf("object path = %q, want %q", got, want)
	}
	if got, want := source.RootEntity, "ItemView"; got != want {
		t.Fatalf("root entity = %q, want %q", got, want)
	}
}

func TestObjectStorageCodegenRejectsDomainPathTraversal(t *testing.T) {
	t.Parallel()

	serviceDir := filepath.Join(t.TempDir(), "sample-service")
	writeStorageTestFile(t, filepath.Join(serviceDir, "contracts", "domain.yaml"), "domain: sample\n")
	writeStorageTestFile(t, filepath.Join(serviceDir, "contracts", "catalog", "item", "storage.yaml"), `
backend: postgres
role: authoritative
tables:
  items:
    entity: Item
codegen:
  enabled: true
  domain_path: ../../outside
`)
	if _, err := deriveGenerationPlan(serviceDir); err == nil {
		t.Fatal("domain_path traversal must be rejected")
	}
}

func TestPGStoreRejectsEntitylessBusinessTable(t *testing.T) {
	t.Parallel()

	ctx := &genContext{
		manifest: &Manifest{OutputDir: t.TempDir()},
		source: Source{
			DomainPkg: "user",
		},
	}
	err := generatePGStore(ctx, "greeting_request_outbox", TableDef{})
	if err == nil {
		t.Fatal("entityless table must not generate pg__store.g.go")
	}
}

func TestModelGenerationRejectsEntitylessBusinessTableBeforeWriting(t *testing.T) {
	t.Parallel()

	outputDir := t.TempDir()
	ctx := &genContext{
		manifest: &Manifest{OutputDir: outputDir},
		source: Source{
			DomainPkg: "user",
		},
		storage: &StorageYAML{
			Backend: "postgresql",
			Tables: map[string]TableDef{
				"greeting_request_outbox": {},
			},
		},
		fields: &FieldsYAML{},
	}
	if err := generateModels(ctx); err == nil {
		t.Fatal("entityless table must fail before model generation")
	}
	if _, err := os.Stat(filepath.Join(outputDir, "domain/user/model/.g.go")); !os.IsNotExist(err) {
		t.Fatalf("empty-name model must not be written, stat err=%v", err)
	}
}

func writeStorageTestFile(t *testing.T, path, content string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		t.Fatal(err)
	}
}
