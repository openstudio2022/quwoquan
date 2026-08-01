package publicweb

import (
	"context"
	"errors"
	"fmt"

	"go.mongodb.org/mongo-driver/v2/mongo"

	application "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/publicweb"
)

// ProductionRuntime wires the real network boundary, authoritative Mongo
// ledgers and durable run budget. It contains no in-memory fallback and is safe
// to construct independently in every durable worker process.
type ProductionRuntime struct {
	Evidence *MongoEvidenceStore
	Budget   *MongoRunBudgetGate
	Open     *application.Service
	Find     *application.Finder
}

func NewProductionRuntime(
	database *mongo.Database,
	budgetLimits application.RunBudgetLimits,
	fetchLimits FetchLimits,
) *ProductionRuntime {
	if database == nil {
		panic("public web production database is required")
	}
	evidence := NewMongoEvidenceStore(database)
	budget := NewMongoRunBudgetGate(database, budgetLimits)
	policy := NewNetworkPolicy(nil)
	open := application.NewService(
		application.NewLedgerTargetResolver(evidence),
		NewFetcher(policy, fetchLimits),
		evidence,
		budget,
		application.DefaultDocumentParser(),
	)
	return &ProductionRuntime{
		Evidence: evidence,
		Budget:   budget,
		Open:     open,
		Find:     application.NewFinder(evidence),
	}
}

func (r *ProductionRuntime) EnsureIndexes(ctx context.Context) error {
	if r == nil || r.Evidence == nil || r.Budget == nil {
		return errors.New("public web production runtime is incomplete")
	}
	if err := r.Evidence.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("ensure public web evidence indexes: %w", err)
	}
	if err := r.Budget.EnsureIndexes(ctx); err != nil {
		return fmt.Errorf("ensure public web budget indexes: %w", err)
	}
	return nil
}
