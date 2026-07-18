package ports

import (
	"context"
	"time"

	"quwoquan_service/services/user-service/internal/domain/persona/profile_update_proposal/model"
)

type ChangeSet struct {
	Proposal       model.ProfileUpdateProposal
	Events         []model.Event
	IdempotencyKey string
	CommandDigest  string
}

type CommitReceipt struct {
	ProposalID string `json:"proposalId"`
	Version    int64  `json:"version"`
	Status     string `json:"status"`
	Replayed   bool   `json:"replayed"`
}

type AggregateStore interface {
	Load(context.Context, string) (model.ProfileUpdateProposal, error)
	Replay(context.Context, string, string, string) (CommitReceipt, bool, error)
	RecordNoopReceipt(
		context.Context,
		model.ProfileUpdateProposal,
		string,
		string,
	) (CommitReceipt, error)
	Commit(context.Context, int64, ChangeSet) (CommitReceipt, error)
}

type Cursor struct {
	CreatedAt time.Time
	ID        string
}

type Slice struct {
	Items      []model.ProfileUpdateProposal
	NextCursor *Cursor
}

type Reader interface {
	Get(context.Context, string) (model.ProfileUpdateProposal, error)
	ListByPersona(context.Context, string, *Cursor, int) (Slice, error)
}
