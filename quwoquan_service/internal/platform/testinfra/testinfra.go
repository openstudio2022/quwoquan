package testinfra

import (
	"context"
	"database/sql"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"sync"
	"testing"

	"github.com/alicebob/miniredis/v2"
	embeddedpostgres "github.com/fergusstrange/embedded-postgres"
	_ "github.com/lib/pq"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"github.com/testcontainers/testcontainers-go"
	mongomod "github.com/testcontainers/testcontainers-go/modules/mongodb"
)

const StableEmbeddedPostgresVersion = embeddedpostgres.PostgresVersion("16.2.0")

// Suite holds all test database instances.
type Suite struct {
	PG      *sql.DB
	Mongo   *mongo.Database
	Redis   *miniredis.Miniredis
	pgEmbed *embeddedpostgres.EmbeddedPostgres
	pgOwned bool
	pgDone  func()
	done    sync.Once
	mongoCl *mongo.Client
	mongoCt testcontainers.Container
}

// SuiteOption configures which databases to start.
type SuiteOption func(*suiteConfig)

type suiteConfig struct {
	pg        bool
	mongo     bool
	redis     bool
	pgPort    uint32
	pgFixture *PostgresFixture
	mongoDB   string
}

// PostgresFixture owns one real embedded PostgreSQL process that can be reused
// by a package-level TestMain. Each borrowed Suite holds the fixture mutex until
// TearDown, so schema cleanup and test execution remain deterministic.
type PostgresFixture struct {
	DB       *sql.DB
	server   *embeddedpostgres.EmbeddedPostgres
	root     string
	mu       sync.Mutex
	closeMu  sync.Once
	closeErr error
}

func WithPostgres() SuiteOption {
	return func(c *suiteConfig) { c.pg = true }
}

func WithMongo(dbName string) SuiteOption {
	return func(c *suiteConfig) { c.mongo = true; c.mongoDB = dbName }
}

func WithRedis() SuiteOption {
	return func(c *suiteConfig) { c.redis = true }
}

func WithPGPort(port uint32) SuiteOption {
	return func(c *suiteConfig) { c.pgPort = port }
}

// WithPostgresFixture borrows a package-level real PostgreSQL fixture instead
// of starting a new database process for every test case.
func WithPostgresFixture(fixture *PostgresFixture) SuiteOption {
	return func(c *suiteConfig) {
		c.pg = true
		c.pgFixture = fixture
	}
}

// StartPostgresFixture starts one explicitly-owned embedded PostgreSQL process.
// The caller must invoke Close after the package test run.
func StartPostgresFixture(root string, port uint32) (*PostgresFixture, error) {
	if root == "" {
		return nil, fmt.Errorf("testinfra: postgres fixture root is required")
	}
	if port == 0 {
		var err error
		port, err = reservePostgresPort()
		if err != nil {
			return nil, err
		}
	}
	if err := os.MkdirAll(root, 0o700); err != nil {
		return nil, fmt.Errorf("testinfra: create postgres fixture root: %w", err)
	}
	server := embeddedpostgres.NewDatabase(
		embeddedpostgres.DefaultConfig().
			Version(StableEmbeddedPostgresVersion).
			Port(port).
			DataPath(filepath.Join(root, "data")).
			RuntimePath(filepath.Join(root, "runtime")),
	)
	if err := server.Start(); err != nil {
		return nil, fmt.Errorf("testinfra: start embedded postgres: %w", err)
	}
	dsn := fmt.Sprintf(
		"host=localhost port=%d user=postgres password=postgres dbname=postgres sslmode=disable",
		port,
	)
	db, err := sql.Open("postgres", dsn)
	if err != nil {
		_ = server.Stop()
		return nil, fmt.Errorf("testinfra: connect postgres: %w", err)
	}
	if err := db.Ping(); err != nil {
		_ = db.Close()
		_ = server.Stop()
		return nil, fmt.Errorf("testinfra: ping postgres: %w", err)
	}
	return &PostgresFixture{DB: db, server: server, root: root}, nil
}

// Close releases the shared database and its temporary runtime directory.
func (f *PostgresFixture) Close() error {
	if f == nil {
		return nil
	}
	f.closeMu.Do(func() {
		if f.DB != nil {
			if err := f.DB.Close(); err != nil {
				f.closeErr = err
			}
		}
		if f.server != nil {
			if err := f.server.Stop(); err != nil && f.closeErr == nil {
				f.closeErr = err
			}
		}
		if err := os.RemoveAll(f.root); err != nil && f.closeErr == nil {
			f.closeErr = err
		}
	})
	return f.closeErr
}

// NewSuite starts the requested test databases. Call suite.TearDown() to stop.
func NewSuite(t *testing.T, opts ...SuiteOption) *Suite {
	t.Helper()

	cfg := &suiteConfig{
		mongoDB: "test_db",
	}
	for _, o := range opts {
		o(cfg)
	}

	s := &Suite{}

	if cfg.redis {
		mr := miniredis.RunT(t)
		s.Redis = mr
		t.Logf("testinfra: miniredis started at %s", mr.Addr())
	}

	if cfg.pg {
		if cfg.pgFixture != nil {
			if cfg.pgFixture.DB == nil {
				t.Fatal("testinfra: postgres fixture is not started")
			}
			cfg.pgFixture.mu.Lock()
			s.PG = cfg.pgFixture.DB
			s.pgDone = cfg.pgFixture.mu.Unlock
			t.Cleanup(func() { s.TearDown(t) })
			s.CleanPG(t)
		} else {
			pgPort := cfg.pgPort
			if pgPort == 0 {
				var err error
				pgPort, err = reservePostgresPort()
				if err != nil {
					t.Fatal(err)
				}
			}
			pgRoot := t.TempDir()
			pg := embeddedpostgres.NewDatabase(
				embeddedpostgres.DefaultConfig().
					Version(StableEmbeddedPostgresVersion).
					Port(pgPort).
					DataPath(filepath.Join(pgRoot, "data")).
					RuntimePath(filepath.Join(pgRoot, "runtime")),
			)
			if err := pg.Start(); err != nil {
				t.Fatalf("testinfra: start embedded postgres: %v", err)
			}
			s.pgEmbed = pg
			s.pgOwned = true

			dsn := fmt.Sprintf("host=localhost port=%d user=postgres password=postgres dbname=postgres sslmode=disable", pgPort)
			db, err := sql.Open("postgres", dsn)
			if err != nil {
				pg.Stop()
				t.Fatalf("testinfra: connect postgres: %v", err)
			}
			s.PG = db
			t.Logf("testinfra: embedded postgres started on port %d", pgPort)
		}
	}

	if cfg.mongo {
		mongoURI := os.Getenv("TEST_MONGO_URI")

		if mongoURI == "" {
			// Use testcontainers for isolated MongoDB
			ctx := context.Background()
			container, err := mongomod.Run(ctx,
				"mongo:7-jammy",
				mongomod.WithReplicaSet(mongoReplicaSetName),
				testcontainers.WithEnv(map[string]string{
					"MONGO_INITDB_DATABASE": cfg.mongoDB,
				}),
			)
			if err != nil {
				s.TearDown(t)
				t.Fatalf("testinfra: start mongo testcontainer: %v", err)
			}
			s.mongoCt = container

			uri, err := container.ConnectionString(ctx)
			if err != nil {
				s.TearDown(t)
				t.Fatalf("testinfra: mongo connection string: %v", err)
			}
			mongoURI = uri
			t.Logf("testinfra: mongo testcontainer started at %s", mongoURI)
		} else {
			t.Logf("testinfra: mongo connecting to external %s", mongoURI)
		}

		clientOptions := options.Client().ApplyURI(mongoURI)
		if s.mongoCt != nil {
			clientOptions.SetDirect(true)
		}
		client, err := mongo.Connect(clientOptions)
		if err != nil {
			s.TearDown(t)
			t.Fatalf("testinfra: connect mongo: %v", err)
		}
		s.mongoCl = client
		s.Mongo = client.Database(cfg.mongoDB)
	}

	return s
}

// reservePostgresPort provides a per-suite port. The listener is closed before
// embedded Postgres binds it, so callers that require a fixed port can still
// use WithPGPort explicitly.
func reservePostgresPort() (uint32, error) {
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return 0, fmt.Errorf("testinfra: reserve postgres port: %w", err)
	}
	defer listener.Close()

	address, ok := listener.Addr().(*net.TCPAddr)
	if !ok || address.Port <= 0 {
		return 0, fmt.Errorf(
			"testinfra: reserve postgres port returned invalid address %v",
			listener.Addr(),
		)
	}
	return uint32(address.Port), nil
}

// TearDown stops all test databases.
func (s *Suite) TearDown(t *testing.T) {
	t.Helper()
	s.done.Do(func() {
		if s.pgOwned && s.PG != nil {
			_ = s.PG.Close()
		}
		if s.pgOwned && s.pgEmbed != nil {
			if err := s.pgEmbed.Stop(); err != nil {
				t.Logf("testinfra: stop postgres: %v", err)
			}
		}
		if s.pgDone != nil {
			s.pgDone()
		}
		if s.mongoCl != nil {
			if err := s.mongoCl.Disconnect(context.Background()); err != nil {
				t.Logf("testinfra: disconnect mongo: %v", err)
			}
		}
		if s.mongoCt != nil {
			if err := s.mongoCt.Terminate(context.Background()); err != nil {
				t.Logf("testinfra: terminate mongo container: %v", err)
			}
		}
	})
}

// CleanPG truncates all tables in the public schema.
func (s *Suite) CleanPG(t *testing.T) {
	t.Helper()
	if s.PG == nil {
		return
	}
	_, err := s.PG.Exec(`
		DO $$ 
		DECLARE r RECORD;
		BEGIN
			FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
				EXECUTE 'TRUNCATE TABLE ' || quote_ident(r.tablename) || ' CASCADE';
			END LOOP;
		END $$;
	`)
	if err != nil {
		t.Fatalf("testinfra: clean pg: %v", err)
	}
}

// CleanMongo drops all collections in the test database.
func (s *Suite) CleanMongo(t *testing.T) {
	t.Helper()
	if s.Mongo == nil {
		return
	}
	if err := s.Mongo.Drop(context.Background()); err != nil {
		t.Fatalf("testinfra: clean mongo: %v", err)
	}
}

// CleanRedis flushes all Redis data.
func (s *Suite) CleanRedis(t *testing.T) {
	t.Helper()
	if s.Redis == nil {
		return
	}
	s.Redis.FlushAll()
}

// CleanAll resets all databases.
func (s *Suite) CleanAll(t *testing.T) {
	t.Helper()
	s.CleanPG(t)
	s.CleanMongo(t)
	s.CleanRedis(t)
}
