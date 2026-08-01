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
	preferenceports "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/ports"
	sessionports "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/persistence"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/runtimeconfig"
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
	if strings.TrimSpace(cfg.UserService.BaseURL) == "" {
		return NewDependencyError("user-service", "configuration", errors.New("user_service.base_url is required"))
	}
	if strings.TrimSpace(cfg.ChatService.BaseURL) == "" {
		return NewDependencyError("chat-service", "configuration", errors.New("chat_service.base_url is required"))
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
	SubscriptionStore sessionports.SkillSubscriptionStore
	SessionRunStore   sessionports.SessionRunStore
	PreferenceStore   preferenceports.Store
	PreferenceReader  preferenceports.Reader
	MongoClient       *mongo.Client
	PostgresPool      *pgxpool.Pool
}

type PreferenceStoreFactory func(
	db *mongo.Database,
) (preferenceports.Store, preferenceports.Reader, error)

func OpenPersistentDependencies(
	ctx context.Context,
	cfg runtimeconfig.Config,
	preferenceFactory PreferenceStoreFactory,
) (deps *PersistentDependencies, err error) {
	if preferenceFactory == nil {
		return nil, NewDependencyError("mongodb.assistant_preferences", "composition", errors.New("preference store factory is required"))
	}
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

	mongoSubscriptions := persistence.NewMongoSkillSubscriptionStore(db)
	if err := mongoSubscriptions.EnsureIndexes(ctx); err != nil {
		return nil, NewDependencyError("mongodb.skill_subscriptions", "indexes", err)
	}
	deps.SubscriptionStore = mongoSubscriptions

	mongoSessionRuns := persistence.NewMongoSessionRunStore(db)
	if err := mongoSessionRuns.EnsureIndexes(ctx); err != nil {
		return nil, NewDependencyError("mongodb.assistant_runs", "indexes", err)
	}
	deps.SessionRunStore = mongoSessionRuns

	preferenceStore, preferenceReader, err := preferenceFactory(db)
	if err != nil {
		return nil, NewDependencyError(
			"mongodb.assistant_preferences",
			"indexes",
			err,
		)
	}
	deps.PreferenceStore = preferenceStore
	deps.PreferenceReader = preferenceReader

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
