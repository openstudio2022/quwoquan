package gathering

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"strings"
	"sync"
	"time"

	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
	ports "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/ports"
)

type Reconciler struct {
	store         ports.AggregateStore
	candidates    ports.ReconciliationStore
	conversations ports.ConversationPort
	now           func() time.Time

	mu          sync.RWMutex
	lastSuccess time.Time
	lastFailure error
}

func NewReconciler(
	store ports.AggregateStore,
	candidates ports.ReconciliationStore,
	conversations ports.ConversationPort,
) *Reconciler {
	if store == nil || candidates == nil || conversations == nil {
		panic("Gathering Reconciler requires aggregate, reconciliation and Chat ports")
	}
	return &Reconciler{
		store: store, candidates: candidates, conversations: conversations, now: time.Now,
	}
}

func (reconciler *Reconciler) ReconcileOnce(ctx context.Context, limit int) (int, error) {
	if limit <= 0 {
		limit = 100
	}
	values, err := reconciler.candidates.ListReconciliationCandidates(ctx, limit)
	if err != nil {
		reconciler.recordFailure(err)
		return 0, err
	}
	for index, value := range values {
		if err := reconciler.reconcile(ctx, value); err != nil {
			reconciler.recordFailure(err)
			return index, fmt.Errorf("reconcile Gathering %s: %w", value.ID, err)
		}
	}
	reconciler.recordSuccess()
	return len(values), nil
}

func (reconciler *Reconciler) Run(ctx context.Context, interval time.Duration) error {
	if interval <= 0 {
		interval = 500 * time.Millisecond
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		if _, err := reconciler.ReconcileOnce(ctx, 100); err != nil && ctx.Err() != nil {
			return ctx.Err()
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-ticker.C:
		}
	}
}

func (reconciler *Reconciler) Healthy(maxStaleness time.Duration) error {
	if maxStaleness <= 0 {
		maxStaleness = 10 * time.Second
	}
	reconciler.mu.RLock()
	defer reconciler.mu.RUnlock()
	if reconciler.lastSuccess.IsZero() {
		return fmt.Errorf("Gathering reconciliation has not completed a scan")
	}
	if reconciler.lastFailure != nil {
		return fmt.Errorf("Gathering reconciliation last failure: %w", reconciler.lastFailure)
	}
	if time.Since(reconciler.lastSuccess) > maxStaleness {
		return fmt.Errorf("Gathering reconciliation heartbeat is stale")
	}
	return nil
}

func (reconciler *Reconciler) reconcile(ctx context.Context, value model.Gathering) error {
	now := reconciler.now().UTC()
	if reevaluated := model.Reevaluate(value, now); reevaluated.Version != value.Version {
		committed, err := reconciler.commitSystem(ctx, value, "expire", "GatheringCompleted", func(current *model.Gathering) (model.Gathering, error) {
			return model.Reevaluate(*current, now), nil
		})
		if err != nil {
			return err
		}
		value = committed
	}
	if strings.TrimSpace(value.ConversationID) == "" {
		conversationID, err := reconciler.conversations.EnsureGroupConversation(
			ctx, value.ID, value.Title, value.CreatorPersonaID, value.Capacity,
			"gathering:"+value.ID+":conversation",
		)
		if err != nil {
			return err
		}
		committed, err := reconciler.commitSystem(ctx, value, "binding:"+conversationID, "GatheringConversationBound", func(current *model.Gathering) (model.Gathering, error) {
			return model.BindConversation(*current, conversationID, now)
		})
		if err != nil {
			return err
		}
		value = committed
	}

	for _, participant := range value.Participants {
		desiredState := ""
		switch {
		case participant.State == model.ParticipantStateJoined:
			desiredState = "joined"
		case participant.State == model.ParticipantStatePending && value.JoinPolicy == model.JoinPolicyOpen:
			desiredState = "joined"
		case participant.State == model.ParticipantStateLeft || participant.State == model.ParticipantStateRejected:
			desiredState = "left"
		default:
			// Approval-pending participants never owned Chat membership; do not
			// advance the Chat watermark with a fabricated leave projection.
			continue
		}
		operationKey := fmt.Sprintf(
			"gathering:%s:reconcile:%d:%s:%s",
			value.ID, value.Version, participant.PersonaID, desiredState,
		)
		if err := reconciler.conversations.ProjectParticipant(
			ctx, value.ID, value.CreatorPersonaID, participant.PersonaID, desiredState,
			membershipSourceSequence(value.Version), operationKey,
		); err != nil {
			return err
		}
		if desiredState == "joined" && participant.State == model.ParticipantStatePending {
			committed, err := reconciler.commitSystem(ctx, value, fmt.Sprintf("confirm:%d:%s", value.Version, participant.PersonaID), "GatheringParticipantStateChanged", func(current *model.Gathering) (model.Gathering, error) {
				return model.ConfirmJoin(*current, participant.PersonaID, now)
			})
			if err != nil {
				return err
			}
			value = committed
		}
	}
	return reconciler.candidates.SaveReconciliationCheckpoint(ctx, value.ID, value.Version, now)
}

func (reconciler *Reconciler) commitSystem(
	ctx context.Context,
	value model.Gathering,
	action string,
	eventType string,
	mutate ports.Mutation,
) (model.Gathering, error) {
	receiptKey := "system:gathering-reconcile:" + value.ID + ":" + action
	digest := sha256.Sum256([]byte(receiptKey))
	receipt, err := reconciler.store.Commit(ctx, ports.CommitRequest{
		GatheringID: value.ID, ReceiptKey: receiptKey,
		CommandDigest: hex.EncodeToString(digest[:]), ReceiptExpiresAt: reconciler.now().UTC().Add(receiptRetention),
		EventType: eventType,
		Mutate: func(current *model.Gathering) (model.Gathering, error) {
			if current == nil {
				return model.Gathering{}, fmt.Errorf("Gathering disappeared during reconciliation")
			}
			return mutate(current)
		},
	})
	if err != nil {
		return model.Gathering{}, err
	}
	return receipt.Gathering, nil
}

func (reconciler *Reconciler) recordSuccess() {
	reconciler.mu.Lock()
	defer reconciler.mu.Unlock()
	reconciler.lastSuccess, reconciler.lastFailure = time.Now().UTC(), nil
}

func (reconciler *Reconciler) recordFailure(err error) {
	reconciler.mu.Lock()
	defer reconciler.mu.Unlock()
	reconciler.lastFailure = err
}
