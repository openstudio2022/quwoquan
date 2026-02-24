package testinfra

import (
	"context"
	"database/sql"
	"fmt"
	"os"
	"testing"

	embeddedpostgres "github.com/fergusstrange/embedded-postgres"
	"github.com/alicebob/miniredis/v2"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"github.com/testcontainers/testcontainers-go"
	mongomod "github.com/testcontainers/testcontainers-go/modules/mongodb"
)

// Suite holds all test database instances.
type Suite struct {
	PG      *sql.DB
	Mongo   *mongo.Database
	Redis   *miniredis.Miniredis
	pgEmbed *embeddedpostgres.EmbeddedPostgres
	mongoCl *mongo.Client
	mongoCt testcontainers.Container
}

// SuiteOption configures which databases to start.
type SuiteOption func(*suiteConfig)

type suiteConfig struct {
	pg    bool
	mongo bool
	redis bool
	pgPort uint32
	mongoDB string
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

// NewSuite starts the requested test databases. Call suite.TearDown() to stop.
func NewSuite(t *testing.T, opts ...SuiteOption) *Suite {
	t.Helper()

	cfg := &suiteConfig{
		pgPort:  15432,
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
		pgPort := cfg.pgPort
		pg := embeddedpostgres.NewDatabase(
			embeddedpostgres.DefaultConfig().
				Port(pgPort).
				DataPath(os.TempDir()+"/embedded-pg-data").
				RuntimePath(os.TempDir()+"/embedded-pg-runtime"),
		)
		if err := pg.Start(); err != nil {
			t.Fatalf("testinfra: start embedded postgres: %v", err)
		}
		s.pgEmbed = pg

		dsn := fmt.Sprintf("host=localhost port=%d user=postgres password=postgres dbname=postgres sslmode=disable", pgPort)
		db, err := sql.Open("postgres", dsn)
		if err != nil {
			pg.Stop()
			t.Fatalf("testinfra: connect postgres: %v", err)
		}
		s.PG = db
		t.Logf("testinfra: embedded postgres started on port %d", pgPort)
	}

	if cfg.mongo {
		mongoURI := os.Getenv("TEST_MONGO_URI")

		if mongoURI == "" {
			// Use testcontainers for isolated MongoDB
			ctx := context.Background()
			container, err := mongomod.Run(ctx,
				"mongo:7-jammy",
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

		client, err := mongo.Connect(options.Client().ApplyURI(mongoURI))
		if err != nil {
			s.TearDown(t)
			t.Fatalf("testinfra: connect mongo: %v", err)
		}
		s.mongoCl = client
		s.Mongo = client.Database(cfg.mongoDB)
	}

	return s
}

// TearDown stops all test databases.
func (s *Suite) TearDown(t *testing.T) {
	t.Helper()

	if s.PG != nil {
		s.PG.Close()
	}
	if s.pgEmbed != nil {
		if err := s.pgEmbed.Stop(); err != nil {
			t.Logf("testinfra: stop postgres: %v", err)
		}
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
