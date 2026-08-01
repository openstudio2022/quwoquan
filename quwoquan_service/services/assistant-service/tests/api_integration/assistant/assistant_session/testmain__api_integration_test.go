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
	learningapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/application"
	learningmodel "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/domain/model"
	learningpersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/infrastructure/persistence"
	learningprojection "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/infrastructure/projection"
	preferencefact "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/application"
	preferencepersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/infrastructure/persistence"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	runpersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/persistence"
	consentapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/application"
	consentpersistence "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/infrastructure/persistence"
)

const integrationPolicyReleaseDigest = "e1a0a7e3379c544c2551da7aafba674ddae2ac9c7d08fdb5762301e9097c771d"

var (
	integrationMongoDB           *mongo.Database
	integrationMongoClient       *mongo.Client
	integrationMongoContainer    *mongomod.MongoDBContainer
	integrationPostgresPool      *pgxpool.Pool
	integrationPostgresContainer testcontainers.Container
	integrationRedisServer       *testinfra.RealRedis
	integrationRedisRouter       *rtredis.Router
	integrationRedisClient       rtredis.Client
	integrationConsentStore      *consentpersistence.PgStore
	integrationSubscriptionStore *persistence.MongoSkillSubscriptionStore
	integrationSessionRunStore   *persistence.MongoSessionRunStore
	integrationLearningFactStore *learningpersistence.MongoStore
	integrationLearningProjector *learningprojection.MongoProjector
	integrationPreferenceStore   *preferencepersistence.MongoStore
	integrationRunRepository     *runpersistence.MongoRunRepository
	integrationRunCommands       *runruntime.CommandService
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
	readinessDeadline := time.Now().Add(30 * time.Second)
	for {
		err = integrationPostgresPool.Ping(ctx)
		if err == nil {
			break
		}
		if ctx.Err() != nil || time.Now().After(readinessDeadline) {
			panic("assistant-service api_integration ping Postgres: " + err.Error())
		}
		select {
		case <-ctx.Done():
			panic("assistant-service api_integration ping Postgres: " + ctx.Err().Error())
		case <-time.After(200 * time.Millisecond):
		}
	}
}

func initializeIntegrationStores(ctx context.Context) {
	integrationSubscriptionStore = persistence.NewMongoSkillSubscriptionStore(integrationMongoDB)
	if err := integrationSubscriptionStore.EnsureIndexes(ctx); err != nil {
		panic("assistant-service api_integration ensure subscription indexes: " + err.Error())
	}
	integrationConsentStore = consentpersistence.NewPgStore(integrationPostgresPool)
	if err := integrationConsentStore.EnsureSchema(ctx); err != nil {
		panic("assistant-service api_integration ensure SkillConsent schema: " + err.Error())
	}
	integrationSessionRunStore = persistence.NewMongoSessionRunStore(integrationMongoDB)
	if err := integrationSessionRunStore.EnsureIndexes(ctx); err != nil {
		panic("assistant-service api_integration ensure session/run indexes: " + err.Error())
	}
	integrationRunRepository = runpersistence.NewMongoRunRepository(
		integrationMongoDB,
	)
	if err := integrationRunRepository.EnsureIndexes(ctx); err != nil {
		panic("assistant-service api_integration ensure AssistantRun indexes: " + err.Error())
	}
	integrationRunCommands = runruntime.NewCommandService(
		integrationRunRepository,
		runruntime.SessionAuthorizerFunc(func(
			context.Context,
			string,
			string,
		) error {
			return nil
		}),
		time.Now,
		nil,
	)
	integrationLearningFactStore = learningpersistence.NewMongoStore(
		integrationMongoDB,
	)
	if err := integrationLearningFactStore.EnsureIndexes(ctx); err != nil {
		panic("assistant-service api_integration ensure learning fact indexes: " + err.Error())
	}
	integrationLearningProjector = learningprojection.NewMongoProjector(
		integrationMongoDB,
	)
	if err := integrationLearningProjector.EnsureIndexes(ctx); err != nil {
		panic("assistant-service api_integration ensure learning projection indexes: " + err.Error())
	}
	integrationPreferenceStore = preferencepersistence.NewMongoStore(integrationMongoDB)
	if err := integrationPreferenceStore.EnsureIndexes(ctx); err != nil {
		panic("assistant-service api_integration ensure preference indexes: " + err.Error())
	}
}

func newIntegrationAssistantService(opts ...orchestration.AssistantServiceOption) *orchestration.AssistantService {
	learningFactService := learningapplication.NewService(
		integrationLearningFactStore,
		learningpersistence.NewMongoRunOwnerReader(integrationMongoDB),
		nil,
	)
	baseOptions := []orchestration.AssistantServiceOption{
		orchestration.WithLearningFactWriter(
			ports.LearningFactWriterFunc(
				func(
					ctx context.Context,
					command ports.ServiceScorecardFactCommand,
				) error {
					_, err := learningFactService.AppendServiceFact(
						ctx,
						learningmodel.AppendCommand{
							EventID:          command.EventID,
							FactType:         learningmodel.FactTypeServiceScorecard,
							AssistantTurnID:  command.AssistantTurnID,
							ReferralSource:   "service",
							DomainID:         command.DomainID,
							MetricID:         command.MetricID,
							MetricValue:      command.MetricValue,
							MetricSource:     command.MetricSource,
							TrainingEligible: false,
							OccurredAt:       command.OccurredAt,
						},
					)
					return err
				},
			),
		),
		orchestration.WithLearningProjectionReader(integrationLearningProjector),
		orchestration.WithSkillSubscriptionStore(integrationSubscriptionStore),
		orchestration.WithSessionRunStore(integrationSessionRunStore),
		orchestration.WithRunCommandService(integrationRunCommands),
		orchestration.WithFrozenPolicyResolver(
			ports.FrozenPolicyResolverFunc(
				func(
					_ context.Context,
					policyID string,
					_ string,
					skillID string,
					domainID string,
				) (assistant.AssistantFrozenPolicySelection, error) {
					if strings.TrimSpace(skillID) == "" {
						skillID = "fallback_general_search"
					}
					if strings.TrimSpace(domainID) == "" {
						domainID = "assistant"
					}
					return assistant.AssistantFrozenPolicySelection{
						PolicyID:        policyID,
						ReleaseDigest:   integrationPolicyReleaseDigest,
						Cohort:          "control",
						RolloutRevision: 1,
						RuleID:          "test-default",
						Template: assistant.AssistantFrozenPolicyTemplate{
							TemplateID:      "test-template",
							SkillID:         skillID,
							DomainID:        domainID,
							PromptPolicy:    "test frozen prompt",
							AllowedTools:    []string{},
							SearchIntensity: "medium",
						},
					}, nil
				},
			),
		),
		orchestration.WithPreferenceSnapshotReader(
			preferencefact.NewQueryFacade(integrationPreferenceStore),
		),
	}
	baseOptions = append(baseOptions, opts...)
	return orchestration.NewAssistantService(
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
		"assistant_sessions",
		"assistant_runs",
		"assistant_run_events",
		"assistant_learning_facts",
		"assistant_learning_fact_receipts",
		"assistant_learning_fact_outbox",
		"assistant_learning_fact_sequences",
		"assistant_learning_projection_receipts",
		"assistant_learning_projection_watermarks",
		"rm_assistant_learning_projection",
		"assistant_policy_releases",
		"assistant_policy_release_receipts",
		"assistant_policy_release_outbox",
		"assistant_policy_rollouts",
		"assistant_policy_rollout_receipts",
		"assistant_policy_rollout_outbox",
		"skill_subscriptions",
		"assistant_preferences",
	} {
		if _, err := integrationMongoDB.Collection(collection).DeleteMany(ctx, bson.M{}); err != nil {
			t.Fatalf("reset MongoDB collection %s: %v", collection, err)
		}
	}
	if _, err := integrationPostgresPool.Exec(
		ctx,
		`TRUNCATE TABLE skill_consent_events, skill_consent_command_receipts, skill_consents`,
	); err != nil {
		t.Fatalf("reset Postgres SkillConsent tables: %v", err)
	}
	if err := integrationRedisServer.FlushDBs(ctx, 0, 1, 2); err != nil {
		t.Fatalf("reset assistant integration Redis: %v", err)
	}
	if _, err := integrationLearningProjector.Rebuild(ctx); err != nil {
		t.Fatalf("initialize canonical assistant learning projection: %v", err)
	}
}

func TestAssistantStorageTopologyMigrationsAndIndexes(t *testing.T) {
	resetIntegrationState(t)
	ctx := context.Background()

	assertMongoIndex(t, "skill_subscriptions", "idx_skill_subscriptions_status_updated")
	assertMongoIndex(t, "assistant_preferences", "uq_assistant_preference_identity")
	assertMongoIndex(t, "assistant_run_events", "uq_run_events_run_seq")
	assertMongoIndex(t, "assistant_learning_facts", "uq_assistant_learning_fact_sequence")
	assertMongoIndex(t, "assistant_learning_facts", "idx_assistant_learning_fact_turn")
	assertMongoIndex(t, "rm_assistant_learning_projection", "idx_assistant_learning_projection_owner_updated")

	var activeIndexDefinition string
	if err := integrationPostgresPool.QueryRow(
		ctx,
		`SELECT indexdef FROM pg_indexes WHERE schemaname = current_schema() AND indexname = 'idx_skill_consents_account_active'`,
	).Scan(&activeIndexDefinition); err != nil {
		t.Fatalf("query active consent index: %v", err)
	}
	if !strings.Contains(activeIndexDefinition, "WHERE (revoked_at IS NULL)") {
		t.Fatalf("active consent index is not partial: %s", activeIndexDefinition)
	}

	commands := consentapplication.NewCommandFacade(
		integrationConsentStore,
		func() time.Time { return time.Now().UTC() },
	)
	result, err := commands.Grant(
		ctx,
		"storage-topology-command",
		"account-storage-topology",
		"personal_content_access",
		"read_own_content",
	)
	if err != nil || result.Consent == nil {
		t.Fatalf("grant Postgres consent result=%+v error=%v", result, err)
	}
	consents, err := integrationConsentStore.ListActiveConsents(
		ctx, "account-storage-topology",
	)
	if err != nil {
		t.Fatalf("list Postgres consents: %v", err)
	}
	if len(consents) != 1 || consents[0].SkillID != "personal_content_access" {
		t.Fatalf("Postgres consents=%+v", consents)
	}
	for _, table := range []string{
		"skill_consent_command_receipts",
		"skill_consent_events",
	} {
		var count int
		if err := integrationPostgresPool.QueryRow(
			ctx, "SELECT COUNT(*) FROM "+table,
		).Scan(&count); err != nil || count != 1 {
			t.Fatalf("%s count=%d error=%v, want 1", table, count, err)
		}
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
