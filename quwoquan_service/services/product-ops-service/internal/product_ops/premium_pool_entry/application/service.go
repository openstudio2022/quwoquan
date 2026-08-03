package application

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"strings"
	"time"

	"quwoquan_service/services/product-ops-service/internal/product_ops/premium_pool_entry/domain/model"
	"quwoquan_service/services/product-ops-service/internal/product_ops/premium_pool_entry/domain/ports"
)

const (
	IntentUpsert   = "upsert"
	IntentRollback = "rollback"
	IntentTakedown = "takedown"

	EventUpserted        = "PremiumPoolEntryUpserted"
	EventRolledBack      = "PremiumPoolEntryRolledBack"
	EventTakedownEjected = "PremiumPoolEntryTakedownEjected"
)

type UpsertCommand struct {
	ContentID        string
	Scope            string
	QualityScore     float64
	QualityAdmission string
	SupplySource     string
	SourceTaskID     string
	AuditID          string
	RollbackToken    string
	ExpiresAt        time.Time
	Context          ports.CommandContext
}

type EntryView struct {
	ContentID        string  `json:"contentId"`
	Scope            string  `json:"scope"`
	Status           string  `json:"status"`
	QualityScore     float64 `json:"qualityScore"`
	QualityAdmission string  `json:"qualityAdmission"`
	SupplySource     string  `json:"supplySource,omitempty"`
	SourceTaskID     string  `json:"sourceTaskId,omitempty"`
	AuditID          string  `json:"auditId"`
	RollbackToken    string  `json:"rollbackToken"`
	FeaturedAt       string  `json:"featuredAt"`
	ExpiresAt        string  `json:"expiresAt"`
	TakedownEjected  bool    `json:"takedownEjected"`
	Revision         int64   `json:"revision"`
	UpdatedAt        string  `json:"updatedAt"`
}

type MutationReceiptView struct {
	ObjectType     string `json:"objectType"`
	ObjectID       string `json:"objectId"`
	Intent         string `json:"intent"`
	PayloadDigest  string `json:"payloadDigest"`
	IdempotencyKey string `json:"idempotencyKey"`
	CommittedAt    string `json:"committedAt"`
	Replayed       bool   `json:"replayed"`
}

type TakedownResult struct {
	Entry          EntryView            `json:"entry"`
	ApprovalCount  int                  `json:"approvalCount"`
	ApprovalState  string               `json:"approvalState"`
	Pending        bool                 `json:"pending"`
	PayloadDigest  string               `json:"payloadDigest"`
	ApproverActors []string             `json:"approverActors"`
	Receipt        *MutationReceiptView `json:"receipt,omitempty"`
}

type Service struct {
	store ports.Store
	now   func() time.Time
}

func NewService(store ports.Store) *Service {
	if store == nil {
		panic("PremiumPoolEntry service requires a store")
	}
	return &Service{store: store, now: time.Now}
}

func (service *Service) List(ctx context.Context, activeOnly bool) ([]EntryView, error) {
	entries, err := service.store.List(ctx)
	if err != nil {
		return nil, err
	}
	now := service.now().UTC()
	out := make([]EntryView, 0, len(entries))
	for _, entry := range entries {
		if activeOnly && !entry.ActiveAt(now) {
			continue
		}
		out = append(out, viewFromEntry(entry))
	}
	sort.Slice(out, func(i, j int) bool { return out[i].UpdatedAt > out[j].UpdatedAt })
	return out, nil
}

func (service *Service) Upsert(ctx context.Context, command UpsertCommand) (EntryView, error) {
	if err := validateCommandContext(command.Context); err != nil {
		return EntryView{}, err
	}
	commandDigest := stableDigest(struct {
		Intent  string        `json:"intent"`
		ActorID string        `json:"actorId"`
		Input   UpsertCommand `json:"input"`
	}{Intent: IntentUpsert, ActorID: command.Context.ActorID, Input: commandWithoutContext(command)})
	contentID := strings.TrimSpace(command.ContentID)
	if contentID == "" {
		return EntryView{}, model.ErrInvalidArgument
	}
	if replay, found, err := service.store.Replay(ctx, contentID, command.Context.IdempotencyKey); err != nil {
		return EntryView{}, err
	} else if found {
		if replay.Intent != IntentUpsert || replay.CommandDigest != commandDigest {
			return EntryView{}, model.ErrIdempotencyConflict
		}
		return viewFromEntry(replay.Entry), nil
	}
	current, found, err := service.store.Load(ctx, contentID)
	if err != nil {
		return EntryView{}, err
	}
	var currentRef *model.Entry
	expectedRevision := int64(0)
	if found {
		currentRef = &current
		expectedRevision = current.Revision
	}
	next, err := model.Upsert(currentRef, model.UpsertInput{
		ContentID: contentID, Scope: command.Scope, QualityScore: command.QualityScore,
		QualityAdmission: command.QualityAdmission, SupplySource: command.SupplySource,
		SourceTaskID: command.SourceTaskID, AuditID: command.AuditID,
		RollbackToken: command.RollbackToken, ExpiresAt: command.ExpiresAt,
	}, service.now().UTC())
	if err != nil {
		return EntryView{}, err
	}
	receipt, err := service.store.Commit(ctx, ports.ChangeSet{
		Entry: next, ExpectedRevision: expectedRevision, Intent: IntentUpsert,
		CommandDigest: commandDigest, Context: command.Context, Before: currentRef,
		Event: eventFor(EventUpserted, next, command.Context.IdempotencyKey, commandDigest),
	})
	if err != nil {
		return EntryView{}, err
	}
	return viewFromEntry(receipt.Entry), nil
}

func (service *Service) Rollback(
	ctx context.Context,
	contentID string,
	commandContext ports.CommandContext,
) (EntryView, error) {
	if err := validateCommandContext(commandContext); err != nil {
		return EntryView{}, err
	}
	contentID = strings.TrimSpace(contentID)
	if contentID == "" {
		return EntryView{}, model.ErrInvalidArgument
	}
	if replay, found, err := service.store.Replay(ctx, contentID, commandContext.IdempotencyKey); err != nil {
		return EntryView{}, err
	} else if found {
		if replay.Intent != IntentRollback {
			return EntryView{}, model.ErrIdempotencyConflict
		}
		return viewFromEntry(replay.Entry), nil
	}
	current, found, err := service.store.Load(ctx, contentID)
	if err != nil {
		return EntryView{}, err
	}
	if !found {
		return EntryView{}, model.ErrNotFound
	}
	next, err := current.Rollback(service.now().UTC())
	if err != nil {
		return EntryView{}, err
	}
	commandDigest := stableDigest(struct {
		Intent    string `json:"intent"`
		ActorID   string `json:"actorId"`
		ContentID string `json:"contentId"`
		Revision  int64  `json:"revision"`
	}{Intent: IntentRollback, ActorID: commandContext.ActorID, ContentID: current.ContentID, Revision: current.Revision})
	receipt, err := service.store.Commit(ctx, ports.ChangeSet{
		Entry: next, ExpectedRevision: current.Revision, Intent: IntentRollback,
		CommandDigest: commandDigest, Context: commandContext, Before: &current,
		Event: eventFor(EventRolledBack, next, commandContext.IdempotencyKey, commandDigest),
	})
	if err != nil {
		return EntryView{}, err
	}
	return viewFromEntry(receipt.Entry), nil
}

func (service *Service) Takedown(
	ctx context.Context,
	contentID string,
	commandContext ports.CommandContext,
) (TakedownResult, error) {
	if err := validateCommandContext(commandContext); err != nil {
		return TakedownResult{}, err
	}
	contentID = strings.TrimSpace(contentID)
	if contentID == "" {
		return TakedownResult{}, model.ErrInvalidArgument
	}
	if replay, found, err := service.store.Replay(ctx, contentID, commandContext.IdempotencyKey); err != nil {
		return TakedownResult{}, err
	} else if found {
		if replay.Intent != IntentTakedown || replay.ApprovalDigest == "" {
			return TakedownResult{}, model.ErrIdempotencyConflict
		}
		approvals, err := service.store.ListApprovals(
			ctx, contentID, replay.ApprovalDigest, IntentTakedown, replay.Entry.Revision-1,
		)
		if err != nil {
			return TakedownResult{}, err
		}
		actors := distinctActors(approvals)
		receiptView := receiptView(replay)
		return TakedownResult{
			Entry: viewFromEntry(replay.Entry), ApprovalCount: len(actors),
			ApprovalState: "approved", Pending: false,
			PayloadDigest: replay.ApprovalDigest, ApproverActors: actors,
			Receipt: &receiptView,
		}, nil
	}
	current, found, err := service.store.Load(ctx, contentID)
	if err != nil {
		return TakedownResult{}, err
	}
	if !found {
		return TakedownResult{}, model.ErrNotFound
	}
	if current.Status != model.StatusActive {
		return TakedownResult{}, model.ErrInvalidTransition
	}
	payloadDigest := stableDigest(struct {
		Intent string    `json:"intent"`
		Entry  EntryView `json:"entry"`
	}{Intent: IntentTakedown, Entry: viewFromEntry(current)})
	approval := ports.Approval{
		ContentID: current.ContentID, PayloadDigest: payloadDigest,
		Decision: IntentTakedown, ActorID: commandContext.ActorID,
		Revision: current.Revision, ApprovedAt: service.now().UTC(),
	}
	if err := service.store.RecordApproval(ctx, approval); err != nil {
		return TakedownResult{}, err
	}
	approvals, err := service.store.ListApprovals(
		ctx, current.ContentID, payloadDigest, IntentTakedown, current.Revision,
	)
	if err != nil {
		return TakedownResult{}, err
	}
	actors := distinctActors(approvals)
	result := TakedownResult{
		Entry: viewFromEntry(current), ApprovalCount: len(actors),
		ApprovalState: "pending_second_principal", Pending: true,
		PayloadDigest: payloadDigest, ApproverActors: actors,
	}
	if len(actors) < 2 {
		return result, nil
	}
	next, err := current.Takedown(service.now().UTC())
	if err != nil {
		return TakedownResult{}, err
	}
	commandDigest := stableDigest(struct {
		Intent        string `json:"intent"`
		ContentID     string `json:"contentId"`
		Revision      int64  `json:"revision"`
		PayloadDigest string `json:"payloadDigest"`
	}{Intent: IntentTakedown, ContentID: current.ContentID, Revision: current.Revision, PayloadDigest: payloadDigest})
	receipt, err := service.store.Commit(ctx, ports.ChangeSet{
		Entry: next, ExpectedRevision: current.Revision, Intent: IntentTakedown,
		CommandDigest: commandDigest, Context: commandContext, Before: &current,
		ApprovalDigest: payloadDigest, RequireDualApproval: true,
		Event: eventFor(EventTakedownEjected, next, commandContext.IdempotencyKey, commandDigest),
	})
	if err != nil {
		return TakedownResult{}, err
	}
	receiptView := receiptView(receipt)
	result.Entry = viewFromEntry(receipt.Entry)
	result.ApprovalState = "approved"
	result.Pending = false
	result.Receipt = &receiptView
	return result, nil
}

func validateCommandContext(commandContext ports.CommandContext) error {
	actorID := strings.TrimSpace(commandContext.ActorID)
	idempotencyKey := strings.TrimSpace(commandContext.IdempotencyKey)
	if actorID == "" || actorID == "unverified" || idempotencyKey == "" || len(idempotencyKey) > 160 {
		return model.ErrInvalidArgument
	}
	return nil
}

func commandWithoutContext(command UpsertCommand) UpsertCommand {
	command.Context = ports.CommandContext{}
	return command
}

func stableDigest(value any) string {
	payload, _ := json.Marshal(value)
	return fmt.Sprintf("%x", sha256.Sum256(payload))
}

func eventFor(eventType string, entry model.Entry, idempotencyKey, commandDigest string) ports.Event {
	eventSeed := sha256.Sum256([]byte(strings.Join([]string{
		eventType, entry.ContentID, idempotencyKey, commandDigest,
	}, "\x1f")))
	return ports.Event{
		ID: "premium_pool_" + fmt.Sprintf("%x", eventSeed[:16]), Type: eventType,
		AggregateID: entry.ContentID, Payload: eventPayload(entry), OccurredAt: entry.UpdatedAt,
	}
}

func eventPayload(entry model.Entry) map[string]any {
	payload, _ := json.Marshal(viewFromEntry(entry))
	var out map[string]any
	_ = json.Unmarshal(payload, &out)
	return out
}

func viewFromEntry(entry model.Entry) EntryView {
	return EntryView{
		ContentID: entry.ContentID, Scope: entry.Scope,
		Status: string(entry.Status), QualityScore: entry.QualityScore,
		QualityAdmission: entry.QualityAdmission, SupplySource: entry.SupplySource,
		SourceTaskID: entry.SourceTaskID, AuditID: entry.AuditID,
		RollbackToken:   entry.RollbackToken,
		FeaturedAt:      entry.FeaturedAt.UTC().Format(time.RFC3339),
		ExpiresAt:       entry.ExpiresAt.UTC().Format(time.RFC3339),
		TakedownEjected: entry.TakedownEjected(), Revision: entry.Revision,
		UpdatedAt: entry.UpdatedAt.UTC().Format(time.RFC3339),
	}
}

func receiptView(receipt ports.CommitReceipt) MutationReceiptView {
	return MutationReceiptView{
		ObjectType: "premium_pool_entry", ObjectID: receipt.Entry.ContentID,
		Intent: receipt.Intent, PayloadDigest: receipt.CommandDigest,
		IdempotencyKey: receipt.IdempotencyKey,
		CommittedAt:    receipt.CommittedAt.UTC().Format(time.RFC3339Nano),
		Replayed:       receipt.Replayed,
	}
}

func distinctActors(approvals []ports.Approval) []string {
	seen := make(map[string]struct{}, len(approvals))
	for _, approval := range approvals {
		actorID := strings.TrimSpace(approval.ActorID)
		if actorID != "" && actorID != "unverified" {
			seen[actorID] = struct{}{}
		}
	}
	out := make([]string, 0, len(seen))
	for actorID := range seen {
		out = append(out, actorID)
	}
	sort.Strings(out)
	return out
}

func IsUserConflict(err error) bool {
	return errors.Is(err, model.ErrRevisionConflict) ||
		errors.Is(err, model.ErrIdempotencyConflict) ||
		errors.Is(err, model.ErrInvalidTransition) ||
		errors.Is(err, model.ErrDualApprovalRequired)
}
