package repository

import (
	"context"
	"database/sql"
	"fmt"

	"go.mongodb.org/mongo-driver/v2/mongo"

	"quwoquan_service/runtime/registry"
)

// Factory creates Repository instances driven by metadata.
type Factory struct {
	reg              *registry.EntityRegistry
	pgDB             *sql.DB
	mongoDB          *mongo.Database
	cache            CacheAdapter
	interceptorBuild InterceptorBuilder
}

// CacheAdapter abstracts cache operations (Redis/in-memory).
type CacheAdapter interface {
	Get(ctx context.Context, key string) ([]byte, error)
	Set(ctx context.Context, key string, value []byte, ttlSeconds int) error
	Del(ctx context.Context, key string) error
}

// InterceptorBuilder wraps a base repository with an interceptor chain.
// This avoids importing the interceptor package (no circular dependency).
type InterceptorBuilder func(inner Repository[map[string]any], entityName string) Repository[map[string]any]

// FactoryOption configures the Factory.
type FactoryOption func(*Factory)

func WithPostgres(db *sql.DB) FactoryOption {
	return func(f *Factory) { f.pgDB = db }
}

func WithMongo(db *mongo.Database) FactoryOption {
	return func(f *Factory) { f.mongoDB = db }
}

func WithCache(c CacheAdapter) FactoryOption {
	return func(f *Factory) { f.cache = c }
}

// WithInterceptors sets an interceptor builder for auto-wrapping repositories.
func WithInterceptors(b InterceptorBuilder) FactoryOption {
	return func(f *Factory) { f.interceptorBuild = b }
}

// NewFactory creates a repository factory backed by the EntityRegistry.
func NewFactory(reg *registry.EntityRegistry, opts ...FactoryOption) *Factory {
	f := &Factory{reg: reg}
	for _, o := range opts {
		o(f)
	}
	return f
}

// Create returns a fully-decorated Repository for the named entity:
//  1. Select storage adapter (Postgres or Mongo) from metadata
//  2. Auto-wrap with cache if cache_ttl_seconds > 0 and CacheAdapter provided
//  3. Auto-wrap with interceptor chain if InterceptorBuilder provided
func (f *Factory) Create(entityName string) (Repository[map[string]any], error) {
	backend, err := f.reg.GetStorageBackend(entityName)
	if err != nil {
		return nil, err
	}

	var base Repository[map[string]any]

	switch backend {
	case "postgres":
		if f.pgDB == nil {
			return nil, fmt.Errorf("postgres backend required for entity %q but no pg connection provided", entityName)
		}
		base, err = newPGRepository(f, entityName)
	case "mongodb":
		if f.mongoDB == nil {
			return nil, fmt.Errorf("mongodb backend required for entity %q but no mongo connection provided", entityName)
		}
		base, err = newMongoRepository(f, entityName)
	default:
		return nil, fmt.Errorf("unsupported storage backend %q for entity %q", backend, entityName)
	}
	if err != nil {
		return nil, err
	}

	repo := base

	// Auto-wrap: cache decorator when TTL configured
	if f.cache != nil {
		ttl, _ := f.reg.GetCacheTTL(entityName)
		if ttl > 0 {
			repo = NewCachedRepository(repo, f.cache, entityName, ttl)
		}
	}

	// Auto-wrap: interceptor chain
	if f.interceptorBuild != nil {
		repo = f.interceptorBuild(repo, entityName)
	}

	return repo, nil
}
