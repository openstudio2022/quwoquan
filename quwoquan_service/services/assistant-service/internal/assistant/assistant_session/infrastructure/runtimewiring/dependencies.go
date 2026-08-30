package runtimewiring

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
	"go.mongodb.org/mongo-driver/v2/mongo"

	preferenceports "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/ports"
	sessionports "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/persistence"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/runtimeconfig"
	subscriptionports "quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/ports"
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

// ValidateRuntimeDependenciesConfig 校验领域出向依赖与 Redis scene 声明。
// mongodb.uri/database 与 postgres.dsn 的必填由 servicekit 的 required 声明
// 承担，此处不再重复，避免同一约束出现第二处真相源。
func ValidateRuntimeDependenciesConfig(cfg runtimeconfig.Config) error {
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
	if strings.TrimSpace(cfg.IntegrationService.BaseURL) == "" {
		return NewDependencyError("integration-service", "configuration", errors.New("integration_service.base_url is required"))
	}
	if err := validateRedisSceneConfig("general", cfg.Redis.General); err != nil {
		return err
	}
	if err := validateRedisSceneConfig("rec", cfg.Redis.Rec); err != nil {
		return err
	}
	return nil
}

// RedisScenes 把两段声明装配成三个 codegen scene：realtime 复用 general 的
// 物理实例，rec 独立。scene 名与 rtredis 的 generated 前缀路由同源。
func RedisScenes(cfg runtimeconfig.Config) map[string]runtimeconfig.RedisSceneConfig {
	return map[string]runtimeconfig.RedisSceneConfig{
		"rec":      cfg.Redis.Rec,
		"general":  cfg.Redis.General,
		"realtime": cfg.Redis.General,
	}
}

type PersistentDependencies struct {
	SubscriptionStore subscriptionports.Store
	SessionStore      sessionports.SessionStore
	PreferenceStore   preferenceports.Store
	PreferenceReader  preferenceports.Reader
	PostgresPool      *pgxpool.Pool
}

type PreferenceStoreFactory func(
	db *mongo.Database,
) (preferenceports.Store, preferenceports.Reader, error)

type SubscriptionStoreFactory func(
	db *mongo.Database,
) (subscriptionports.Store, error)

// OpenPersistentDependencies 在骨架已装配的 Mongo database 与 Postgres 连接池
// 之上打开领域仓储。连接生命周期归 servicekit 装配面所有，这里只做 schema /
// index 就绪，失败即 fail-closed 交回上层。
func OpenPersistentDependencies(
	ctx context.Context,
	db *mongo.Database,
	postgresPool *pgxpool.Pool,
	subscriptionFactory SubscriptionStoreFactory,
	preferenceFactory PreferenceStoreFactory,
) (deps *PersistentDependencies, err error) {
	if db == nil {
		return nil, NewDependencyError("mongodb", "composition", errors.New("mongo database handle is required"))
	}
	if postgresPool == nil {
		return nil, NewDependencyError("postgres", "composition", errors.New("postgres pool is required"))
	}
	if subscriptionFactory == nil {
		return nil, NewDependencyError("mongodb.skill_subscriptions", "composition", errors.New("subscription store factory is required"))
	}
	if preferenceFactory == nil {
		return nil, NewDependencyError("mongodb.assistant_preferences", "composition", errors.New("preference store factory is required"))
	}
	deps = &PersistentDependencies{PostgresPool: postgresPool}

	mongoSubscriptions, err := subscriptionFactory(db)
	if err != nil {
		return nil, NewDependencyError("mongodb.skill_subscriptions", "indexes", err)
	}
	deps.SubscriptionStore = mongoSubscriptions

	mongoSessions := persistence.NewMongoSessionStore(db)
	if err := mongoSessions.EnsureIndexes(ctx); err != nil {
		return nil, NewDependencyError("mongodb.assistant_sessions", "indexes", err)
	}
	deps.SessionStore = mongoSessions

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

	return deps, nil
}

// ValidateRedisSceneConfig 保持迁移前的 fail-closed 强度：assistant 的
// general/rec scene 必须显式声明 standalone 地址或 cluster 地址表，缺失不得
// 静默回落 memory——会话与推荐上下文落到单实例内存里等于静默丢数据。
func ValidateRedisSceneConfig(name string, scene runtimeconfig.RedisSceneConfig) error {
	return validateRedisSceneConfig(name, scene)
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

func nonEmptyStrings(values []string) []string {
	out := make([]string, 0, len(values))
	for _, value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			out = append(out, trimmed)
		}
	}
	return out
}
