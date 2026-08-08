package storagecontract

import (
	"os"
	"path/filepath"
	"testing"
)

func TestIndexAuditMatchesSemanticKeysRatherThanIndexNames(t *testing.T) {
	repo := t.TempDir()
	writeIndexAuditFixture(t, repo, "demo-service", "catalog", "item", `backend: mongodb
role: authoritative
collections:
  items:
    indexes:
      - name: authored_name_is_not_runtime_identity
        keys: {ownerId: 1, updatedAt: -1}
`, `package persistence
// The production name deliberately differs; semantic keys are the contract.
func ensureIndexes() { collection.Indexes().CreateOne(ctx, SetKeys("ownerId", "updatedAt")) }
func list() { collection.Find(ctx, map[string]any{"ownerId": owner}, SetSort("updatedAt")) }
`)
	report, err := AuditIndexes(repo)
	if err != nil {
		t.Fatal(err)
	}
	if report.Declarations != 1 || report.Created != 1 || report.Used != 1 || len(report.Issues) != 0 {
		t.Fatalf("report = %+v", report)
	}
}

func TestIndexAuditRejectsNameOnlyAndMissingQueryUse(t *testing.T) {
	repo := t.TempDir()
	writeIndexAuditFixture(t, repo, "demo-service", "catalog", "item", `backend: mongodb
role: authoritative
collections:
  items:
    indexes:
      - name: idx_owner_updated
        keys: {ownerId: 1, updatedAt: -1}
`, `package persistence
func ensureIndexes() { collection.Indexes().CreateOne(ctx, "idx_owner_updated") }
`)
	report, err := AuditIndexes(repo)
	if err != nil {
		t.Fatal(err)
	}
	if len(report.Issues) != 2 || report.Issues[0].Code != "CONTRACT.STORAGE.INDEX_CREATION_MISSING" || report.Issues[1].Code != "CONTRACT.STORAGE.INDEX_USAGE_MISSING" {
		t.Fatalf("issues = %+v", report.Issues)
	}
}

func TestIndexAuditDoesNotBorrowQueryMarkersFromAnotherFunction(t *testing.T) {
	repo := t.TempDir()
	writeIndexAuditFixture(t, repo, "demo-service", "catalog", "item", `backend: mongodb
role: authoritative
collections:
  items:
    indexes:
      - name: idx_owner_updated
        keys: {ownerId: 1, updatedAt: -1}
`, `package persistence
func ensureIndexes() { collection.Indexes().CreateOne(ctx, SetKeys("ownerId", "updatedAt")) }
func unrelatedQuery() { collection.Find(ctx, map[string]any{"ownerId": owner}) }
`)
	report, err := AuditIndexes(repo)
	if err != nil {
		t.Fatal(err)
	}
	if report.Created != 1 || report.Used != 0 || len(report.Issues) != 1 || report.Issues[0].Code != "CONTRACT.STORAGE.INDEX_USAGE_MISSING" {
		t.Fatalf("report = %+v", report)
	}
}

func TestIndexAuditDoesNotAssembleDeclaredKeysAcrossDifferentRuntimeIndexes(t *testing.T) {
	repo := t.TempDir()
	writeIndexAuditFixture(t, repo, "demo-service", "catalog", "item", `backend: mongodb
role: authoritative
collections:
  items:
    indexes:
      - name: authored_idx
        keys: {ownerId: 1, updatedAt: -1}
`, `package persistence
func ensureIndexes() {
  collection.Indexes().CreateMany(ctx, []mongo.IndexModel{
    {Keys: bson.D{{Key: "ownerId", Value: 1}, {Key: "status", Value: 1}}},
    {Keys: bson.D{{Key: "kind", Value: 1}, {Key: "updatedAt", Value: -1}}},
  })
}
func list() { collection.Find(ctx, map[string]any{"ownerId": owner}, SetSort("updatedAt")) }
`)
	report, err := AuditIndexes(repo)
	if err != nil {
		t.Fatal(err)
	}
	if report.Created != 0 || report.Used != 1 || len(report.Issues) != 1 || report.Issues[0].Code != "CONTRACT.STORAGE.INDEX_CREATION_MISSING" {
		t.Fatalf("report = %+v", report)
	}
}

func TestIndexAuditAcceptsCanonicalGeneratedMongoStoreOnlyWhenProductionWiresEnsureIndexes(t *testing.T) {
	repo := t.TempDir()
	writeIndexAuditFixture(t, repo, "demo-service", "catalog", "item", `backend: mongodb
role: authoritative
collections:
  items:
    indexes:
      - name: idx_owner_updated
        keys: {ownerId: 1, updatedAt: -1}
        unique: true
codegen:
  enabled: true
`, `package persistence
import generated "quwoquan_service/services/demo-service/generated/catalog/item/persistence/catalog/persistence"
type MongoItemStore struct { *generated.MongoItemStoreBase }
func NewMongoItemStore() *MongoItemStore {
  return &MongoItemStore{MongoItemStoreBase: generated.NewMongoItemStoreBase(nil)}
}
`)
	cmdDir := filepath.Join(repo, "quwoquan_service", "services", "demo-service", "cmd", "api")
	if err := os.MkdirAll(cmdDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(cmdDir, "main.go"), []byte(`package main
func main() {
  store := persistence.NewMongoItemStore()
  _ = store.EnsureIndexes(ctx)
}
`), 0o600); err != nil {
		t.Fatal(err)
	}
	report, err := AuditIndexes(repo)
	if err != nil {
		t.Fatal(err)
	}
	if report.Created != 1 || report.Used != 1 || len(report.Issues) != 0 {
		t.Fatalf("report = %+v", report)
	}

	if err := os.WriteFile(filepath.Join(cmdDir, "main.go"), []byte(`package main
func main() { _ = persistence.NewMongoItemStore() }
`), 0o600); err != nil {
		t.Fatal(err)
	}
	report, err = AuditIndexes(repo)
	if err != nil {
		t.Fatal(err)
	}
	if report.Created != 0 || len(report.Issues) != 1 || report.Issues[0].Code != "CONTRACT.STORAGE.INDEX_CREATION_MISSING" {
		t.Fatalf("unwired report = %+v", report)
	}
}

func TestIndexAuditAcceptsSQLAndPythonCreationForms(t *testing.T) {
	for name, source := range map[string]string{
		"sql":    `CREATE INDEX runtime_idx ON records (owner_id, updated_at); SELECT id FROM records WHERE owner_id = $1 ORDER BY updated_at;`,
		"python": `collection.create_index([("ownerId", 1), ("updatedAt", -1)], name="runtime_idx")\ncollection.find({"ownerId": actor}).sort("updatedAt")`,
	} {
		t.Run(name, func(t *testing.T) {
			repo := t.TempDir()
			storage := `backend: mongodb
role: authoritative
collections:
  records:
    indexes:
      - name: authored_idx
        keys: {ownerId: 1, updatedAt: -1}
`
			if name == "sql" {
				storage = `backend: postgres
role: authoritative
tables:
  records:
    indexes:
      - name: authored_idx
        columns: [owner_id, updated_at]
`
			}
			writeIndexAuditFixture(t, repo, "demo-service", "catalog", "item", storage, source)
			report, err := AuditIndexes(repo)
			if err != nil {
				t.Fatal(err)
			}
			if report.Created != 1 || report.Used != 1 || len(report.Issues) != 0 {
				t.Fatalf("report = %+v", report)
			}
		})
	}
}

func TestIndexAuditRecognizesPythonFindOneAsAReadPurpose(t *testing.T) {
	repo := t.TempDir()
	writeIndexAuditFixture(t, repo, "demo-service", "catalog", "item", `backend: mongodb
role: authoritative
collections:
  records:
    indexes:
      - name: authored_idx
        keys: {requestId: 1, targetId: 1, exposedAt: -1}
`, `collection.create_index([("requestId", 1), ("targetId", 1), ("exposedAt", -1)], name="runtime_idx")
def latest(request_id, target_id):
    return collection.find_one(
        {"requestId": request_id, "targetId": target_id},
        sort=[("exposedAt", -1)],
    )
`)
	report, err := AuditIndexes(repo)
	if err != nil {
		t.Fatal(err)
	}
	if report.Created != 1 || report.Used != 1 || len(report.Issues) != 0 {
		t.Fatalf("report = %+v", report)
	}
}

func TestIndexAuditTreatsUniqueConstraintAsExplicitPurpose(t *testing.T) {
	repo := t.TempDir()
	writeIndexAuditFixture(t, repo, "demo-service", "catalog", "item", `backend: postgres
role: authoritative
tables:
  records:
    unique_constraints:
      - name: uq_records_owner
        columns: [owner_id]
`, `CREATE UNIQUE INDEX runtime_unique ON records (owner_id);`)
	report, err := AuditIndexes(repo)
	if err != nil {
		t.Fatal(err)
	}
	if report.Created != 1 || report.Used != 1 || len(report.Issues) != 0 {
		t.Fatalf("report = %+v", report)
	}
}

func TestIndexAuditRecognizesCompositePrimaryKeyAsCreation(t *testing.T) {
	repo := t.TempDir()
	writeIndexAuditFixture(t, repo, "demo-service", "catalog", "item", `backend: postgres
role: authoritative
tables:
  directions:
    unique_constraints:
      - name: uq_direction
        columns: [pair_id, source_id]
`, `CREATE TABLE directions (
  pair_id TEXT NOT NULL,
  source_id TEXT NOT NULL,
  PRIMARY KEY (pair_id, source_id)
);`)
	report, err := AuditIndexes(repo)
	if err != nil {
		t.Fatal(err)
	}
	if report.Created != 1 || report.Used != 1 || len(report.Issues) != 0 {
		t.Fatalf("report = %+v", report)
	}
}

func TestIndexAuditRecognizesMongoAutomaticIDIndex(t *testing.T) {
	repo := t.TempDir()
	writeIndexAuditFixture(t, repo, "demo-service", "catalog", "item", `backend: mongodb
role: authoritative
collections:
  watermarks:
    indexes:
      - name: authored_identity_name
        keys: {_id: 1}
        unique: true
`, `package persistence`)
	report, err := AuditIndexes(repo)
	if err != nil {
		t.Fatal(err)
	}
	if report.Created != 1 || report.Used != 1 || len(report.Issues) != 0 {
		t.Fatalf("report = %+v", report)
	}
}

func TestIndexAuditFollowsGoSQLConstantIntoSchemaAndQueryScopes(t *testing.T) {
	repo := t.TempDir()
	writeIndexAuditFixture(t, repo, "demo-service", "catalog", "item", `backend: postgres
role: authoritative
tables:
  records:
    indexes:
      - name: authored_idx
        columns: [owner_id, updated_at]
`, "package persistence\n"+"const schema = `CREATE INDEX runtime_idx ON records(owner_id, updated_at)`\n"+
		"func ensure() { pool.Exec(ctx, schema) }\n"+
		"func list() { pool.Query(ctx, `SELECT id FROM records WHERE owner_id=$1 ORDER BY updated_at`) }\n")
	report, err := AuditIndexes(repo)
	if err != nil {
		t.Fatal(err)
	}
	if report.Created != 1 || report.Used != 1 || len(report.Issues) != 0 {
		t.Fatalf("report = %+v", report)
	}
}

func TestIndexAuditFollowsPostgresColumnHardCutoverIntoExistingIndex(t *testing.T) {
	repo := t.TempDir()
	writeIndexAuditFixture(t, repo, "demo-service", "catalog", "item", `backend: postgres
role: authoritative
tables:
  records:
    indexes:
      - name: canonical_idx
        columns: [owner_persona_id, updated_at]
`, `CREATE INDEX historical_idx ON records(previous_owner_id, updated_at);
ALTER TABLE records RENAME COLUMN previous_owner_id TO owner_persona_id;
SELECT id FROM records WHERE owner_persona_id = $1 ORDER BY updated_at;
`)
	report, err := AuditIndexes(repo)
	if err != nil {
		t.Fatal(err)
	}
	if report.Created != 1 || report.Used != 1 || len(report.Issues) != 0 {
		t.Fatalf("report = %+v", report)
	}
}

func TestIndexAuditFollowsSharedRuntimeCollectionBindingBySemanticStoreName(t *testing.T) {
	repo := t.TempDir()
	writeIndexAuditFixture(t, repo, "demo-service", "catalog", "item", `backend: mongodb
role: authoritative
collections:
  reliable_task_outbox:
    indexes:
      - name: authored_idx
        keys: {startAt: 1, status: 1}
`, `package persistence`)
	sharedDir := filepath.Join(repo, "quwoquan_service", "internal", "platform", "reliabletaskmongo")
	if err := os.MkdirAll(sharedDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(sharedDir, "store.go"), []byte(`package reliabletaskmongo
func newStore(db *Database) *Store {
  return &Store{outboxes: db.Collection("reliable_task_outbox")}
}

func (store *Store) EnsureIndexes() {
  store.outboxes.Indexes().CreateOne(ctx, IndexModel{Keys: D{{Key: "startAt"}, {Key: "status"}}})
}
func (store *Store) claim() {
  store.outboxes.Find(ctx, M{"status": "pending"}, SetSort(D{{Key: "startAt"}}))
}
`), 0o600); err != nil {
		t.Fatal(err)
	}
	report, err := AuditIndexes(repo)
	if err != nil {
		t.Fatal(err)
	}
	if report.Created != 1 || report.Used != 1 || len(report.Issues) != 0 {
		t.Fatalf("report = %+v", report)
	}
}

func TestIndexAuditPreservesNestedElemMatchFieldIdentity(t *testing.T) {
	repo := t.TempDir()
	writeIndexAuditFixture(t, repo, "demo-service", "catalog", "item", `backend: mongodb
role: authoritative
collections:
  items:
    indexes:
      - name: idx_nested_owner_page
        keys: {participants.owner.id: 1, participants.state: 1, updatedAt: -1}
`, `package persistence
func ensureIndexes() {
  collection.Indexes().CreateOne(ctx, mongo.IndexModel{Keys: bson.D{
    {Key: "participants.owner.id", Value: 1},
    {Key: "participants.state", Value: 1},
    {Key: "updatedAt", Value: -1},
  }})
}
func list() {
  filter := bson.M{"participants": bson.M{"$elemMatch": bson.M{
    "owner.id": ownerID,
    "state": "active",
  }}}
  collection.Find(ctx, filter, options.Find().SetSort(bson.D{{Key: "updatedAt", Value: -1}}))
}
`)
	report, err := AuditIndexes(repo)
	if err != nil {
		t.Fatal(err)
	}
	if report.Created != 1 || report.Used != 1 || len(report.Issues) != 0 {
		t.Fatalf("report = %+v", report)
	}
}

func writeIndexAuditFixture(t *testing.T, repo, service, context, object, storage, production string) {
	t.Helper()
	contractDir := filepath.Join(repo, "quwoquan_service", "services", service, "contracts", context, object)
	implementationDir := filepath.Join(repo, "quwoquan_service", "services", service, "internal", context, object, "infrastructure")
	if err := os.MkdirAll(contractDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(implementationDir, 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(contractDir, "storage.yaml"), []byte(storage), 0o600); err != nil {
		t.Fatal(err)
	}
	extension := ".go"
	if len(production) >= 6 && production[:6] == "CREATE" {
		extension = ".sql"
	} else if len(production) >= 10 && production[:10] == "collection" {
		extension = ".py"
	}
	if err := os.WriteFile(filepath.Join(implementationDir, "storage"+extension), []byte(production), 0o600); err != nil {
		t.Fatal(err)
	}
}
