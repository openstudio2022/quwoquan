package runtimewiring

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"go.mongodb.org/mongo-driver/v2/mongo"

	rtmongo "quwoquan_service/internal/platform/mongodb"
	platformredis "quwoquan_service/internal/platform/redis"
	rtredis "quwoquan_service/runtime/redis"
	"quwoquan_service/services/assistant-service/internal/application"
	preferenceports "quwoquan_service/services/assistant-service/internal/domain/assistant/preference_fact/ports"
	preferencepersistence "quwoquan_service/services/assistant-service/internal/infrastructure/assistant/preference_fact/persistence"
	"quwoquan_service/services/assistant-service/internal/infrastructure/persistence"
	"quwoquan_service/services/assistant-service/internal/infrastructure/projection"
	"quwoquan_service/services/assistant-service/internal/runtimeconfig"
)

const DependencyProbeTimeout = 10 * time.Second

type DependencyError struct {
	Dependency string
	Stage      string
	Err        error
}

func (e *DependencyError) Error() string {
	return fmt.Sprintf("dependency=%s stage=%s: %v", e.Dependency, e.Stage, e.Err)
}

func (e *DependencyError) Unwrap() error {
	return e.Err
}

func NewDependencyError(dependency, stage string, err error) error {
	if err == nil {
		return nil
	}
	return &DependencyError{
		Dependency: dependency,
		Stage:      stage,
		Err:        err,
	}
}

func ValidateRuntimeDependenciesConfig(cfg runtimeconfig.Config) error {
	if strings.TrimSpace(cfg.MongoDB.URI) == "" {
		return NewDependencyError("mongodb", "configuration", errors.New("mongodb.uri is required"))
	}
	if strings.TrimSpace(cfg.MongoDB.Database) == "" {
		return NewDependencyError("mongodb", "configuration", errors.New("mongodb.database is required"))
	}
	if strings.TrimSpace(cfg.Postgres.DSN) == "" {
		return NewDependencyError("postgres", "configuration", errors.New("postgres.dsn is required"))
	}
	if strings.TrimSpace(cfg.NotificationService.BaseURL) == "" {
		return NewDependencyError("notification-service", "configuration", errors.New("notification_service.base_url is required"))
	}
	if strings.TrimSpace(cfg.SearchService.BaseURL) == "" {
		return NewDependencyError("search-service", "configuration", errors.New("search_service.base_url is required"))
	}
	if strings.TrimSpace(cfg.EntityService.BaseURL) == "" {
		return NewDependencyError("entity-service", "configuration", errors.New("entity_service.base_url is required"))
	}
	if strings.TrimSpace(cfg.ContentService.BaseURL) == "" {
		return NewDependencyError("content-service", "configuration", errors.New("content_service.base_url is required"))
	}
	if err := validateRedisSceneConfig("general", cfg.Redis.General); err != nil {
		return err
	}
	if err := validateRedisSceneConfig("rec", cfg.Redis.Rec); err != nil {
		return err
	}
	return nil
}

func BuildRedisRouter(cfg runtimeconfig.Config) (*rtredis.Router, error) {
	if err := validateRedisSceneConfig("general", cfg.Redis.General); err != nil {
		return nil, err
	}
	if err := validateRedisSceneConfig("rec", cfg.Redis.Rec); err != nil {
		return nil, err
	}
	generalScene := runtimeRedisSceneConfig(cfg.Redis.General)
	router, err := platformredis.NewRouter(rtredis.RouterConfig{
		Scenes: map[string]rtredis.SceneConfig{
			"rec":      runtimeRedisSceneConfig(cfg.Redis.Rec),
			"general":  generalScene,
			"realtime": generalScene,
		},
		PrefixRoutes: rtredis.GeneratedPrefixRoutes(),
		DefaultScene: rtredis.GeneratedDefaultScene,
	})
	if err != nil {
		return nil, NewDependencyError("redis", "initialization", err)
	}
	return router, nil
}

type PersistentDependencies struct {
	EventStore           application.EventStore
	ProfileStore         application.LearningProfileStore
	SubscriptionStore    application.SkillSubscriptionStore
	ConsentStore         application.ConsentStore
	ConversationRunStore application.ConversationRunStore
	PreferenceStore      preferenceports.Store
	PreferenceReader     preferenceports.Reader
	MongoClient          *mongo.Client
	PostgresPool         *pgxpool.Pool
}

func OpenPersistentDependencies(ctx context.Context, cfg runtimeconfig.Config) (deps *PersistentDependencies, err error) {
	deps = &PersistentDependencies{}
	defer func() {
		if err == nil {
			return
		}
		closeCtx, cancel := context.WithTimeout(context.Background(), DependencyProbeTimeout)
		defer cancel()
		_ = deps.Close(closeCtx)
	}()

	mongoClient, err := rtmongo.Connect(
		ctx,
		rtmongo.ConnectConfig{
			URI:      strings.TrimSpace(cfg.MongoDB.URI),
			Database: strings.TrimSpace(cfg.MongoDB.Database),
		},
	)
	if err != nil {
		return nil, NewDependencyError("mongodb", "connectivity", err)
	}
	deps.MongoClient = mongoClient
	db := mongoClient.Database(strings.TrimSpace(cfg.MongoDB.Database))

	mongoEvents := persistence.NewMongoEventStore(db)
	if err := mongoEvents.EnsureIndexes(ctx); err != nil {
		return nil, NewDependencyError("mongodb.interaction_events", "indexes", err)
	}
	deps.EventStore = mongoEvents

	mongoProfiles := projection.NewLearningProfileStore(db)
	if err := mongoProfiles.EnsureIndexes(ctx); err != nil {
		return nil, NewDependencyError("mongodb.rm_assistant_learning_profile", "indexes", err)
	}
	deps.ProfileStore = mongoProfiles

	mongoSubscriptions := persistence.NewMongoSkillSubscriptionStore(db)
	if err := mongoSubscriptions.EnsureIndexes(ctx); err != nil {
		return nil, NewDependencyError("mongodb.skill_subscriptions", "indexes", err)
	}
	deps.SubscriptionStore = mongoSubscriptions

	mongoConversationRuns := persistence.NewMongoConversationRunStore(db)
	if err := mongoConversationRuns.EnsureIndexes(ctx); err != nil {
		return nil, NewDependencyError("mongodb.assistant_runs", "indexes", err)
	}
	deps.ConversationRunStore = mongoConversationRuns

	mongoPreferences := preferencepersistence.NewMongoStore(db)
	if err := mongoPreferences.EnsureIndexes(ctx); err != nil {
		return nil, NewDependencyError(
			"mongodb.assistant_preference_facts",
			"indexes",
			err,
		)
	}
	deps.PreferenceStore = mongoPreferences
	deps.PreferenceReader = mongoPreferences

	poolCfg, err := pgxpool.ParseConfig(strings.TrimSpace(cfg.Postgres.DSN))
	if err != nil {
		return nil, NewDependencyError("postgres", "configuration", err)
	}
	if cfg.Postgres.MaxOpenConns > 0 {
		poolCfg.MaxConns = int32(cfg.Postgres.MaxOpenConns)
	}
	if cfg.Postgres.MaxIdleConns > 0 {
		poolCfg.MinConns = int32(cfg.Postgres.MaxIdleConns)
	}
	if cfg.Postgres.ConnMaxLifetimeMinutes > 0 {
		poolCfg.MaxConnLifetime = time.Duration(cfg.Postgres.ConnMaxLifetimeMinutes) * time.Minute
	}
	postgresPool, err := pgxpool.NewWithConfig(ctx, poolCfg)
	if err != nil {
		return nil, NewDependencyError("postgres", "connectivity", err)
	}
	deps.PostgresPool = postgresPool

	probeCtx, cancel := context.WithTimeout(ctx, DependencyProbeTimeout)
	defer cancel()
	if err := pingPostgresUntilReady(probeCtx, postgresPool); err != nil {
		return nil, NewDependencyError("postgres", "connectivity", err)
	}

	pgConsents := persistence.NewPgConsentStore(postgresPool)
	if err := pgConsents.EnsureSchema(ctx); err != nil {
		return nil, NewDependencyError("postgres.skill_consents", "migration", err)
	}
	deps.ConsentStore = pgConsents

	return deps, nil
}

func (d *PersistentDependencies) Close(ctx context.Context) error {
	if d == nil {
		return nil
	}
	if d.PostgresPool != nil {
		d.PostgresPool.Close()
	}
	if d.MongoClient != nil {
		return d.MongoClient.Disconnect(ctx)
	}
	return nil
}

func validateRedisSceneConfig(name string, scene runtimeconfig.RedisSceneConfig) error {
	mode := strings.TrimSpace(scene.Mode)
	switch mode {
	case "standalone":
		if strings.TrimSpace(scene.Addr) == "" {
			return NewDependencyError(
				"redis."+name,
				"configuration",
				fmt.Errorf("redis.%s.addr is required for standalone mode", name),
			)
		}
	case "cluster":
		if len(nonEmptyStrings(scene.Addrs)) == 0 {
			return NewDependencyError(
				"redis."+name,
				"configuration",
				fmt.Errorf("redis.%s.addrs is required for cluster mode", name),
			)
		}
	default:
		return NewDependencyError(
			"redis."+name,
			"configuration",
			fmt.Errorf("redis.%s.mode must be standalone or cluster, got %q", name, mode),
		)
	}
	return nil
}

func runtimeRedisSceneConfig(cfg runtimeconfig.RedisSceneConfig) rtredis.SceneConfig {
	return rtredis.SceneConfig{
		Mode:           strings.TrimSpace(cfg.Mode),
		Addr:           strings.TrimSpace(cfg.Addr),
		Addrs:          nonEmptyStrings(cfg.Addrs),
		Password:       cfg.Password,
		DB:             cfg.DB,
		TLS:            cfg.TLS,
		PoolSize:       cfg.Pool.Size,
		MinIdleConns:   cfg.Pool.MinIdle,
		ReadTimeoutMs:  cfg.Pool.ReadTimeoutMs,
		WriteTimeoutMs: cfg.Pool.WriteTimeoutMs,
		DialTimeoutMs:  cfg.Pool.DialTimeoutMs,
	}
}

func pingPostgresUntilReady(ctx context.Context, pool *pgxpool.Pool) error {
	var lastErr error
	ticker := time.NewTicker(250 * time.Millisecond)
	defer ticker.Stop()
	for {
		if err := pool.Ping(ctx); err == nil {
			return nil
		} else {
			lastErr = err
		}
		select {
		case <-ctx.Done():
			return fmt.Errorf("postgres readiness probe exhausted: %w", lastErr)
		case <-ticker.C:
		}
	}
}

func nonEmptyStrings(values []string) []string {
	out := make([]string, 0, len(values))
	for _, value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			out = append(out, trimmed)
		}
	}
	return out
}
