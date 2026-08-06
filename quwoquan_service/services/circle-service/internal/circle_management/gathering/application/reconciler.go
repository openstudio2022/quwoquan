package gathering

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"strings"
	"sync"
	"time"

	gatheringevent "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/event"
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
	if value.RoomBindingStatus == model.GatheringRoomBindingStatusReady {
		if strings.TrimSpace(value.ConversationID) == "" {
			return fmt.Errorf("Gathering %s has ready room binding without conversationId", value.ID)
		}
	}
	if value.RoomBindingStatus != model.GatheringRoomBindingStatusPending &&
		value.RoomBindingStatus != model.GatheringRoomBindingStatusFailed &&
		value.RoomBindingStatus != model.GatheringRoomBindingStatusReady {
		return fmt.Errorf(
			"Gathering %s has unsupported room binding status %q",
			value.ID,
			value.RoomBindingStatus,
		)
	}

	accessMode, postingPolicy := gatheringConversationPolicy(value)
	sourceEventID := fmt.Sprintf("gathering:%s:room:v%d", value.ID, value.Version)
	conversationID, ensureErr := reconciler.conversations.EnsureGatheringConversation(
		ctx,
		ports.EnsureGatheringConversationCommand{
			GatheringID:    value.ID,
			SourceEventID:  sourceEventID,
			SourceVersion:  value.Version,
			OwnerPersonaID: primaryOrganizerPersonaID(value),
			Title:          value.Purpose.Title,
			AccessMode:     accessMode,
			PostingPolicy:  postingPolicy,
		},
	)
	if ensureErr != nil {
		if value.RoomBindingStatus == model.GatheringRoomBindingStatusPending {
			if _, commitErr := reconciler.commitSystem(
				ctx,
				value,
				fmt.Sprintf("room-failed:%d", value.Version),
				gatheringevent.GatheringRoomBindingChanged,
				func(current *model.Gathering) (model.Gathering, error) {
					return model.MarkGatheringRoomFailed(*current, now)
				},
			); commitErr != nil {
				return errors.Join(ensureErr, commitErr)
			}
		}
		return ensureErr
	}
	if value.RoomBindingStatus == model.GatheringRoomBindingStatusReady {
		if value.ConversationID != conversationID {
			return fmt.Errorf(
				"Gathering %s room projection rebound from %s to %s",
				value.ID,
				value.ConversationID,
				conversationID,
			)
		}
	} else {
		committed, err := reconciler.commitSystem(
			ctx,
			value,
			fmt.Sprintf("room-ready:%d:%s", value.Version, conversationID),
			gatheringevent.GatheringRoomBindingChanged,
			func(current *model.Gathering) (model.Gathering, error) {
				return model.MarkGatheringRoomReady(*current, conversationID, now)
			},
		)
		if err != nil {
			return err
		}
		value = committed
	}
	if err := reconciler.projectMemberships(ctx, value); err != nil {
		return err
	}
	return reconciler.candidates.SaveReconciliationCheckpoint(ctx, value.ID, value.Version, now)
}

func (reconciler *Reconciler) projectMemberships(
	ctx context.Context,
	value model.Gathering,
) error {
	for _, assignment := range value.OrganizerAssignments {
		state := "active"
		if !assignment.RevokedAt.IsZero() {
			state = "revoked"
		}
		sourceEventID := fmt.Sprintf(
			"gathering:%s:organizer:%s:v%d",
			value.ID,
			assignment.PersonaID,
			assignment.Version,
		)
		if err := reconciler.conversations.ProjectGatheringMembership(
			ctx,
			ports.ProjectGatheringMembershipCommand{
				GatheringID:   value.ID,
				PersonaID:     assignment.PersonaID,
				SourceEventID: sourceEventID,
				SourceVersion: assignment.Version,
				SourceType:    "organizer_assignment",
				State:         state,
			},
		); err != nil {
			return err
		}
	}
	for _, participation := range value.Participations {
		state := "closed"
		if participation.State == model.ParticipationStateActive {
			state = "active"
		}
		sourceEventID := fmt.Sprintf(
			"gathering:%s:participation:%s:v%d",
			value.ID,
			participation.PersonaID,
			participation.Version,
		)
		if err := reconciler.conversations.ProjectGatheringMembership(
			ctx,
			ports.ProjectGatheringMembershipCommand{
				GatheringID:   value.ID,
				PersonaID:     participation.PersonaID,
				SourceEventID: sourceEventID,
				SourceVersion: participation.Version,
				SourceType:    "participation",
				State:         state,
			},
		); err != nil {
			return err
		}
	}
	return nil
}

func gatheringConversationPolicy(value model.Gathering) (string, string) {
	if value.LifecycleStatus == model.GatheringLifecycleStatusCancelled ||
		value.LifecycleStatus == model.GatheringLifecycleStatusCompleted {
		return "read_only", "announcements_only"
	}
	return "active", "member_chat"
}

func primaryOrganizerPersonaID(value model.Gathering) string {
	for _, assignment := range value.OrganizerAssignments {
		if assignment.Role == "primary_organizer" && assignment.RevokedAt.IsZero() {
			return strings.TrimSpace(assignment.PersonaID)
		}
	}
	return strings.TrimSpace(value.CreatedByPersonaID)
}

func (reconciler *Reconciler) commitSystem(
	ctx context.Context,
	value model.Gathering,
	action string,
	eventType string,
	mutate ports.Mutation,
) (model.Gathering, error) {
	receiptKey := fmt.Sprintf(
		"system:gathering-reconcile:%s:%d:%s",
		value.ID,
		value.Version,
		action,
	)
	digest := sha256.Sum256([]byte(receiptKey))
	receipt, err := reconciler.store.Commit(ctx, ports.CommitRequest{
		GatheringID: value.ID, ReceiptKey: receiptKey,
		CommandDigest: hex.EncodeToString(digest[:]), ReceiptExpiresAt: reconciler.now().UTC().Add(lifecycleReceiptRetention),
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
