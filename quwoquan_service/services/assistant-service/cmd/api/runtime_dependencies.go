package main

import (
	"context"
	"strings"

	"github.com/jackc/pgx/v5/pgxpool"
	"go.mongodb.org/mongo-driver/v2/mongo"

	learningpersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/infrastructure/persistence"
	learningprojection "quwoquan_service/services/assistant-service/internal/assistant/assistant_learning_fact/infrastructure/projection"
	policyreleasepersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_release/infrastructure/persistence"
	policyrolloutpersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_policy_rollout/infrastructure/persistence"
	preferenceports "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/domain/ports"
	preferencepersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_preference/infrastructure/persistence"
	publicwebapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/publicweb"
	runpersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure"
	publicwebpersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/publicweb"
	sessionports "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/runtimewiring"
	turnviewapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_turn_view/application"
	turnviewpersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_turn_view/infrastructure/persistence"
	consentports "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/domain/ports"
	consentpersistence "quwoquan_service/services/assistant-service/internal/assistant/skill_consent/infrastructure/persistence"
	skillpackagepersistence "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/infrastructure/persistence"
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
	subscriptionStore  sessionports.SkillSubscriptionStore
	consentStore       consentports.Store
	sessionRunStore    sessionports.SessionRunStore
	preferenceStore    preferenceports.Store
	preferenceReader   preferenceports.Reader
	turnViewReader     turnviewapplication.Reader
	policyReleaseStore *policyreleasepersistence.MongoStore
	policyRolloutStore *policyrolloutpersistence.MongoStore
	learningFactStore  *learningpersistence.MongoStore
	learningProjection *learningprojection.MongoProjector
	learningRunOwners  *learningpersistence.MongoRunOwnerReader
	runRepository      *runpersistence.MongoRunRepository
	publicWebEvidence  *publicwebpersistence.MongoEvidenceStore
	publicWebBudget    *publicwebpersistence.MongoRunBudgetGate
	skillPackageStore  *skillpackagepersistence.MongoStore
	mongoClient        *mongo.Client
	postgresPool       *pgxpool.Pool
	inner              *runtimewiring.PersistentDependencies
}

func openPersistentDependencies(ctx context.Context, cfg config) (*persistentDependencies, error) {
	inner, err := runtimewiring.OpenPersistentDependencies(ctx, cfg, func(db *mongo.Database) (preferenceports.Store, preferenceports.Reader, error) {
		store := preferencepersistence.NewMongoStore(db)
		if err := store.EnsureIndexes(ctx); err != nil {
			return nil, nil, err
		}
		return store, store, nil
	})
	if err != nil {
		return nil, err
	}
	database := inner.MongoClient.Database(strings.TrimSpace(cfg.MongoDB.Database))
	consentStore := consentpersistence.NewPgStore(inner.PostgresPool)
	if err := consentStore.EnsureSchema(ctx); err != nil {
		_ = inner.Close(ctx)
		return nil, dependencyError("postgres.skill_consents", "schema", err)
	}
	policyReleaseStore := policyreleasepersistence.NewMongoStore(database)
	if err := policyReleaseStore.EnsureIndexes(ctx); err != nil {
		_ = inner.Close(ctx)
		return nil, dependencyError(
			"mongodb.assistant_policy_releases",
			"indexes",
			err,
		)
	}
	policyRolloutStore := policyrolloutpersistence.NewMongoStore(database)
	if err := policyRolloutStore.EnsureIndexes(ctx); err != nil {
		_ = inner.Close(ctx)
		return nil, dependencyError(
			"mongodb.assistant_policy_rollouts",
			"indexes",
			err,
		)
	}
	learningFactStore := learningpersistence.NewMongoStore(database)
	if err := learningFactStore.EnsureIndexes(ctx); err != nil {
		_ = inner.Close(ctx)
		return nil, dependencyError(
			"mongodb.assistant_learning_facts",
			"indexes",
			err,
		)
	}
	learningProjector := learningprojection.NewMongoProjector(database)
	if err := learningProjector.EnsureIndexes(ctx); err != nil {
		_ = inner.Close(ctx)
		return nil, dependencyError(
			"mongodb.rm_assistant_learning_projection",
			"indexes",
			err,
		)
	}
	runRepository := runpersistence.NewMongoRunRepository(database)
	if err := runRepository.EnsureIndexes(ctx); err != nil {
		_ = inner.Close(ctx)
		return nil, dependencyError(
			"mongodb.assistant_runs",
			"indexes",
			err,
		)
	}
	publicWebEvidence := publicwebpersistence.NewMongoEvidenceStore(database)
	if err := publicWebEvidence.EnsureIndexes(ctx); err != nil {
		_ = inner.Close(ctx)
		return nil, dependencyError(
			"mongodb.assistant_run_web_evidence",
			"indexes",
			err,
		)
	}
	publicWebBudget := publicwebpersistence.NewMongoRunBudgetGate(
		database,
		publicwebapplication.RunBudgetLimits{
			MaxPages: 24,
			MaxBytes: 32 << 20,
		},
	)
	if err := publicWebBudget.EnsureIndexes(ctx); err != nil {
		_ = inner.Close(ctx)
		return nil, dependencyError(
			"mongodb.assistant_run_web_budgets",
			"indexes",
			err,
		)
	}
	skillPackageStore := skillpackagepersistence.NewMongoStore(database)
	if err := skillPackageStore.EnsureIndexes(ctx); err != nil {
		_ = inner.Close(ctx)
		return nil, dependencyError(
			"mongodb.assistant_skill_packages",
			"indexes",
			err,
		)
	}
	return &persistentDependencies{
		subscriptionStore:  inner.SubscriptionStore,
		consentStore:       consentStore,
		sessionRunStore:    inner.SessionRunStore,
		preferenceStore:    inner.PreferenceStore,
		preferenceReader:   inner.PreferenceReader,
		turnViewReader:     turnviewpersistence.NewMongoReader(database),
		policyReleaseStore: policyReleaseStore,
		policyRolloutStore: policyRolloutStore,
		learningFactStore:  learningFactStore,
		learningProjection: learningProjector,
		learningRunOwners:  learningpersistence.NewMongoRunOwnerReader(database),
		runRepository:      runRepository,
		publicWebEvidence:  publicWebEvidence,
		publicWebBudget:    publicWebBudget,
		skillPackageStore:  skillPackageStore,
		mongoClient:        inner.MongoClient,
		postgresPool:       inner.PostgresPool,
		inner:              inner,
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
