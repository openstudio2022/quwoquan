package ports

import (
	"context"

	"quwoquan_service/services/product-ops-service/internal/product_ops/experiment/domain/model"
)

type ChangeSet struct {
	Experiment     model.Experiment
	Events         []model.Event
	IdempotencyKey string
	CommandDigest  string
}

type CommitReceipt struct {
	ExperimentID string
	Version      int64
	Replayed     bool
}

type AssignmentStats struct {
	VariantCounts    map[string]int
	AssignedSubjects int
}

type AggregateStore interface {
	Load(context.Context, string) (model.Experiment, error)
	Replay(context.Context, string, string, string) (CommitReceipt, bool, error)
	Commit(context.Context, int64, ChangeSet) (CommitReceipt, error)
}

type CatalogReader interface {
	List(context.Context) ([]model.Experiment, error)
}

type AssignmentSink interface {
	Append(context.Context, model.AssignmentFact) (model.AssignmentFact, bool, error)
}

type AssignmentReader interface {
	Get(context.Context, string, int64, string) (model.AssignmentFact, error)
	Stats(context.Context, string, int64) (AssignmentStats, error)
}
