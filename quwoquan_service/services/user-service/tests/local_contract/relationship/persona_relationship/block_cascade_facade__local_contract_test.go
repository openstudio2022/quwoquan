// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-002.t1
// spec_ref: specs/feature-tree/chat-conversation/contact-and-session-governance/spec.md#sit-002.t3
package local_contract

import (
	"context"
	"errors"
	"testing"

	relationshipapp "quwoquan_service/services/user-service/internal/relationship/persona_relationship/application"
	relmodel "quwoquan_service/services/user-service/internal/relationship/persona_relationship/domain/model"
)

type scriptedBlockStore struct {
	readinessRelationshipStore
	results []relmodel.MutationResult
}

func (store *scriptedBlockStore) Apply(
	_ context.Context,
	command relmodel.Command,
) (relmodel.MutationResult, error) {
	store.commands = append(store.commands, command)
	index := len(store.commands) - 1
	if index >= len(store.results) {
		return relmodel.MutationResult{}, errors.New("unexpected relationship command")
	}
	return store.results[index], nil
}

type recordingGreetingBlockCascade struct {
	pairs [][2]string
}

func (cascade *recordingGreetingBlockCascade) MarkPendingBlockedBetween(
	_ context.Context,
	personaA, personaB string,
) error {
	cascade.pairs = append(cascade.pairs, [2]string{personaA, personaB})
	return nil
}

func changedBlockResult() relmodel.MutationResult {
	return relmodel.MutationResult{
		Changed: true,
		State: relmodel.RelationshipState{
			IsBlocked: true,
		},
		ClearedFollowing: []relmodel.Direction{
			{
				SourcePersonaID: "persona-a",
				TargetPersonaID: "persona-b",
				Following:       false,
			},
			{
				SourcePersonaID: "persona-b",
				TargetPersonaID: "persona-a",
				Following:       false,
			},
		},
		EventName: "PersonaBlocked",
	}
}

func TestChangedBlockCallsGreetingCascadeThroughOwningFacade(t *testing.T) {
	store := &scriptedBlockStore{results: []relmodel.MutationResult{
		changedBlockResult(),
	}}
	greetings := &recordingGreetingBlockCascade{}
	service := relationshipapp.NewPersonaRelationshipService(
		store,
		nil,
		nil,
		greetings,
	)

	result, err := service.Block(
		t.Context(),
		"persona-a",
		"persona-b",
		"block-request",
	)
	if err != nil {
		t.Fatalf("BlockUser: %v", err)
	}
	if !result.Changed || !result.State.IsBlocked || result.EventName != "PersonaBlocked" {
		t.Fatalf("BlockUser result=%+v", result)
	}
	if len(result.ClearedFollowing) != 2 {
		t.Fatalf("cleared follow directions=%d, want 2", len(result.ClearedFollowing))
	}
	for _, direction := range result.ClearedFollowing {
		if direction.Following {
			t.Fatalf("cleared direction still follows: %+v", direction)
		}
	}
	if len(store.commands) != 1 {
		t.Fatalf("relationship commands=%+v", store.commands)
	}
	command := store.commands[0]
	if command.Kind != relmodel.CommandBlock ||
		command.SourcePersonaID != "persona-a" ||
		command.TargetPersonaID != "persona-b" ||
		command.IdempotencyKey != "block-request" {
		t.Fatalf("BlockUser command=%+v", command)
	}
	if len(greetings.pairs) != 1 || greetings.pairs[0] != [2]string{"persona-a", "persona-b"} {
		t.Fatalf("greeting cascade pairs=%+v", greetings.pairs)
	}
}

func TestIdempotentBlockReplayDoesNotRepeatSuccessfulCascade(t *testing.T) {
	store := &scriptedBlockStore{results: []relmodel.MutationResult{
		changedBlockResult(),
		{
			Changed:          false,
			IdempotentReplay: true,
			State: relmodel.RelationshipState{
				IsBlocked: true,
			},
		},
	}}
	greetings := &recordingGreetingBlockCascade{}
	service := relationshipapp.NewPersonaRelationshipService(
		store,
		nil,
		nil,
		greetings,
	)

	if _, err := service.Block(
		t.Context(),
		"persona-a",
		"persona-b",
		"block-request",
	); err != nil {
		t.Fatalf("first BlockUser: %v", err)
	}
	replayed, err := service.Block(
		t.Context(),
		"persona-a",
		"persona-b",
		"block-request",
	)
	if err != nil {
		t.Fatalf("replayed BlockUser: %v", err)
	}
	if replayed.Changed || !replayed.IdempotentReplay || !replayed.State.IsBlocked {
		t.Fatalf("replayed BlockUser result=%+v", replayed)
	}
	if len(greetings.pairs) != 1 {
		t.Fatalf("successful greeting cascade calls=%d, want 1", len(greetings.pairs))
	}
}

func TestUnblockDoesNotCallGreetingCascadeOrRestoreFollowing(t *testing.T) {
	store := &scriptedBlockStore{results: []relmodel.MutationResult{
		{
			Changed:   true,
			State:     relmodel.RelationshipState{},
			EventName: "PersonaUnblocked",
		},
	}}
	greetings := &recordingGreetingBlockCascade{}
	service := relationshipapp.NewPersonaRelationshipService(
		store,
		nil,
		nil,
		greetings,
	)

	result, err := service.Unblock(
		t.Context(),
		"persona-a",
		"persona-b",
		"unblock-request",
	)
	if err != nil {
		t.Fatalf("UnblockUser: %v", err)
	}
	if !result.Changed || result.State.IsBlocked || result.State.IsFollowing ||
		result.EventName != "PersonaUnblocked" {
		t.Fatalf("UnblockUser result=%+v", result)
	}
	if len(store.commands) != 1 || store.commands[0].Kind != relmodel.CommandUnblock {
		t.Fatalf("relationship commands=%+v", store.commands)
	}
	if len(greetings.pairs) != 0 {
		t.Fatalf("UnblockUser greeting cascade pairs=%+v", greetings.pairs)
	}
}
