package ports

import (
	"context"
	"errors"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_subscription/domain/model"
)

var (
	ErrOutboxClaimLost = errors.New("skill subscription outbox claim lost")
	ErrOutboxInvalid   = errors.New("skill subscription outbox input is invalid")
)

// OutboxEvent is a redacted lifecycle envelope. The public subscription event
// contract exposes only subscriptionId; trigger criteria and destination
// details remain inside the aggregate store.
type OutboxEvent struct {
	EventID          string
	EventType        string
	AggregateID      string
	AggregateVersion int64
	Payload          []byte
	OccurredAt       time.Time
	AttemptCount     int
}

type TransactionalOutbox interface {
	ClaimPendingOutbox(
		context.Context,
		string,
		time.Time,
		time.Duration,
	) (OutboxEvent, bool, error)
	MarkOutboxPublished(context.Context, string, string, time.Time) error
	ScheduleOutboxRetry(
		context.Context, string, string, time.Time, time.Time, string,
	) error
}

// Store is the only persistence port allowed to mutate SkillSubscription.
// External commands commit aggregate state, receipt, and outbox atomically;
// delivery methods use the stable delivery identity as their internal fence.
type Store interface {
	GetSkillSubscriptionCommandResult(
		context.Context,
		string,
		string,
		string,
		string,
	) (model.SkillSubscription, bool, error)
	CreateSkillSubscription(
		context.Context,
		string,
		string,
		model.SkillSubscription,
	) (model.SkillSubscription, bool, error)
	GetSkillSubscription(context.Context, string, string) (model.SkillSubscription, error)
	ListSkillSubscriptions(context.Context, string, string, int) ([]model.SkillSubscription, error)
	ListActiveSkillSubscriptionsForDelivery(context.Context, time.Time, int) ([]model.SkillSubscription, error)
	UpdateSkillSubscriptionStatus(
		context.Context,
		string,
		string,
		string,
		*time.Time,
		time.Time,
		string,
		string,
	) (model.SkillSubscription, bool, error)
	BeginSkillSubscriptionDelivery(
		context.Context,
		string,
		string,
		string,
		time.Time,
	) (model.SkillSubscription, bool, error)
	CompleteSkillSubscriptionDelivery(
		context.Context,
		string,
		string,
		string,
		time.Time,
		time.Time,
	) (model.SkillSubscription, error)
	RecordSkillSubscriptionDeliveryFailure(
		context.Context,
		string,
		string,
		string,
		string,
		time.Time,
		time.Time,
	) (model.SkillSubscription, error)
	ClearPendingSkillSubscriptionDelivery(
		context.Context,
		string,
		string,
		string,
		time.Time,
		time.Time,
	) error
}

// ActivityReader and SkillScopedReader are separate read capabilities so
// consumers cannot acquire the mutation Store merely to build a projection or
// execute a bounded owner command fan-out.
type ActivityReader interface {
	ListSkillSubscriptionActivities(
		context.Context,
		string,
		string,
		int,
	) ([]model.ActivityEvent, error)
}

type SkillScopedReader interface {
	ListSkillSubscriptionsBySkill(
		context.Context,
		string,
		string,
		time.Time,
		int,
	) ([]model.SkillSubscription, error)
}
