package reaction

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"quwoquan_service/runtime/commandmeta"
	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
)

const (
	lifecycleCleanupBatchSize = 500
	lifecycleCleanupBudget    = 30 * time.Second
	lifecycleCleanupLease     = lifecycleCleanupBudget + 5*time.Second
)

type LifecycleCleanupScope string

const (
	LifecycleCleanupScopeTarget LifecycleCleanupScope = "target"
	LifecycleCleanupScopeActor  LifecycleCleanupScope = "actor"
)

var (
	ErrLifecycleCleanupDeadline = errors.New("ContentReaction lifecycle cleanup deadline reached")
	ErrLifecycleCleanupLeased   = errors.New("ContentReaction lifecycle cleanup is leased by another worker")
)

type LifecycleCleanupAuthorization struct {
	Source        string
	SourceEventID string
	SourceVersion int64
	Tombstone     string
	OccurredAt    time.Time
}

func (authorization LifecycleCleanupAuthorization) validate() error {
	if strings.TrimSpace(authorization.Source) == "" ||
		strings.TrimSpace(authorization.SourceEventID) == "" ||
		authorization.SourceVersion <= 0 || strings.TrimSpace(authorization.Tombstone) == "" ||
		authorization.OccurredAt.IsZero() {
		return errors.New("ContentReaction lifecycle cleanup authorization is incomplete")
	}
	return nil
}

type LifecycleCleanupJob struct {
	ID            string
	Scope         LifecycleCleanupScope
	Target        reactiondomain.Target
	Actor         reactiondomain.Actor
	Source        string
	SourceEventID string
	SourceVersion int64
	Tombstone     string
	Cursor        string
	Checkpoint    int64
	Deadline      time.Time
	LeaseEpoch    int64
	Completed     bool
}

type LifecycleCleanupJobStore interface {
	Ensure(context.Context, LifecycleCleanupJob) (LifecycleCleanupJob, error)
	Claim(context.Context, string, time.Time, time.Duration) (LifecycleCleanupJob, bool, error)
	Advance(context.Context, string, int64, string, int64, bool) error
}

type LifecycleCleanupMemberReader interface {
	ListActiveReactionsForCleanup(context.Context, LifecycleCleanupJob, int) ([]reactiondomain.Identity, error)
}

type ActorLifecycleCloser interface {
	CloseActorLifecycle(context.Context, reactiondomain.Actor, string) error
	ActorLifecycleClosed(context.Context, reactiondomain.Actor) (bool, error)
}

// LifecycleCleanupPort is deliberately internal. Callers must supply an owner
// lifecycle fact and cannot use a public mutation basis to manufacture cleanup.
type LifecycleCleanupPort interface {
	CleanupTarget(context.Context, reactiondomain.Target, LifecycleCleanupAuthorization) error
	CleanupActor(context.Context, reactiondomain.Actor, LifecycleCleanupAuthorization) error
}

type LifecycleCleanupService struct {
	service   *Service
	members   LifecycleCleanupMemberReader
	jobs      LifecycleCleanupJobStore
	targets   TargetLifecycleCloser
	actors    ActorLifecycleCloser
	now       func() time.Time
	batchSize int
	budget    time.Duration
	lease     time.Duration
}

func NewLifecycleCleanupService(
	service *Service,
	members LifecycleCleanupMemberReader,
	jobs LifecycleCleanupJobStore,
	targets TargetLifecycleCloser,
	actors ActorLifecycleCloser,
) *LifecycleCleanupService {
	return &LifecycleCleanupService{
		service: service, members: members, jobs: jobs, targets: targets, actors: actors,
		now: func() time.Time { return time.Now().UTC() }, batchSize: lifecycleCleanupBatchSize, budget: lifecycleCleanupBudget, lease: lifecycleCleanupLease,
	}
}

// WithExecutionLimitsForTest narrows bounded work in real-engine tests without changing production defaults.
func (cleanup *LifecycleCleanupService) WithExecutionLimitsForTest(batchSize int, budget time.Duration) *LifecycleCleanupService {
	if batchSize > 0 && batchSize <= lifecycleCleanupBatchSize {
		cleanup.batchSize = batchSize
	}
	if budget > 0 {
		cleanup.budget = budget
		cleanup.lease = budget + time.Second
	}
	return cleanup
}

func (cleanup *LifecycleCleanupService) CleanupTarget(ctx context.Context, target reactiondomain.Target, authorization LifecycleCleanupAuthorization) error {
	if err := target.Validate(); err != nil {
		return err
	}
	if err := authorization.validate(); err != nil {
		return err
	}
	if cleanup == nil || cleanup.service == nil || cleanup.members == nil || cleanup.jobs == nil || cleanup.targets == nil {
		return errors.New("ContentReaction target lifecycle cleanup is not configured")
	}
	if err := cleanup.targets.CloseTargetLifecycle(ctx, target, lifecycleCloseSource(authorization)); err != nil {
		return fmt.Errorf("close ContentReaction target lifecycle: %w", err)
	}
	return cleanup.run(ctx, LifecycleCleanupJob{
		ID:    cleanupJobID(LifecycleCleanupScopeTarget, string(target.Kind), target.ID, authorization),
		Scope: LifecycleCleanupScopeTarget, Target: target,
		Source: authorization.Source, SourceEventID: authorization.SourceEventID,
		SourceVersion: authorization.SourceVersion, Tombstone: authorization.Tombstone,
		Deadline: cleanup.now().Add(cleanup.budget),
	})
}

func (cleanup *LifecycleCleanupService) CleanupActor(ctx context.Context, actor reactiondomain.Actor, authorization LifecycleCleanupAuthorization) error {
	if err := actor.Validate(); err != nil {
		return err
	}
	if err := authorization.validate(); err != nil {
		return err
	}
	if cleanup == nil || cleanup.service == nil || cleanup.members == nil || cleanup.jobs == nil || cleanup.actors == nil {
		return errors.New("ContentReaction actor lifecycle cleanup is not configured")
	}
	if err := cleanup.actors.CloseActorLifecycle(ctx, actor, lifecycleCloseSource(authorization)); err != nil {
		return fmt.Errorf("close ContentReaction actor lifecycle: %w", err)
	}
	if closed, err := cleanup.actors.ActorLifecycleClosed(ctx, actor); err != nil || !closed {
		if err != nil {
			return fmt.Errorf("verify ContentReaction actor lifecycle fence: %w", err)
		}
		return errors.New("ContentReaction actor lifecycle fence did not close")
	}
	return cleanup.run(ctx, LifecycleCleanupJob{
		ID:    cleanupJobID(LifecycleCleanupScopeActor, string(actor.Dimension), actor.ID, authorization),
		Scope: LifecycleCleanupScopeActor, Actor: actor,
		Source: authorization.Source, SourceEventID: authorization.SourceEventID,
		SourceVersion: authorization.SourceVersion, Tombstone: authorization.Tombstone,
		Deadline: cleanup.now().Add(cleanup.budget),
	})
}

func (cleanup *LifecycleCleanupService) run(ctx context.Context, seed LifecycleCleanupJob) error {
	job, err := cleanup.jobs.Ensure(ctx, seed)
	if err != nil {
		return err
	}
	if job.Completed {
		return nil
	}
	for cleanup.now().Before(job.Deadline) {
		job, claimed, err := cleanup.jobs.Claim(ctx, job.ID, cleanup.now(), cleanup.lease)
		if err != nil {
			return err
		}
		if !claimed {
			return ErrLifecycleCleanupLeased
		}
		members, err := cleanup.members.ListActiveReactionsForCleanup(ctx, job, cleanup.batchSize)
		if err != nil {
			return err
		}
		if len(members) == 0 {
			return cleanup.jobs.Advance(ctx, job.ID, job.LeaseEpoch, job.Cursor, job.Checkpoint, true)
		}
		cursor := job.Cursor
		for _, identity := range members {
			if cleanup.now().After(job.Deadline) {
				return ErrLifecycleCleanupDeadline
			}
			aggregate, found, err := cleanup.service.data.Aggregate.Load(ctx, identity.AggregateID())
			if err != nil {
				return err
			}
			if !found || aggregate.Value() == reactiondomain.ValueNone {
				continue
			}
			memberVersion := aggregate.Version()
			idempotencyKey := fmt.Sprintf("lifecycle-cleanup:%s:v%d:%s:m%d", job.SourceEventID, job.SourceVersion, identity.AggregateID(), memberVersion)
			commandContext := commandmeta.WithIdempotencyKey(ctx, idempotencyKey)
			if err := cleanup.service.removeForLifecycle(commandContext, identity, memberVersion, job.Source); err != nil {
				return fmt.Errorf("remove ContentReaction %q for %s: %w", identity.AggregateID(), job.Source, err)
			}
			cursor = identity.AggregateID()
		}
		if err := cleanup.jobs.Advance(ctx, job.ID, job.LeaseEpoch, cursor, job.Checkpoint+int64(len(members)), false); err != nil {
			return err
		}
	}
	return ErrLifecycleCleanupDeadline
}

func cleanupJobID(scope LifecycleCleanupScope, dimension, id string, authorization LifecycleCleanupAuthorization) string {
	return fmt.Sprintf("%s:%s:%s:%s:v%d", strings.TrimSpace(authorization.Source), scope, dimension, strings.TrimSpace(id), authorization.SourceVersion)
}

func lifecycleCloseSource(authorization LifecycleCleanupAuthorization) string {
	return fmt.Sprintf("%s:%s:v%d", authorization.Source, authorization.SourceEventID, authorization.SourceVersion)
}
