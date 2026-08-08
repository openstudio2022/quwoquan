package runruntime

import (
	"context"
	"time"
)

type JournalEvent struct {
	EventID   string         `bson:"eventId"`
	RunID     string         `bson:"runId"`
	Sequence  int64          `bson:"sequence"`
	Revision  int64          `bson:"revision"`
	Kind      string         `bson:"kind"`
	Payload   map[string]any `bson:"payload"`
	CreatedAt time.Time      `bson:"createdAt"`
	ExpiresAt time.Time      `bson:"expiresAt"`
}

type CommandReceipt struct {
	RunID         string    `bson:"runId"`
	CommandID     string    `bson:"commandId"`
	CommandKind   string    `bson:"commandKind"`
	PayloadDigest string    `bson:"payloadDigest"`
	Revision      int64     `bson:"revision"`
	CreatedAt     time.Time `bson:"createdAt"`
}

// TerminalRunRecord is the typed, ordered source consumed by read-model
// projectors. SourceCursor fields belong to the AssistantRun store ordering;
// consumers persist them as opaque checkpoints and never query its collection.
type TerminalRunRecord struct {
	Run             Run
	SourceUpdatedAt time.Time
	SourceRunID     string
}

// Repository atomically persists an aggregate snapshot and ordered journal
// events with optimistic CAS. Stream reconnect replays EventsAfter before
// returning the latest snapshot.
type Repository interface {
	Load(context.Context, string) (Run, error)
	LoadByRequest(context.Context, string, string, string) (Run, error)
	LoadCommandReceipt(context.Context, string, string) (CommandReceipt, error)
	Commit(context.Context, int64, Run, []JournalEvent, *CommandReceipt) error
	EventsAfter(context.Context, string, int64, int) ([]JournalEvent, error)
}

type WorkerRepository interface {
	Repository
	// CommitClaim is the only mutation path available to a durable worker. The
	// implementation must validate and write-touch the current work claim in
	// the same transaction as the Run snapshot, journal, receipt, and outbox so
	// an expired worker can never commit after a higher fencing token takes over.
	CommitClaim(
		context.Context,
		WorkClaim,
		int64,
		Run,
		[]JournalEvent,
		*CommandReceipt,
	) error
	LatestSequence(context.Context, string) (int64, error)
}

type WorkClaim struct {
	RunID        string
	WorkerID     string
	FencingToken int64
	ClaimedAt    time.Time
	ExpiresAt    time.Time
}

type WorkQueue interface {
	ClaimNext(context.Context, string, time.Duration) (WorkClaim, error)
	HeartbeatClaim(context.Context, WorkClaim, time.Duration) (WorkClaim, error)
	CompleteClaim(context.Context, WorkClaim, bool, time.Time) error
}

type WorkerLease struct {
	LeaseID      string    `bson:"leaseId"`
	RunID        string    `bson:"runId"`
	WorkerID     string    `bson:"workerId"`
	FencingToken int64     `bson:"fencingToken"`
	AcquiredAt   time.Time `bson:"acquiredAt"`
	HeartbeatAt  time.Time `bson:"heartbeatAt"`
	ExpiresAt    time.Time `bson:"expiresAt"`
}

type LeaseRepository interface {
	Acquire(context.Context, string, string, time.Duration) (WorkerLease, error)
	Heartbeat(context.Context, WorkerLease, time.Duration) (WorkerLease, error)
	Release(context.Context, WorkerLease) error
}
