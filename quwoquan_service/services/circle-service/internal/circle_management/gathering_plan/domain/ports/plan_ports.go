package ports

import (
	"context"
	"encoding/json"
	"time"

	model "quwoquan_service/services/circle-service/internal/circle_management/gathering_plan/domain/model"
)

type GatheringAuthority struct {
	GatheringID         string
	Exists              bool
	CollaborationOpen   bool
	CurrentHost         bool
	ActiveParticipation bool
}

// GatheringAuthorityReader is a live delegated decision from the Gathering
// owner. Plan never persists this result as a role or membership copy.
type GatheringAuthorityReader interface {
	ReadGatheringAuthority(context.Context, string, string) (GatheringAuthority, error)
}

type Mutation func(*model.GatheringPlan) (model.GatheringPlan, model.EventPayload, error)

type CommitRequest struct {
	PlanID           string
	ActorPersonaID   string
	ReceiptKey       string
	CommandDigest    string
	ReceiptExpiresAt time.Time
	EventType        string
	// Authorize runs inside the owner Mongo transaction immediately before
	// state mutation so stale caller claims cannot outlive Gathering authority.
	Authorize func(context.Context) error
	Mutate    Mutation
}

type CommitReceipt struct {
	Result   model.CommandResult
	Replayed bool
}

type AggregateStore interface {
	Load(context.Context, string) (model.GatheringPlan, bool, error)
	Commit(context.Context, CommitRequest) (CommitReceipt, error)
}

type GatheringPlanReader interface {
	ReadByGathering(context.Context, string) (model.GatheringPlan, bool, error)
	ReadByID(context.Context, string) (model.GatheringPlan, bool, error)
	ListRevisions(context.Context, string, string, int) (model.RevisionPage, error)
}

type EventLogRecord struct {
	EventID          string
	EventType        string
	AggregateID      string
	AggregateVersion int64
	Payload          json.RawMessage
	OccurredAt       time.Time
	Sequence         int64
}

type EventLogReader interface {
	ReadEventLogAfter(context.Context, int64, int) ([]EventLogRecord, error)
}
