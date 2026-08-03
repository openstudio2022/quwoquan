package application

import (
	"context"
	"errors"
	"fmt"
	"time"

	"quwoquan_service/services/product-ops-service/internal/product_ops/experiment/domain/model"
	"quwoquan_service/services/product-ops-service/internal/product_ops/experiment/domain/ports"
	assignmentdomain "quwoquan_service/services/product-ops-service/internal/product_ops/experiment_assignment_fact/domain"
)

var ErrInvalidObservation = errors.New("experiment assignment observation is invalid")

// Facade owns assignment-fact append and read use cases. Experiment is consulted
// only to resolve the current aggregate revision and deterministic variant.
type Facade struct {
	experiments ports.AggregateStore
	sink        Sink
	reader      Reader
}

type AssignmentObservation struct {
	ExperimentID       string
	ExperimentRevision int64
	SubjectKey         string
	Variant            string
	ObservedAt         time.Time
}

type Sink interface {
	Append(context.Context, assignmentdomain.Fact) (assignmentdomain.Fact, bool, error)
}

type Reader interface {
	Get(context.Context, string, int64, string) (assignmentdomain.Fact, error)
	Stats(context.Context, string, int64) (assignmentdomain.Stats, error)
}

func NewFacade(experiments ports.AggregateStore, sink Sink, reader Reader) (*Facade, error) {
	if experiments == nil || sink == nil || reader == nil {
		return nil, fmt.Errorf("experiment store, assignment sink and reader are required")
	}
	return &Facade{experiments: experiments, sink: sink, reader: reader}, nil
}

// AppendObserved accepts only a runtime observation produced by Recommendation
// or Search. It recomputes the bucket through Experiment's canonical shared
// algorithm before appending, so neither clients nor services can choose a
// private bucket or write against a stale policy revision.
func (f *Facade) AppendObserved(
	ctx context.Context,
	observation AssignmentObservation,
) (assignmentdomain.Fact, bool, error) {
	experiment, err := f.experiments.LoadRevision(
		ctx,
		observation.ExperimentID,
		observation.ExperimentRevision,
	)
	if err != nil {
		return assignmentdomain.Fact{}, false, err
	}
	observedAt := observation.ObservedAt.UTC()
	if observedAt.IsZero() {
		return assignmentdomain.Fact{}, false, fmt.Errorf("%w: assignment observation time is required", ErrInvalidObservation)
	}
	fact, err := experiment.Assign(observation.SubjectKey, observedAt)
	if err != nil {
		return assignmentdomain.Fact{}, false, err
	}
	if fact.Variant != observation.Variant {
		return assignmentdomain.Fact{}, false, fmt.Errorf("%w: assignment observation does not match canonical bucket", ErrInvalidObservation)
	}
	return f.sink.Append(ctx, fact)
}

func (f *Facade) Get(ctx context.Context, experimentID, subjectKey string) (assignmentdomain.Fact, error) {
	experiment, err := f.experiments.Load(ctx, experimentID)
	if err != nil {
		return assignmentdomain.Fact{}, err
	}
	return f.reader.Get(ctx, experimentID, experiment.Version, subjectKey)
}

func (f *Facade) Stats(ctx context.Context, experimentID string) (model.Experiment, assignmentdomain.Stats, error) {
	experiment, err := f.experiments.Load(ctx, experimentID)
	if err != nil {
		return model.Experiment{}, assignmentdomain.Stats{}, err
	}
	stats, err := f.reader.Stats(ctx, experimentID, experiment.Version)
	return experiment, stats, err
}

func (f *Facade) StatsFor(ctx context.Context, experiment model.Experiment) (assignmentdomain.Stats, error) {
	return f.reader.Stats(ctx, experiment.ID, experiment.Version)
}
