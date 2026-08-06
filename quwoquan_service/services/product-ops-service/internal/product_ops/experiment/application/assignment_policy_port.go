package experiment

import (
	"context"
	"time"

	"quwoquan_service/services/product-ops-service/internal/product_ops/experiment/domain/model"
	assignmentdomain "quwoquan_service/services/product-ops-service/internal/product_ops/experiment_assignment_fact/domain"
)

// ErrAssignmentPolicyNotFound is the public application-level identity for a
// missing Experiment policy. Consumers must not import Experiment's domain or
// persistence packages to classify this failure.
var ErrAssignmentPolicyNotFound = model.ErrNotFound

// AssignmentPolicySnapshot is the minimum Experiment state that a sibling
// object's application layer may consume. It deliberately excludes aggregate
// mutation methods and persistence details.
type AssignmentPolicySnapshot struct {
	ID       string
	Revision int64
	Status   string
}

// AssignmentPolicyPort is Experiment's public application port for the
// ExperimentAssignmentFact object. It owns revision lookup and deterministic
// bucketing so the consumer never imports Experiment's domain/private adapters.
type AssignmentPolicyPort interface {
	CurrentAssignmentPolicy(context.Context, string) (AssignmentPolicySnapshot, error)
	ResolveAssignment(
		context.Context,
		string,
		int64,
		string,
		time.Time,
	) (assignmentdomain.Fact, error)
}

func (f *Facade) CurrentAssignmentPolicy(
	ctx context.Context,
	experimentID string,
) (AssignmentPolicySnapshot, error) {
	experiment, err := f.store.Load(ctx, experimentID)
	if err != nil {
		return AssignmentPolicySnapshot{}, err
	}
	return AssignmentPolicySnapshot{
		ID:       experiment.ID,
		Revision: experiment.Version,
		Status:   experiment.Status,
	}, nil
}

func (f *Facade) ResolveAssignment(
	ctx context.Context,
	experimentID string,
	experimentRevision int64,
	subjectKey string,
	observedAt time.Time,
) (assignmentdomain.Fact, error) {
	experiment, err := f.store.LoadRevision(ctx, experimentID, experimentRevision)
	if err != nil {
		return assignmentdomain.Fact{}, err
	}
	return experiment.Assign(subjectKey, observedAt)
}

var _ AssignmentPolicyPort = (*Facade)(nil)
