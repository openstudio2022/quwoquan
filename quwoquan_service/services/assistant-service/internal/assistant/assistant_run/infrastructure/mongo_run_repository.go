package infrastructure

import (
	"context"
	"fmt"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"
	"go.mongodb.org/mongo-driver/v2/mongo/options"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
)

const runJournalRetention = 7 * 24 * time.Hour

type runDocument struct {
	ID              string         `bson:"_id"`
	UserID          string         `bson:"userId"`
	PersonaID       string         `bson:"personaId,omitempty"`
	SessionID       string         `bson:"sessionId"`
	ClientRequestID string         `bson:"clientRequestId"`
	Revision        int64          `bson:"runRevision"`
	State           string         `bson:"status"`
	Snapshot        runruntime.Run `bson:"snapshot"`
	CreatedAt       time.Time      `bson:"createdAt"`
	UpdatedAt       time.Time      `bson:"updatedAt"`
}

type journalDocument struct {
	ID        string         `bson:"_id"`
	RunID     string         `bson:"runId"`
	Sequence  int64          `bson:"seq"`
	Revision  int64          `bson:"runRevision"`
	Kind      string         `bson:"eventType"`
	Payload   map[string]any `bson:"payload"`
	CreatedAt time.Time      `bson:"createdAt"`
	ExpiresAt time.Time      `bson:"expiresAt"`
}

type commandReceiptDocument struct {
	ID            string    `bson:"_id"`
	RunID         string    `bson:"runId"`
	CommandID     string    `bson:"commandId"`
	CommandKind   string    `bson:"commandKind"`
	PayloadDigest string    `bson:"payloadDigest"`
	Revision      int64     `bson:"runRevision"`
	CreatedAt     time.Time `bson:"createdAt"`
}

type leaseDocument struct {
	ID           string    `bson:"_id"`
	LeaseID      string    `bson:"leaseId"`
	WorkerID     string    `bson:"workerId"`
	FencingToken int64     `bson:"fencingToken"`
	AcquiredAt   time.Time `bson:"acquiredAt"`
	HeartbeatAt  time.Time `bson:"heartbeatAt"`
	ExpiresAt    time.Time `bson:"expiresAt"`
}

type workDocument struct {
	ID           string    `bson:"_id"`
	Status       string    `bson:"status"`
	WorkerID     string    `bson:"workerId,omitempty"`
	FencingToken int64     `bson:"fencingToken"`
	AvailableAt  time.Time `bson:"availableAt"`
	ClaimedAt    time.Time `bson:"claimedAt,omitempty"`
	ExpiresAt    time.Time `bson:"expiresAt,omitempty"`
	UpdatedAt    time.Time `bson:"updatedAt"`
}

type terminalOutboxDocument struct {
	ID                    string     `bson:"_id"`
	RunID                 string     `bson:"runId"`
	UserID                string     `bson:"userId"`
	PersonaID             string     `bson:"personaId"`
	PersonaContextVersion *int64     `bson:"personaContextVersion"`
	SessionID             string     `bson:"sessionId"`
	DomainID              string     `bson:"domainId"`
	Outcome               string     `bson:"outcome"`
	ToolsCalled           *[]string  `bson:"toolsCalled"`
	LLMModel              *string    `bson:"llmModel"`
	LLMTokensUsed         *int64     `bson:"llmTokensUsed"`
	LatencyMS             *int64     `bson:"latencyMs"`
	SatisfactionScore     *float64   `bson:"satisfactionScore"`
	OccurredAt            time.Time  `bson:"occurredAt"`
	ClaimOwner            string     `bson:"claimOwner,omitempty"`
	ClaimUntil            *time.Time `bson:"claimUntil,omitempty"`
	NextAttemptAt         *time.Time `bson:"nextAttemptAt,omitempty"`
	AttemptCount          int        `bson:"attemptCount,omitempty"`
	LastErrorCode         string     `bson:"lastErrorCode,omitempty"`
	ProcessedAt           *time.Time `bson:"processedAt,omitempty"`
}

// MongoRunRepository is the authoritative AssistantRun snapshot, ordered
// journal, and worker-lease store. Snapshot and journal changes commit in one
// Mongo transaction so a reconnect never observes a state without its events.
type MongoRunRepository struct {
	runs           *mongo.Collection
	events         *mongo.Collection
	receipts       *mongo.Collection
	leases         *mongo.Collection
	work           *mongo.Collection
	terminalOutbox *mongo.Collection
	hookOutbox     *mongo.Collection
}

func NewMongoRunRepository(database *mongo.Database) *MongoRunRepository {
	if database == nil {
		panic("assistant run database is required")
	}
	return &MongoRunRepository{
		runs:           database.Collection("assistant_runs"),
		events:         database.Collection("assistant_run_events"),
		receipts:       database.Collection("assistant_run_command_receipts"),
		leases:         database.Collection("assistant_run_worker_leases"),
		work:           database.Collection("assistant_run_work_queue"),
		terminalOutbox: database.Collection("assistant_run_terminal_outbox"),
		hookOutbox:     database.Collection("assistant_run_hook_outbox"),
	}
}

func (r *MongoRunRepository) EnsureIndexes(ctx context.Context) error {
	if _, err := r.runs.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys: bson.D{
				{Key: "userId", Value: 1},
				{Key: "sessionId", Value: 1},
				{Key: "clientRequestId", Value: 1},
			},
			Options: options.Index().SetName("uq_runs_client_request").
				SetUnique(true).
				SetPartialFilterExpression(bson.M{
					"clientRequestId": bson.M{"$type": "string"},
				}),
		},
		{
			Keys:    bson.D{{Key: "userId", Value: 1}, {Key: "createdAt", Value: -1}},
			Options: options.Index().SetName("idx_runs_user_created"),
		},
		{
			Keys: bson.D{
				{Key: "userId", Value: 1},
				{Key: "snapshot.frozenPolicySelection.template.skillId", Value: 1},
				{Key: "updatedAt", Value: -1},
			},
			Options: options.Index().SetName("idx_runs_skill_activity"),
		},
		{
			Keys:    bson.D{{Key: "sessionId", Value: 1}, {Key: "createdAt", Value: -1}},
			Options: options.Index().SetName("idx_runs_session"),
		},
		{
			Keys:    bson.D{{Key: "status", Value: 1}, {Key: "createdAt", Value: -1}},
			Options: options.Index().SetName("idx_runs_status"),
		},
	}); err != nil {
		return fmt.Errorf("create assistant run indexes: %w", err)
	}
	if _, err := r.events.Indexes().CreateMany(ctx, []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "runId", Value: 1}, {Key: "seq", Value: 1}},
			Options: options.Index().SetName("uq_run_events_run_seq").SetUnique(true),
		},
		{
			Keys: bson.D{{Key: "expiresAt", Value: 1}},
			Options: options.Index().SetName("idx_run_events_expire").
				SetExpireAfterSeconds(0),
		},
	}); err != nil {
		return fmt.Errorf("create assistant run event indexes: %w", err)
	}
	if _, err := r.receipts.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{
			{Key: "runId", Value: 1},
			{Key: "commandId", Value: 1},
		},
		Options: options.Index().
			SetName("uq_run_command_receipt").
			SetUnique(true),
	}); err != nil {
		return fmt.Errorf("create assistant run command receipt index: %w", err)
	}
	if _, err := r.leases.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys:    bson.D{{Key: "expiresAt", Value: 1}},
		Options: options.Index().SetName("idx_run_worker_lease_expiry"),
	}); err != nil {
		return fmt.Errorf("create assistant run lease indexes: %w", err)
	}
	if _, err := r.work.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{
			{Key: "status", Value: 1},
			{Key: "availableAt", Value: 1},
			{Key: "expiresAt", Value: 1},
		},
		Options: options.Index().SetName("idx_run_work_ready"),
	}); err != nil {
		return fmt.Errorf("create assistant run work queue indexes: %w", err)
	}
	if _, err := r.terminalOutbox.Indexes().CreateOne(ctx, mongo.IndexModel{
		Keys: bson.D{
			{Key: "processedAt", Value: 1},
			{Key: "nextAttemptAt", Value: 1},
			{Key: "claimUntil", Value: 1},
			{Key: "occurredAt", Value: 1},
		},
		Options: options.Index().SetName("idx_run_terminal_outbox_pending"),
	}); err != nil {
		return fmt.Errorf("create assistant run terminal outbox index: %w", err)
	}
	if err := r.ensureHookOutboxIndexes(ctx); err != nil {
		return err
	}
	return nil
}
