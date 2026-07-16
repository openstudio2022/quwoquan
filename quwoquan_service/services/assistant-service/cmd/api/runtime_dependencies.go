package main

import (
	"context"
	"strings"

	"github.com/jackc/pgx/v5/pgxpool"
	"go.mongodb.org/mongo-driver/v2/mongo"

	"quwoquan_service/services/assistant-service/internal/application"
	"quwoquan_service/services/assistant-service/internal/runtimewiring"
)

const dependencyProbeTimeout = runtimewiring.DependencyProbeTimeout

type startupDependencyError = runtimewiring.DependencyError

func dependencyError(dependency, stage string, err error) error {
	return runtimewiring.NewDependencyError(dependency, stage, err)
}

func validateRuntimeDependenciesConfig(cfg config) error {
	return runtimewiring.ValidateRuntimeDependenciesConfig(cfg)
}

type persistentDependencies struct {
	eventStore        application.EventStore
	profileStore      application.LearningProfileStore
	subscriptionStore application.SkillSubscriptionStore
	consentStore      application.ConsentStore
	mongoClient       *mongo.Client
	postgresPool      *pgxpool.Pool
	inner             *runtimewiring.PersistentDependencies
}

func openPersistentDependencies(ctx context.Context, cfg config) (*persistentDependencies, error) {
	inner, err := runtimewiring.OpenPersistentDependencies(ctx, cfg)
	if err != nil {
		return nil, err
	}
	return &persistentDependencies{
		eventStore:        inner.EventStore,
		profileStore:      inner.ProfileStore,
		subscriptionStore: inner.SubscriptionStore,
		consentStore:      inner.ConsentStore,
		mongoClient:       inner.MongoClient,
		postgresPool:      inner.PostgresPool,
		inner:             inner,
	}, nil
}

func (d *persistentDependencies) Close(ctx context.Context) error {
	if d == nil {
		return nil
	}
	if d.inner != nil {
		return d.inner.Close(ctx)
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
