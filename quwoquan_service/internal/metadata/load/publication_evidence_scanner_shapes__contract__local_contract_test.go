package load

import (
	"os"
	"path/filepath"
	"testing"
)

func TestPublicationScannerResolvesCanonicalBlindspotShapes(t *testing.T) {
	t.Parallel()

	repoRoot := repositoryRootForTest(t)
	for name, expectation := range map[string]struct {
		service  string
		relation string
		writes   bool
		delivers bool
	}{
		"MediaUploadSession 两跳事务写入并装配 durable relay": {
			service:  "content-service",
			relation: "media_upload_session_outbox",
			writes:   true,
			delivers: true,
		},
		"Gathering 两跳事务写入并装配 durable relay": {
			service:  "circle-service",
			relation: "gathering_outbox",
			writes:   true,
			delivers: true,
		},
		"ExternalInteraction 使用实际装配的 shared reliabletaskmongo": {
			service:  "integration-service",
			relation: "external_interaction_result_outbox",
			writes:   true,
			delivers: true,
		},
		"Experiment 使用 import-qualified pgoutbox": {
			service:  "product-ops-service",
			relation: "product_ops_outbox",
			writes:   true,
			delivers: true,
		},
		"PremiumPoolEntry 使用 import-qualified pgoutbox": {
			service:  "product-ops-service",
			relation: "premium_pool_entry_outbox",
			writes:   true,
			delivers: true,
		},
		"RecommendationModelRelease 的 PyMongo 事务写入并装配 durable relay": {
			service:  "recommendation-service",
			relation: "rec_model_release_outbox",
			writes:   true,
			delivers: true,
		},
		"CallSession 对象 relay 由 production composition 装配": {
			service:  "rtc-service",
			relation: "call_session_outbox",
			writes:   true,
			delivers: true,
		},
	} {
		t.Run(name, func(t *testing.T) {
			t.Parallel()
			index, err := buildServiceWriteIndex(filepath.Join(
				repoRoot, "quwoquan_service", "services", expectation.service,
			))
			if err != nil {
				t.Fatalf("build write index: %v", err)
			}
			if _, ok := index.resolveTransactionalWrite(expectation.relation); ok != expectation.writes {
				t.Fatalf("write(%q)=%v, want %v", expectation.relation, ok, expectation.writes)
			}
			if _, ok := index.resolveDeliveryImplementation(expectation.relation); ok != expectation.delivers {
				t.Fatalf("delivery(%q)=%v, want %v", expectation.relation, ok, expectation.delivers)
			}
		})
	}
}

func TestPublicationScannerResolvesPlatformControlPlaneScopedOutbox(t *testing.T) {
	t.Parallel()

	repoRoot := repositoryRootForTest(t)
	index, err := buildServiceWriteIndex(filepath.Join(
		repoRoot, "quwoquan_service", "control-plane", "platform-ops",
	))
	if err != nil {
		t.Fatalf("build platform-ops write index: %v", err)
	}
	assertPublicationResolution(t, index, "platform_control_plane_outbox", true, true)
	assertPublicationResolution(t, index, "product_control_plane_outbox", false, false)
}

func TestGoPublicationScannerUsesBoundedCallAndRelationPropagation(t *testing.T) {
	t.Parallel()

	serviceRoot := filepath.Join(t.TempDir(), "quwoquan_service", "services", "sample-service")
	writePublicationTestSource(t, serviceRoot, "internal/store/store.go", `package store

type Context interface{}
type Database struct{}
type Collection struct{}
type Session struct{}
type Store struct { outbox *Collection; ordinary *Collection }

func (db *Database) Collection(name string) *Collection { return nil }
func (session *Session) WithTransaction(ctx Context, callback func(Context) (any, error)) (any, error) { return nil, nil }
func (collection *Collection) InsertOne(ctx Context, document any) (any, error) { return nil, nil }

func NewStore(db *Database) *Store {
    return &Store{
        outbox: db.Collection("two_hop_outbox"),
        ordinary: db.Collection("non_transactional_outbox"),
    }
}

func (store *Store) Commit(ctx Context, session *Session) error {
    _, err := session.WithTransaction(ctx, func(txCtx Context) (any, error) {
        return nil, store.writeOutbox(txCtx, store.outbox)
    })
    return err
}

func (store *Store) writeOutbox(ctx Context, collection *Collection) error {
    return appendOutbox(ctx, collection)
}

func appendOutbox(ctx Context, collection *Collection) error {
    _, err := collection.InsertOne(ctx, struct{}{})
    return err
}

func (store *Store) SaveOutsideTransaction(ctx Context) error {
    _, err := store.ordinary.InsertOne(ctx, struct{}{})
    return err
}

// TODO: session.WithTransaction(ctx, func(txCtx Context) { ghost.InsertOne(txCtx, "ghost_outbox") })
func diagnostic() error { return errors.New("ghost_outbox InsertOne WithTransaction") }
`)

	index, err := buildServiceWriteIndex(serviceRoot)
	if err != nil {
		t.Fatalf("build write index: %v", err)
	}
	assertPublicationResolution(t, index, "two_hop_outbox", true, false)
	assertPublicationResolution(t, index, "non_transactional_outbox", false, false)
	assertPublicationResolution(t, index, "ghost_outbox", false, false)
}

func TestGoPublicationScannerRequiresHandoffAndCmdComposition(t *testing.T) {
	t.Parallel()

	serviceRoot := filepath.Join(t.TempDir(), "quwoquan_service", "services", "sample-service")
	writePublicationTestSource(t, serviceRoot, "internal/demo/object/infrastructure/persistence/store.go", `package persistence

type Context interface{}
type Database struct{}
type Collection struct{}
type Session struct{}
type Store struct { outbox *Collection }

func (db *Database) Collection(name string) *Collection { return nil }
func (session *Session) WithTransaction(ctx Context, callback func(Context) (any, error)) (any, error) { return nil, nil }
func (collection *Collection) InsertOne(ctx Context, document any) (any, error) { return nil, nil }
func (collection *Collection) FindOneAndUpdate(ctx Context, filter any, update any) (any, error) { return nil, nil }
func (collection *Collection) UpdateOne(ctx Context, filter any, update any) (any, error) { return nil, nil }

func NewStore(db *Database) *Store { return &Store{outbox: db.Collection("composed_outbox")} }

func (store *Store) Commit(ctx Context, session *Session) error {
    _, err := session.WithTransaction(ctx, func(txCtx Context) (any, error) {
        _, writeErr := store.outbox.InsertOne(txCtx, struct{}{})
        return nil, writeErr
    })
    return err
}

func (store *Store) ClaimPendingOutbox(ctx Context) (any, error) {
    return store.outbox.FindOneAndUpdate(ctx, nil, nil)
}

func (store *Store) MarkOutboxPublished(ctx Context) error {
    _, err := store.outbox.UpdateOne(ctx, nil, nil)
    return err
}
`)

	index, err := buildServiceWriteIndex(serviceRoot)
	if err != nil {
		t.Fatalf("build read/checkpoint index: %v", err)
	}
	assertPublicationResolution(t, index, "composed_outbox", true, false)

	writePublicationTestSource(t, serviceRoot, "internal/demo/object/application/outbox_relay.go", `package application

type Outbox interface {
    ClaimPendingOutbox(ctx any) (any, error)
    MarkOutboxPublished(ctx any) error
}
type Publisher interface { PublishEvent(ctx any, event any) error }
type OutboxRelay struct { outbox Outbox; publisher Publisher }

func NewOutboxRelay(outbox Outbox, publisher Publisher) *OutboxRelay {
    return &OutboxRelay{outbox: outbox, publisher: publisher}
}

func (relay *OutboxRelay) Drain(ctx any) error {
    event, err := relay.outbox.ClaimPendingOutbox(ctx)
    if err != nil { return err }
    if err := relay.publisher.PublishEvent(ctx, event); err != nil { return err }
    return relay.outbox.MarkOutboxPublished(ctx)
}
`)
	index, err = buildServiceWriteIndex(serviceRoot)
	if err != nil {
		t.Fatalf("build uncomposed relay index: %v", err)
	}
	assertPublicationResolution(t, index, "composed_outbox", true, false)

	writePublicationTestSource(t, serviceRoot, "cmd/api/main.go", `package main

import relay "quwoquan_service/services/sample-service/internal/demo/object/application"

func main() { _ = relay.NewOutboxRelay(nil, nil) }
`)
	index, err = buildServiceWriteIndex(serviceRoot)
	if err != nil {
		t.Fatalf("build composed relay index: %v", err)
	}
	assertPublicationResolution(t, index, "composed_outbox", true, true)
}

func TestGoPublicationScannerResolvesOnlyComposedScopedDynamicSQL(t *testing.T) {
	t.Parallel()

	sharedStore := `package persistence

import "fmt"

type Pool struct{}
type Tx struct{}
type PostgresStore struct { pool *Pool; scope string }

func (pool *Pool) BeginTx(ctx any, options any) (*Tx, error) { return nil, nil }
func (pool *Pool) Exec(ctx any, query string, arguments ...any) (any, error) { return nil, nil }
func (tx *Tx) Exec(ctx any, query string, arguments ...any) (any, error) { return nil, nil }

func NewPostgresStore(pool *Pool, scope string) *PostgresStore {
    return &PostgresStore{pool: pool, scope: scope}
}

func (store *PostgresStore) commitMutation(ctx any) error {
    tx, err := store.pool.BeginTx(ctx, nil)
    if err != nil { return err }
    outboxTable := store.mutationOutboxTable()
    query := fmt.Sprintf("INSERT INTO %s(event_id) VALUES ($1)", outboxTable)
    _, err = tx.Exec(ctx, query, "event-1")
    return err
}

func (store *PostgresStore) mutationOutboxTable() string {
    switch store.scope {
    case "product-ops":
        return "product_control_plane_outbox"
    case "platform-ops":
        return "platform_control_plane_outbox"
    default:
        return "generic_control_plane_outbox"
    }
}

func (store *PostgresStore) diagnosticTable() string {
    switch store.scope {
    case "platform-ops":
        return "format_only_outbox"
    }
    return "diagnostic_fallback_outbox"
}

func (store *PostgresStore) diagnostic(ctx any) error {
    tx, err := store.pool.BeginTx(ctx, nil)
    if err != nil { return err }
    table := store.diagnosticTable()
    query := fmt.Sprintf("selected relation: %s", table)
    _, err = tx.Exec(ctx, query)
    return err
}

func (store *PostgresStore) nonTransactionalTable() string {
    switch store.scope {
    case "platform-ops":
        return "non_transactional_outbox"
    }
    return "non_transactional_fallback_outbox"
}

func (store *PostgresStore) writeWithoutTransaction(ctx any) error {
    table := store.nonTransactionalTable()
    query := fmt.Sprintf("INSERT INTO %s(event_id) VALUES ($1)", table)
    _, err := store.pool.Exec(ctx, query, "event-1")
    return err
}

// TODO: tx.Exec(ctx, fmt.Sprintf("INSERT INTO %s", "comment_only_outbox"))
func diagnosticText() string {
    return "platform-ops platform_control_plane_outbox BeginTx fmt.Sprintf Exec"
}
`

	for _, subject := range []struct {
		name       string
		scope      string
		decoyScope string
		written    string
		notWritten string
	}{
		{
			name:       "platform composition selects only platform relation",
			scope:      "platform-ops",
			decoyScope: "product-ops",
			written:    "platform_control_plane_outbox",
			notWritten: "product_control_plane_outbox",
		},
		{
			name:       "product composition selects only product relation",
			scope:      "product-ops",
			decoyScope: "platform-ops",
			written:    "product_control_plane_outbox",
			notWritten: "platform_control_plane_outbox",
		},
	} {
		subject := subject
		t.Run(subject.name, func(t *testing.T) {
			t.Parallel()
			moduleRoot := filepath.Join(t.TempDir(), "quwoquan_service")
			serviceRoot := filepath.Join(moduleRoot, "services", "sample-service")
			writePublicationTestSource(t, serviceRoot, "cmd/api/main.go", `package main

import (
    persistence "quwoquan_service/internal/platform/controlplane/persistence"
    decoy "quwoquan_service/internal/platform/otherpersistence"
)

func compose(pool *persistence.Pool) {
    _ = persistence.NewPostgresStore(pool, "`+subject.scope+`")
    _ = decoy.NewPostgresStore(nil, "`+subject.decoyScope+`")
}
`)
			writePublicationTestSource(
				t,
				moduleRoot,
				"internal/platform/controlplane/persistence/postgres_store.go",
				sharedStore,
			)
			writePublicationTestSource(
				t,
				moduleRoot,
				"internal/platform/otherpersistence/store.go",
				`package otherpersistence
type Store struct{}
func NewPostgresStore(pool any, scope string) *Store { return &Store{} }
`,
			)

			index, err := buildServiceWriteIndex(serviceRoot)
			if err != nil {
				t.Fatalf("build write index: %v", err)
			}
			assertPublicationResolution(t, index, subject.written, true, false)
			assertPublicationResolution(t, index, subject.notWritten, false, false)
			assertPublicationResolution(t, index, "generic_control_plane_outbox", false, false)
			assertPublicationResolution(t, index, "format_only_outbox", false, false)
			assertPublicationResolution(t, index, "non_transactional_outbox", false, false)
			assertPublicationResolution(t, index, "comment_only_outbox", false, false)
		})
	}
}

func TestSharedAndPostgresCompositionRequireRealQualifiedCalls(t *testing.T) {
	t.Parallel()

	moduleRoot := filepath.Join(t.TempDir(), "quwoquan_service")
	serviceRoot := filepath.Join(moduleRoot, "services", "sample-service")
	writePublicationTestSource(t, serviceRoot, "cmd/api/main.go", `package main

import (
    fake "example.com/not-canonical"
    pg "quwoquan_service/internal/platform/pgoutbox"
    reliable "quwoquan_service/internal/platform/reliabletaskmongo"
)

func compose(db *Database, pool *Pool, publisher *Publisher) {
    _ = reliable.NewExternalInteraction(db)
    _, _ = pg.NewDispatcher(pool, publisher, "qualified_outbox")
    _, _ = fake.NewDispatcher(pool, publisher, "wrong_import_outbox")
}

// TODO: pg.NewDispatcher(pool, publisher, "comment_only_outbox")
func diagnostic() error { return errors.New("pgoutbox.NewDispatcher string_only_outbox") }
`)
	writePublicationTestSource(t, moduleRoot, "internal/platform/pgoutbox/dispatcher.go", `package pgoutbox
func NewDispatcher(pool *Pool, publisher *Publisher, relation string) (*Dispatcher, error) { return nil, nil }
`)
	writePublicationTestSource(t, moduleRoot, "internal/platform/reliabletaskmongo/store.go", `package reliabletaskmongo

type Context interface{}
type Database struct{}
type Collection struct{}
type Session struct{}
type Store struct { outbox *Collection; session *Session }

func (db *Database) Collection(name string) *Collection { return nil }
func (collection *Collection) InsertOne(ctx Context, document any) (any, error) { return nil, nil }
func (collection *Collection) FindOneAndUpdate(ctx Context, filter any, update any) *Result { return nil }
func (session *Session) WithTransaction(ctx Context, callback func(Context) (any, error)) (any, error) { return nil, nil }

func NewExternalInteraction(db *Database) *Store {
    return &Store{outbox: db.Collection("shared_result_outbox"), session: &Session{}}
}

func (store *Store) Record(ctx Context) error {
    _, err := store.session.WithTransaction(ctx, func(txCtx Context) (any, error) {
        _, writeErr := store.outbox.InsertOne(txCtx, struct{}{})
        return nil, writeErr
    })
    return err
}

func (store *Store) Lease(ctx Context) { store.outbox.FindOneAndUpdate(ctx, nil, nil) }
`)

	index, err := buildServiceWriteIndex(serviceRoot)
	if err != nil {
		t.Fatalf("build write index: %v", err)
	}
	assertPublicationResolution(t, index, "shared_result_outbox", true, true)
	assertPublicationResolution(t, index, "qualified_outbox", false, true)
	assertPublicationResolution(t, index, "wrong_import_outbox", false, false)
	assertPublicationResolution(t, index, "comment_only_outbox", false, false)
	assertPublicationResolution(t, index, "string_only_outbox", false, false)
}

func TestPythonPublicationScannerRequiresPyMongoTransactionStructure(t *testing.T) {
	t.Parallel()

	serviceRoot := filepath.Join(t.TempDir(), "quwoquan_service", "services", "sample-service")
	writePublicationTestSource(t, serviceRoot, "internal/model/store.py", `
class Store:
    def __init__(self, database):
        self._database = database
        self._outbox = database["python_transactional_outbox"]
        self._ordinary = database["python_non_transactional_outbox"]

    def _insert_outbox(self, *, session):
        self._outbox.insert_one({"event": "created"}, session=session)

    def _run_transaction(self, callback):
        return self._database.client.start_session().with_transaction(callback)

    def execute(self):
        def transaction(session):
            self._insert_outbox(session=session)
        return self._run_transaction(transaction)

    def save_without_transaction(self):
        self._ordinary.insert_one({"event": "not-atomic"})

    # TODO: self._ghost.insert_one({}, session=session)  # python_comment_outbox
    def diagnostic(self):
        raise RuntimeError("database['python_string_outbox'].insert_one session=session")
`)

	index, err := buildServiceWriteIndex(serviceRoot)
	if err != nil {
		t.Fatalf("build write index: %v", err)
	}
	assertPublicationResolution(t, index, "python_transactional_outbox", true, false)
	assertPublicationResolution(t, index, "python_non_transactional_outbox", false, false)
	assertPublicationResolution(t, index, "python_comment_outbox", false, false)
	assertPublicationResolution(t, index, "python_string_outbox", false, false)
}

func TestPythonPublicationScannerRequiresHandoffAndCmdComposition(t *testing.T) {
	t.Parallel()

	serviceRoot := filepath.Join(t.TempDir(), "quwoquan_service", "services", "sample-service")
	writePublicationTestSource(t, serviceRoot, "internal/demo/object/infrastructure/store.py", `
class Store:
    def __init__(self, database):
        self._database = database
        self._outbox = database["python_composed_outbox"]

    def _insert(self, *, session):
        self._outbox.insert_one({"event": "created"}, session=session)

    def commit(self):
        def transaction(session):
            self._insert(session=session)
        return self._database.client.start_session().with_transaction(transaction)

    def claim_pending_outbox(self):
        return self._outbox.find_one_and_update({}, {"$set": {"claimed": True}})

    def mark_outbox_published(self):
        return self._outbox.update_one({}, {"$set": {"published": True}})
`)
	writePublicationTestSource(t, serviceRoot, "internal/demo/object/application/outbox_relay.py", `
class SampleOutboxRelay:
    def __init__(self, outbox, publisher):
        self._outbox = outbox
        self._publisher = publisher

    def drain(self):
        event = self._outbox.claim_pending_outbox()
        self._publisher.publish(event)
        self._outbox.mark_outbox_published()
`)

	index, err := buildServiceWriteIndex(serviceRoot)
	if err != nil {
		t.Fatalf("build uncomposed Python relay index: %v", err)
	}
	assertPublicationResolution(t, index, "python_composed_outbox", true, false)

	writePublicationTestSource(t, serviceRoot, "cmd/api/main.py", `
from quwoquan_service.services.sample_service.internal.demo.object.application.outbox_relay import SampleOutboxRelay

def compose(outbox, publisher):
    return SampleOutboxRelay(outbox, publisher)
`)
	index, err = buildServiceWriteIndex(serviceRoot)
	if err != nil {
		t.Fatalf("build composed Python relay index: %v", err)
	}
	assertPublicationResolution(t, index, "python_composed_outbox", true, true)
}

func assertPublicationResolution(
	t *testing.T,
	index *serviceWriteIndex,
	relation string,
	writes bool,
	delivers bool,
) {
	t.Helper()
	if _, ok := index.resolveTransactionalWrite(relation); ok != writes {
		t.Fatalf("write(%q)=%v, want %v", relation, ok, writes)
	}
	if _, ok := index.resolveDeliveryImplementation(relation); ok != delivers {
		t.Fatalf("delivery(%q)=%v, want %v", relation, ok, delivers)
	}
}

func writePublicationTestSource(t *testing.T, root string, relative string, source string) {
	t.Helper()
	path := filepath.Join(root, filepath.FromSlash(relative))
	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatalf("create source dir: %v", err)
	}
	if err := os.WriteFile(path, []byte(source), 0o600); err != nil {
		t.Fatalf("write source: %v", err)
	}
}
