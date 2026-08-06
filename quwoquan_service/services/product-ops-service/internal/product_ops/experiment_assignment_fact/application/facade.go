package application

import (
	"context"
	"errors"
	"fmt"
	"time"

	experimentapplication "quwoquan_service/services/product-ops-service/internal/product_ops/experiment/application"
	assignmentdomain "quwoquan_service/services/product-ops-service/internal/product_ops/experiment_assignment_fact/domain"
)

var (
	ErrInvalidObservation = errors.New("experiment assignment observation is invalid")
	ErrExperimentNotFound = errors.New("experiment assignment policy not found")
)

// Facade owns assignment-fact append and read use cases. Experiment is consulted
// only to resolve the current aggregate revision and deterministic variant.
type Facade struct {
	policies experimentapplication.AssignmentPolicyPort
	sink     Sink
	reader   Reader
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

// StatsPort is the public application read port consumed by Experiment's
// catalog HTTP owner. It exposes no assignment persistence implementation.
type StatsPort interface {
	StatsForRevision(context.Context, string, int64) (assignmentdomain.Stats, error)
}

func NewFacade(
	policies experimentapplication.AssignmentPolicyPort,
	sink Sink,
	reader Reader,
) (*Facade, error) {
	if policies == nil || sink == nil || reader == nil {
		return nil, fmt.Errorf("experiment policy port, assignment sink and reader are required")
	}
	return &Facade{policies: policies, sink: sink, reader: reader}, nil
}

// AppendObserved accepts only a runtime observation produced by Recommendation
// or Search. It recomputes the bucket through Experiment's canonical shared
// algorithm before appending, so neither clients nor services can choose a
// private bucket or write against a stale policy revision.
func (f *Facade) AppendObserved(
	ctx context.Context,
	observation AssignmentObservation,
) (assignmentdomain.Fact, bool, error) {
	observedAt := observation.ObservedAt.UTC()
	if observedAt.IsZero() {
		return assignmentdomain.Fact{}, false, fmt.Errorf("%w: assignment observation time is required", ErrInvalidObservation)
	}
	fact, err := f.policies.ResolveAssignment(
		ctx,
		observation.ExperimentID,
		observation.ExperimentRevision,
		observation.SubjectKey,
		observedAt,
	)
	if err != nil {
		return assignmentdomain.Fact{}, false, mapExperimentPolicyError(err)
	}
	if fact.Variant != observation.Variant {
		return assignmentdomain.Fact{}, false, fmt.Errorf("%w: assignment observation does not match canonical bucket", ErrInvalidObservation)
	}
	return f.sink.Append(ctx, fact)
}

func (f *Facade) Get(ctx context.Context, experimentID, subjectKey string) (assignmentdomain.Fact, error) {
	policy, err := f.policies.CurrentAssignmentPolicy(ctx, experimentID)
	if err != nil {
		return assignmentdomain.Fact{}, mapExperimentPolicyError(err)
	}
	return f.reader.Get(ctx, experimentID, policy.Revision, subjectKey)
}

func (f *Facade) Stats(
	ctx context.Context,
	experimentID string,
) (experimentapplication.AssignmentPolicySnapshot, assignmentdomain.Stats, error) {
	policy, err := f.policies.CurrentAssignmentPolicy(ctx, experimentID)
	if err != nil {
		return experimentapplication.AssignmentPolicySnapshot{}, assignmentdomain.Stats{}, mapExperimentPolicyError(err)
	}
	stats, err := f.reader.Stats(ctx, experimentID, policy.Revision)
	return policy, stats, err
}

func (f *Facade) StatsForRevision(
	ctx context.Context,
	experimentID string,
	experimentRevision int64,
) (assignmentdomain.Stats, error) {
	return f.reader.Stats(ctx, experimentID, experimentRevision)
}

func mapExperimentPolicyError(err error) error {
	if errors.Is(err, experimentapplication.ErrAssignmentPolicyNotFound) {
		return fmt.Errorf("%w: %v", ErrExperimentNotFound, err)
	}
	return err
}

var _ StatsPort = (*Facade)(nil)
