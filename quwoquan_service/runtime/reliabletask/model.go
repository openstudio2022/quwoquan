package reliabletask

import "time"

const (
	TaskOutboxStatusPending     = "pending"
	TaskOutboxStatusDispatching = "dispatching"
	TaskOutboxStatusDispatched  = "dispatched"
	TaskOutboxStatusFailed      = "failed"
	TaskOutboxStatusCancelled   = "cancelled"

	TaskStatusReady      = "ready"
	TaskStatusProcessing = "processing"
	TaskStatusRetryWait  = "retry_wait"
	TaskStatusSucceeded  = "succeeded"
	TaskStatusDead       = "dead"

	NotificationStatusPending    = "pending"
	NotificationStatusProcessing = "processing"
	NotificationStatusSucceeded  = "succeeded"
	NotificationStatusRetryWait  = "retry_wait"
	NotificationStatusDead       = "dead"

	RecipientStatusPending   = "pending"
	RecipientStatusDelivered = "delivered"
	RecipientStatusFailed    = "failed"
)

type RuntimeFailure struct {
	Code       string            `bson:"code" json:"code"`
	Message    string            `bson:"message" json:"message"`
	Attributes map[string]string `bson:"attributes,omitempty" json:"attributes,omitempty"`
}

type RetryPolicy struct {
	MaxAttempts int
	Backoff     []time.Duration
}

func DefaultRetryPolicy() RetryPolicy {
	return RetryPolicy{
		MaxAttempts: 5,
		Backoff: []time.Duration{
			200 * time.Millisecond,
			500 * time.Millisecond,
			time.Second,
			2 * time.Second,
			5 * time.Second,
		},
	}
}

func (p RetryPolicy) NextDelay(attempt int) (time.Duration, bool) {
	if p.MaxAttempts <= 0 {
		p.MaxAttempts = DefaultRetryPolicy().MaxAttempts
	}
	if attempt >= p.MaxAttempts {
		return 0, false
	}
	if len(p.Backoff) == 0 {
		p.Backoff = DefaultRetryPolicy().Backoff
	}
	idx := attempt - 1
	if idx < 0 {
		idx = 0
	}
	if idx >= len(p.Backoff) {
		idx = len(p.Backoff) - 1
	}
	return p.Backoff[idx], true
}

type DeclareTaskRequest struct {
	TaskType        string
	OwnerDomain     string
	AggregateType   string
	AggregateID     string
	DedupeKey       string
	IdempotencyKey  string
	PartitionKey    string
	ShardID         int
	Payload         map[string]string
	PayloadAllow    []string
	Trigger         string
	StartAt         time.Time
	MaxDelayUntil   time.Time
	MergeWindow     time.Duration
	CreatedByModule string
}

type TaskOutboxRecord struct {
	OutboxID         string            `bson:"_id" json:"outboxId"`
	TaskType         string            `bson:"taskType" json:"taskType"`
	OwnerDomain      string            `bson:"ownerDomain" json:"ownerDomain"`
	AggregateType    string            `bson:"aggregateType" json:"aggregateType"`
	AggregateID      string            `bson:"aggregateId" json:"aggregateId"`
	DedupeKey        string            `bson:"dedupeKey" json:"dedupeKey"`
	IdempotencyKey   string            `bson:"idempotencyKey" json:"idempotencyKey"`
	PartitionKey     string            `bson:"partitionKey" json:"partitionKey"`
	ShardID          int               `bson:"shardId" json:"shardId"`
	Payload          map[string]string `bson:"payload" json:"payload"`
	Trigger          string            `bson:"trigger" json:"trigger"`
	Status           string            `bson:"status" json:"status"`
	StartAt          time.Time         `bson:"startAt" json:"startAt"`
	MaxDelayUntil    time.Time         `bson:"maxDelayUntil" json:"maxDelayUntil"`
	CreatedByModule  string            `bson:"createdByModule" json:"createdByModule"`
	CreatedAt        time.Time         `bson:"createdAt" json:"createdAt"`
	UpdatedAt        time.Time         `bson:"updatedAt" json:"updatedAt"`
	DispatchAttempts int               `bson:"dispatchAttempts" json:"dispatchAttempts"`
	LastFailure      *RuntimeFailure   `bson:"lastFailure,omitempty" json:"lastFailure,omitempty"`
}

type ReliableAsyncTask struct {
	TaskID         string            `bson:"_id" json:"taskId"`
	OutboxID       string            `bson:"outboxId" json:"outboxId"`
	TaskType       string            `bson:"taskType" json:"taskType"`
	OwnerDomain    string            `bson:"ownerDomain" json:"ownerDomain"`
	AggregateType  string            `bson:"aggregateType" json:"aggregateType"`
	AggregateID    string            `bson:"aggregateId" json:"aggregateId"`
	DedupeKey      string            `bson:"dedupeKey" json:"dedupeKey"`
	IdempotencyKey string            `bson:"idempotencyKey" json:"idempotencyKey"`
	PartitionKey   string            `bson:"partitionKey" json:"partitionKey"`
	ShardID        int               `bson:"shardId" json:"shardId"`
	Payload        map[string]string `bson:"payload" json:"payload"`
	Status         string            `bson:"status" json:"status"`
	Attempts       int               `bson:"attempts" json:"attempts"`
	NextAttemptAt  time.Time         `bson:"nextAttemptAt" json:"nextAttemptAt"`
	LeaseOwner     string            `bson:"leaseOwner,omitempty" json:"leaseOwner,omitempty"`
	LeaseToken     string            `bson:"leaseToken,omitempty" json:"leaseToken,omitempty"`
	LeaseUntil     time.Time         `bson:"leaseUntil,omitempty" json:"leaseUntil,omitempty"`
	CreatedAt      time.Time         `bson:"createdAt" json:"createdAt"`
	UpdatedAt      time.Time         `bson:"updatedAt" json:"updatedAt"`
	LastFailure    *RuntimeFailure   `bson:"lastFailure,omitempty" json:"lastFailure,omitempty"`
}

type NotificationOutboxRecord struct {
	NotificationID string            `bson:"_id" json:"notificationId"`
	EventType      string            `bson:"eventType" json:"eventType"`
	OwnerDomain    string            `bson:"ownerDomain" json:"ownerDomain"`
	AggregateType  string            `bson:"aggregateType" json:"aggregateType"`
	AggregateID    string            `bson:"aggregateId" json:"aggregateId"`
	DedupeKey      string            `bson:"dedupeKey" json:"dedupeKey"`
	Payload        map[string]string `bson:"payload" json:"payload"`
	RecipientIDs   []string          `bson:"recipientIds" json:"recipientIds"`
	Status         string            `bson:"status" json:"status"`
	Attempts       int               `bson:"attempts" json:"attempts"`
	NextAttemptAt  time.Time         `bson:"nextAttemptAt" json:"nextAttemptAt"`
	LeaseOwner     string            `bson:"leaseOwner,omitempty" json:"leaseOwner,omitempty"`
	LeaseToken     string            `bson:"leaseToken,omitempty" json:"leaseToken,omitempty"`
	LeaseUntil     time.Time         `bson:"leaseUntil,omitempty" json:"leaseUntil,omitempty"`
	CreatedAt      time.Time         `bson:"createdAt" json:"createdAt"`
	UpdatedAt      time.Time         `bson:"updatedAt" json:"updatedAt"`
	LastFailure    *RuntimeFailure   `bson:"lastFailure,omitempty" json:"lastFailure,omitempty"`
}

type NotificationDeliveryLedgerRecord struct {
	LedgerID       string          `bson:"_id" json:"ledgerId"`
	NotificationID string          `bson:"notificationId" json:"notificationId"`
	EventType      string          `bson:"eventType" json:"eventType"`
	RecipientID    string          `bson:"recipientId" json:"recipientId"`
	Status         string          `bson:"status" json:"status"`
	DeliveredSeq   int64           `bson:"deliveredSeq,omitempty" json:"deliveredSeq,omitempty"`
	Attempts       int             `bson:"attempts" json:"attempts"`
	UpdatedAt      time.Time       `bson:"updatedAt" json:"updatedAt"`
	LastFailure    *RuntimeFailure `bson:"lastFailure,omitempty" json:"lastFailure,omitempty"`
}

type TaskLease struct {
	Env        string    `bson:"env" json:"env"`
	Domain     string    `bson:"domain" json:"domain"`
	Module     string    `bson:"module" json:"module"`
	Owner      string    `bson:"owner" json:"owner"`
	Token      string    `bson:"token" json:"token"`
	ShardID    int       `bson:"shardId" json:"shardId"`
	LeaseUntil time.Time `bson:"leaseUntil" json:"leaseUntil"`
	UpdatedAt  time.Time `bson:"updatedAt" json:"updatedAt"`
}

type ClaimShardLeaseRequest struct {
	Env      string
	Domain   string
	Module   string
	Owner    string
	ShardID  int
	LeaseTTL time.Duration
	Now      time.Time
}
