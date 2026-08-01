package application_test

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"quwoquan_service/runtime/operation"
	gatheringerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering"
	app "quwoquan_service/services/circle-service/internal/circle_management/gathering/application"
	model "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
	ports "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/ports"
)

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-conversation-binding/spec.md#gwt-002
func TestCreateBindingFailureStaysDraftAndRetryReusesConversation(t *testing.T) {
	store := newMemoryStore()
	chat := &conversationDouble{failEnsure: true}
	facade := app.NewCommandFacade(store, navigableTargetDouble{}, chat)
	facadeTime := time.Date(2026, 8, 1, 8, 0, 0, 0, time.UTC)
	command := createCommand(facadeTime)
	ctx := commandContext("persona-owner", "create-key")

	if _, err := facade.Create(ctx, command); err == nil {
		t.Fatal("Create must surface the conversation binding failure")
	}
	draft := store.mustLoad(t)
	if draft.Status != model.StatusDraft || model.JoinedCount(draft) != 1 {
		t.Fatalf("failed binding fabricated availability: %+v", draft)
	}

	chat.failEnsure = false
	result, err := facade.Create(ctx, command)
	if err != nil {
		t.Fatalf("Create retry: %v", err)
	}
	if result.Status != model.StatusOpen || result.ConversationID != "conversation-gathering" || chat.createdIDs != 1 {
		t.Fatalf("retry result=%+v createdIDs=%d", result, chat.createdIDs)
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-conversation-binding/spec.md#gwt-002
func TestOpenJoinTransportFailureRemainsPendingAndRetryConfirmsWithoutDuplicate(t *testing.T) {
	store := newMemoryStore()
	chat := &conversationDouble{}
	facade := app.NewCommandFacade(store, navigableTargetDouble{}, chat)
	created, err := facade.Create(commandContext("persona-owner", "create-key"), createCommand(time.Now().UTC().Add(time.Hour)))
	if err != nil {
		t.Fatalf("Create: %v", err)
	}
	chat.failAdd = true
	joinContext := commandContext("persona-2", "join-key")
	if _, err := facade.Join(joinContext, app.GatheringCommand{GatheringID: created.GatheringID}); err == nil {
		t.Fatal("Join must surface Chat member failure")
	}
	pending := store.mustLoad(t)
	if stateFor(pending, "persona-2") != model.ParticipantStatePending || model.JoinedCount(pending) != 1 {
		t.Fatalf("failed transport fabricated joined state: %+v", pending.Participants)
	}

	chat.failAdd = false
	joined, err := facade.Join(joinContext, app.GatheringCommand{GatheringID: created.GatheringID})
	if err != nil {
		t.Fatalf("Join retry: %v", err)
	}
	if joined.ParticipantState != model.ParticipantStateJoined || model.JoinedCount(store.mustLoad(t)) != 2 {
		t.Fatalf("retry result = %+v", joined)
	}
	if len(store.mustLoad(t).Participants) != 2 {
		t.Fatal("retry created a duplicate roster row")
	}
}

// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-001
func TestConcurrentJoinReservationsCannotExceedCapacity(t *testing.T) {
	store := newMemoryStore()
	chat := &conversationDouble{}
	facade := app.NewCommandFacade(store, navigableTargetDouble{}, chat)
	command := createCommand(time.Now().UTC().Add(time.Hour))
	command.Capacity = 2
	created, err := facade.Create(commandContext("persona-owner", "create-key"), command)
	if err != nil {
		t.Fatalf("Create: %v", err)
	}

	var wait sync.WaitGroup
	errorsByPersona := make(chan error, 2)
	for _, personaID := range []string{"persona-2", "persona-3"} {
		personaID := personaID
		wait.Add(1)
		go func() {
			defer wait.Done()
			_, joinErr := facade.Join(commandContext(personaID, "join-"+personaID), app.GatheringCommand{GatheringID: created.GatheringID})
			errorsByPersona <- joinErr
		}()
	}
	wait.Wait()
	close(errorsByPersona)
	successes, failures := 0, 0
	for joinErr := range errorsByPersona {
		if joinErr == nil {
			successes++
		} else {
			failures++
		}
	}
	latest := store.mustLoad(t)
	if successes != 1 || failures != 1 || model.JoinedCount(latest) != 2 || latest.Status != model.StatusFull {
		t.Fatalf("successes=%d failures=%d state=%+v", successes, failures, latest)
	}
}

type receiptRecord struct {
	digest    string
	gathering model.Gathering
}

type memoryStore struct {
	mu       sync.Mutex
	value    *model.Gathering
	receipts map[string]receiptRecord
}

func newMemoryStore() *memoryStore {
	return &memoryStore{receipts: map[string]receiptRecord{}}
}

func (store *memoryStore) Load(_ context.Context, gatheringID string) (model.Gathering, bool, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	if store.value == nil || store.value.ID != gatheringID {
		return model.Gathering{}, false, nil
	}
	return clone(*store.value), true, nil
}

func (store *memoryStore) Commit(_ context.Context, request ports.CommitRequest) (ports.CommitReceipt, error) {
	store.mu.Lock()
	defer store.mu.Unlock()
	if receipt, ok := store.receipts[request.ReceiptKey]; ok {
		if receipt.digest != request.CommandDigest {
			return ports.CommitReceipt{}, gatheringerrors.ErrGatheringIdempotencyConflict
		}
		return ports.CommitReceipt{Gathering: clone(receipt.gathering), Replayed: true}, nil
	}
	var current *model.Gathering
	if store.value != nil {
		copy := clone(*store.value)
		current = &copy
	}
	next, err := request.Mutate(current)
	if err != nil {
		return ports.CommitReceipt{}, err
	}
	copy := clone(next)
	store.value = &copy
	store.receipts[request.ReceiptKey] = receiptRecord{digest: request.CommandDigest, gathering: clone(next)}
	return ports.CommitReceipt{Gathering: clone(next)}, nil
}

func (store *memoryStore) mustLoad(t *testing.T) model.Gathering {
	t.Helper()
	store.mu.Lock()
	defer store.mu.Unlock()
	if store.value == nil {
		t.Fatal("Gathering is missing")
	}
	return clone(*store.value)
}

type navigableTargetDouble struct{}

func (navigableTargetDouble) RequireNavigable(_ context.Context, target model.TargetRef) error {
	if target.ObjectID == "" || target.RouteID == "" {
		return errors.New("target is not navigable")
	}
	return nil
}

type conversationDouble struct {
	mu         sync.Mutex
	failEnsure bool
	failAdd    bool
	createdIDs int
}

func (double *conversationDouble) EnsureGroupConversation(_ context.Context, _, _, _, _ string) (string, error) {
	double.mu.Lock()
	defer double.mu.Unlock()
	if double.failEnsure {
		return "", errors.New("chat unavailable")
	}
	if double.createdIDs == 0 {
		double.createdIDs++
	}
	return "conversation-gathering", nil
}

func (double *conversationDouble) AddMember(_ context.Context, _, _, _ string) error {
	double.mu.Lock()
	defer double.mu.Unlock()
	if double.failAdd {
		return errors.New("chat unavailable")
	}
	return nil
}

func (*conversationDouble) RemoveMember(context.Context, string, string, string) error { return nil }

func commandContext(personaID, key string) context.Context {
	return operation.WithContext(context.Background(), operation.Context{
		OperationID: "circle.gathering.command", RequestID: "request-" + key,
		TraceID: "trace-" + key, IdempotencyKey: key,
		Actor: operation.ActorContext{PersonaID: personaID},
	})
}

func createCommand(startAt time.Time) app.CreateCommand {
	return app.CreateCommand{
		Title:     "贡嘎日落同行",
		TargetRef: model.TargetRef{ObjectTypeRef: "photo_spot", ObjectID: "spot-1", RouteID: "gatheringDetail"},
		StartAt:   startAt, Capacity: 3, JoinPolicy: model.JoinPolicyOpen,
	}
}

func stateFor(value model.Gathering, personaID string) model.ParticipantState {
	for _, participant := range value.Participants {
		if participant.PersonaID == personaID {
			return participant.State
		}
	}
	return model.ParticipantState("")
}

func clone(value model.Gathering) model.Gathering {
	value.Participants = append([]model.Participant(nil), value.Participants...)
	return value
}
