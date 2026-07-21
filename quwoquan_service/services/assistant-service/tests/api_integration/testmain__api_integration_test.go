package api_integration

import (
	"context"
	"fmt"
	"os"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/testcontainers/testcontainers-go"
	mongomod "github.com/testcontainers/testcontainers-go/modules/mongodb"
	"github.com/testcontainers/testcontainers-go/wait"
	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	mongoopts "go.mongodb.org/mongo-driver/v2/mongo/options"

	platformredis "quwoquan_service/internal/platform/redis"
	"quwoquan_service/internal/platform/testinfra"
	runtimemessaging "quwoquan_service/runtime/messaging"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/assistant-service/internal/application"
	preferencefact "quwoquan_service/services/assistant-service/internal/application/assistant/preference_fact"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
	preferencepersistence "quwoquan_service/services/assistant-service/internal/infrastructure/assistant/preference_fact/persistence"
	"quwoquan_service/services/assistant-service/internal/infrastructure/messaging"
	"quwoquan_service/services/assistant-service/internal/infrastructure/persistence"
	"quwoquan_service/services/assistant-service/internal/infrastructure/projection"
)

var (
	integrationMongoDB              *mongo.Database
	integrationMongoClient          *mongo.Client
	integrationMongoContainer       *mongomod.MongoDBContainer
	integrationPostgresPool         *pgxpool.Pool
	integrationPostgresContainer    testcontainers.Container
	integrationRedisServer          *testinfra.RealRedis
	integrationRedisRouter          *rtredis.Router
	integrationRedisClient          rtredis.Client
	integrationEventStore           *persistence.MongoEventStore
	integrationConsentStore         *persistence.PgConsentStore
	integrationProfileStore         *projection.LearningProfileStore
	integrationSubscriptionStore    *persistence.MongoSkillSubscriptionStore
	integrationConversationRunStore *persistence.MongoConversationRunStore
	integrationPreferenceStore      *preferencepersistence.MongoStore
)

func TestMain(m *testing.M) {
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)

	testinfra.ConfigureLocalContainerRuntime()
	startIntegrationRedis(ctx)
	startIntegrationMongo(ctx)
	startIntegrationPostgres(ctx)
	initializeIntegrationStores(ctx)
	cancel()

	code := m.Run()

	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 45*time.Second)
	stopIntegrationDependencies(shutdownCtx)
	shutdownCancel()
	os.Exit(code)
}

func startIntegrationRedis(ctx context.Context) {
	var err error
	integrationRedisServer, err = testinfra.StartRealRedis(ctx)
	if err != nil {
		panic("assistant-service api_integration requires real Redis: " + err.Error())
	}
	if err := integrationRedisServer.FlushDBs(ctx, 0, 1, 2); err != nil {
		panic("assistant-service api_integration flush Redis: " + err.Error())
	}
	integrationRedisRouter, err = platformredis.NewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"general": {
				Mode:     "standalone",
				Addr:     integrationRedisServer.Addr,
				Password: integrationRedisServer.Password,
				DB:       1,
				TLS:      integrationRedisServer.TLS,
			},
			"rec": {
				Mode:     "standalone",
				Addr:     integrationRedisServer.Addr,
				Password: integrationRedisServer.Password,
				DB:       0,
				TLS:      integrationRedisServer.TLS,
			},
			"realtime": {
				Mode:     "standalone",
				Addr:     integrationRedisServer.Addr,
				Password: integrationRedisServer.Password,
				DB:       2,
				TLS:      integrationRedisServer.TLS,
			},
		},
		PrefixRoutes: rtredis.GeneratedPrefixRoutes(),
		DefaultScene: rtredis.GeneratedDefaultScene,
	})
	if err != nil {
		panic("assistant-service api_integration create Redis router: " + err.Error())
	}
	integrationRedisClient = integrationRedisRouter.Scene("general")
	if err := integrationRedisRouter.PingAll(context.Background()); err != nil {
		panic("assistant-service api_integration ping Redis: " + err.Error())
	}
}

func startIntegrationMongo(ctx context.Context) {
	mongoURI := strings.TrimSpace(os.Getenv("QWQ_TEST_MONGO_URI"))
	if mongoURI == "" {
		mongoURI = strings.TrimSpace(os.Getenv("TEST_MONGO_URI"))
	}
	if mongoURI == "" {
		container, err := runIntegrationMongoContainer(ctx)
		if err != nil {
			panic(
				"assistant-service api_integration requires a real MongoDB; " +
					"set QWQ_TEST_MONGO_URI/TEST_MONGO_URI or start Docker: " + err.Error(),
			)
		}
		integrationMongoContainer = container
		mongoURI, err = container.ConnectionString(ctx)
		if err != nil {
			panic("assistant-service api_integration get MongoDB connection string: " + err.Error())
		}
	}

	var err error
	mongoClientOptions := mongoopts.Client().
		ApplyURI(mongoURI).
		SetServerSelectionTimeout(15 * time.Second)
	if integrationMongoContainer != nil {
		mongoClientOptions.SetDirect(true)
	}
	integrationMongoClient, err = mongo.Connect(mongoClientOptions)
	if err != nil {
		panic("assistant-service api_integration connect MongoDB: " + err.Error())
	}
	if err := integrationMongoClient.Ping(ctx, nil); err != nil {
		panic("assistant-service api_integration ping MongoDB: " + err.Error())
	}
	databaseName := "assistant_api_integration_" + strconv.Itoa(os.Getpid())
	integrationMongoDB = integrationMongoClient.Database(databaseName)
}

func startIntegrationPostgres(ctx context.Context) {
	postgresDSN := strings.TrimSpace(os.Getenv("QWQ_TEST_POSTGRES_DSN"))
	if postgresDSN == "" {
		postgresDSN = strings.TrimSpace(os.Getenv("TEST_PG_DSN"))
	}
	if postgresDSN == "" {
		container, dsn, err := runIntegrationPostgresContainer(ctx)
		if err != nil {
			panic(
				"assistant-service api_integration requires a real Postgres; " +
					"set QWQ_TEST_POSTGRES_DSN/TEST_PG_DSN or start Docker: " + err.Error(),
			)
		}
		integrationPostgresContainer = container
		postgresDSN = dsn
	}

	var err error
	integrationPostgresPool, err = pgxpool.New(ctx, postgresDSN)
	if err != nil {
		panic("assistant-service api_integration connect Postgres: " + err.Error())
	}
	if err := integrationPostgresPool.Ping(ctx); err != nil {
		panic("assistant-service api_integration ping Postgres: " + err.Error())
	}
}

func initializeIntegrationStores(ctx context.Context) {
	integrationEventStore = persistence.NewMongoEventStore(integrationMongoDB)
	if err := integrationEventStore.EnsureIndexes(ctx); err != nil {
		panic("assistant-service api_integration ensure event indexes: " + err.Error())
	}
	integrationProfileStore = projection.NewLearningProfileStore(integrationMongoDB)
	if err := integrationProfileStore.EnsureIndexes(ctx); err != nil {
		panic("assistant-service api_integration ensure profile indexes: " + err.Error())
	}
	integrationSubscriptionStore = persistence.NewMongoSkillSubscriptionStore(integrationMongoDB)
	if err := integrationSubscriptionStore.EnsureIndexes(ctx); err != nil {
		panic("assistant-service api_integration ensure subscription indexes: " + err.Error())
	}
	integrationConsentStore = persistence.NewPgConsentStore(integrationPostgresPool)
	if err := integrationConsentStore.EnsureSchema(ctx); err != nil {
		panic("assistant-service api_integration run Postgres migrations: " + err.Error())
	}
	integrationConversationRunStore = persistence.NewMongoConversationRunStore(integrationMongoDB)
	if err := integrationConversationRunStore.EnsureIndexes(ctx); err != nil {
		panic("assistant-service api_integration ensure conversation/run indexes: " + err.Error())
	}
	integrationPreferenceStore = preferencepersistence.NewMongoStore(integrationMongoDB)
	if err := integrationPreferenceStore.EnsureIndexes(ctx); err != nil {
		panic("assistant-service api_integration ensure preference indexes: " + err.Error())
	}
}

func newIntegrationAssistantService(opts ...application.AssistantServiceOption) *application.AssistantService {
	messageTransport := newIntegrationMessageTransport()
	baseOptions := []application.AssistantServiceOption{
		application.WithLearningProfileStore(integrationProfileStore),
		application.WithSkillSubscriptionStore(integrationSubscriptionStore),
		application.WithConversationRunStore(integrationConversationRunStore),
		application.WithPreferenceSnapshotReader(
			preferencefact.NewQueryFacade(integrationPreferenceStore),
		),
		application.WithEventPublisher(
			messaging.NewRedisEventPublisherWithTransport(
				messageTransport,
				"assistant-service-api-integration",
				nil,
			),
		),
	}
	baseOptions = append(baseOptions, opts...)
	return application.NewAssistantService(
		integrationEventStore,
		integrationConsentStore,
		integrationRedisClient,
		baseOptions...,
	)
}

func newIntegrationMessageTransport() *runtimemessaging.RedisMessageTransport {
	transport, err := runtimemessaging.NewRedisMessageTransportForRoot(
		"assistant-service-api-integration",
		runtimemessaging.RedisMessageTransportAdapter,
		integrationRedisClient,
		integrationRedisClient,
	)
	if err != nil {
		panic("assistant-service api_integration create message transport: " + err.Error())
	}
	return transport
}

func resetIntegrationState(t *testing.T) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()

	for _, collection := range []string{
		"assistant_interaction_events",
		"assistant_scorecard_facts",
		"rm_assistant_learning_profile",
		"skill_subscriptions",
		"assistant_preference_facts",
	} {
		if _, err := integrationMongoDB.Collection(collection).DeleteMany(ctx, bson.M{}); err != nil {
			t.Fatalf("reset MongoDB collection %s: %v", collection, err)
		}
	}
	if _, err := integrationPostgresPool.Exec(ctx, `TRUNCATE TABLE skill_consents`); err != nil {
		t.Fatalf("reset Postgres skill_consents: %v", err)
	}
	if err := integrationRedisServer.FlushDBs(ctx, 0, 1, 2); err != nil {
		t.Fatalf("reset assistant integration Redis: %v", err)
	}
}

func TestAssistantStorageTopologyMigrationsAndIndexes(t *testing.T) {
	resetIntegrationState(t)
	ctx := context.Background()

	assertMongoIndex(t, "assistant_interaction_events", "idx_ie_user_created")
	assertMongoIndex(t, "assistant_scorecard_facts", "idx_score_user_created")
	assertMongoIndex(t, "rm_assistant_learning_profile", "idx_alp_user")
	assertMongoIndex(t, "skill_subscriptions", "idx_skill_subscriptions_status_updated")
	assertMongoIndex(t, "assistant_preference_facts", "uq_assistant_preference_identity")

	var migrationApplied bool
	if err := integrationPostgresPool.QueryRow(
		ctx,
		`SELECT EXISTS (SELECT 1 FROM assistant_schema_migrations WHERE version = 1)`,
	).Scan(&migrationApplied); err != nil {
		t.Fatalf("query assistant migration ledger: %v", err)
	}
	if !migrationApplied {
		t.Fatal("assistant consent schema migration v1 was not recorded")
	}

	var activeIndexDefinition string
	if err := integrationPostgresPool.QueryRow(
		ctx,
		`SELECT indexdef FROM pg_indexes WHERE schemaname = current_schema() AND indexname = 'idx_skill_consents_user_active'`,
	).Scan(&activeIndexDefinition); err != nil {
		t.Fatalf("query active consent index: %v", err)
	}
	if !strings.Contains(activeIndexDefinition, "WHERE (revoked_at IS NULL)") {
		t.Fatalf("active consent index is not partial: %s", activeIndexDefinition)
	}

	now := time.Now().UTC()
	event := assistant.InteractionEvent{
		EventID:   "event-storage-topology",
		RunID:     "run-storage-topology",
		UserID:    "user-storage-topology",
		DomainID:  "assistant",
		EventType: "answer_viewed",
		CreatedAt: now,
	}
	if err := integrationEventStore.InsertInteractionEvent(ctx, event); err != nil {
		t.Fatalf("insert MongoDB interaction event: %v", err)
	}
	events, err := integrationEventStore.ListLatestInteractionEvents(ctx, event.UserID, 10)
	if err != nil {
		t.Fatalf("list MongoDB interaction events: %v", err)
	}
	if len(events) != 1 || events[0].EventID != event.EventID {
		t.Fatalf("MongoDB interaction events=%+v", events)
	}

	consent := assistant.SkillConsent{
		ID:           "user-storage-topology:personal_content_access",
		UserID:       "user-storage-topology",
		SkillID:      "personal_content_access",
		GrantedScope: "read_own_content",
		GrantedAt:    now,
	}
	if _, err := integrationConsentStore.UpsertConsent(ctx, consent); err != nil {
		t.Fatalf("upsert Postgres consent: %v", err)
	}
	consents, err := integrationConsentStore.ListActiveConsents(ctx, consent.UserID)
	if err != nil {
		t.Fatalf("list Postgres consents: %v", err)
	}
	if len(consents) != 1 || consents[0].SkillID != consent.SkillID {
		t.Fatalf("Postgres consents=%+v", consents)
	}

	if err := integrationRedisClient.Set(ctx, "assistant:test:protocol", "ready", time.Minute); err != nil {
		t.Fatalf("write Redis protocol engine: %v", err)
	}
	value, err := integrationRedisClient.Get(ctx, "assistant:test:protocol")
	if err != nil {
		t.Fatalf("read Redis protocol engine: %v", err)
	}
	if value != "ready" {
		t.Fatalf("Redis value=%q, want ready", value)
	}
}

func assertMongoIndex(t *testing.T, collectionName, indexName string) {
	t.Helper()
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	cursor, err := integrationMongoDB.Collection(collectionName).Indexes().List(ctx)
	if err != nil {
		t.Fatalf("list MongoDB indexes for %s: %v", collectionName, err)
	}
	defer cursor.Close(ctx)
	for cursor.Next(ctx) {
		var index bson.M
		if err := cursor.Decode(&index); err != nil {
			t.Fatalf("decode MongoDB index for %s: %v", collectionName, err)
		}
		if index["name"] == indexName {
			return
		}
	}
	if err := cursor.Err(); err != nil {
		t.Fatalf("iterate MongoDB indexes for %s: %v", collectionName, err)
	}
	t.Fatalf("MongoDB index %s missing from %s", indexName, collectionName)
}

func runIntegrationMongoContainer(ctx context.Context) (container *mongomod.MongoDBContainer, err error) {
	defer func() {
		if recovered := recover(); recovered != nil {
			err = fmt.Errorf("testcontainers panic: %v", recovered)
		}
	}()
	return mongomod.Run(ctx, "mongo:7-jammy", mongomod.WithReplicaSet("rs0"))
}

func runIntegrationPostgresContainer(ctx context.Context) (container testcontainers.Container, dsn string, err error) {
	defer func() {
		if recovered := recover(); recovered != nil {
			err = fmt.Errorf("testcontainers panic: %v", recovered)
		}
	}()
	container, err = testcontainers.GenericContainer(ctx, testcontainers.GenericContainerRequest{
		ContainerRequest: testcontainers.ContainerRequest{
			Image:        "postgres:16-alpine",
			ExposedPorts: []string{"5432/tcp"},
			Env: map[string]string{
				"POSTGRES_DB":       "postgres",
				"POSTGRES_USER":     "postgres",
				"POSTGRES_PASSWORD": "postgres",
			},
			WaitingFor: wait.ForListeningPort("5432/tcp").WithStartupTimeout(2 * time.Minute),
		},
		Started: true,
	})
	if err != nil {
		return nil, "", err
	}
	endpoint, err := container.Endpoint(ctx, "")
	if err != nil {
		_ = container.Terminate(ctx)
		return nil, "", fmt.Errorf("Postgres endpoint: %w", err)
	}
	dsn = fmt.Sprintf("postgres://postgres:postgres@%s/postgres?sslmode=disable", endpoint)
	return container, dsn, nil
}

func stopIntegrationDependencies(ctx context.Context) {
	if integrationPostgresPool != nil {
		integrationPostgresPool.Close()
	}
	if integrationMongoDB != nil {
		_ = integrationMongoDB.Drop(ctx)
	}
	if integrationMongoClient != nil {
		_ = integrationMongoClient.Disconnect(ctx)
	}
	if integrationPostgresContainer != nil {
		_ = integrationPostgresContainer.Terminate(ctx)
	}
	if integrationMongoContainer != nil {
		_ = integrationMongoContainer.Terminate(ctx)
	}
	if integrationRedisRouter != nil {
		_ = integrationRedisRouter.Close()
	}
	if integrationRedisServer != nil {
		_ = integrationRedisServer.Close(ctx)
	}
}
