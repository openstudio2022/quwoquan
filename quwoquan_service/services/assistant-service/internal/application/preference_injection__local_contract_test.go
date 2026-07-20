package application_test

import (
	"context"
	"strings"
	"testing"

	"quwoquan_service/services/assistant-service/internal/application"
	"quwoquan_service/services/assistant-service/internal/domain/assistant"
	preferencemodel "quwoquan_service/services/assistant-service/internal/domain/assistant/preference_fact/model"
	"quwoquan_service/services/assistant-service/internal/infrastructure/persistence"
)

type fixedPreferenceSnapshotReader struct{}

func (fixedPreferenceSnapshotReader) ResolveActiveSnapshots(
	_ context.Context,
	_ string,
	_ string,
) ([]preferencemodel.Snapshot, []preferencemodel.Snapshot, error) {
	return []preferencemodel.Snapshot{
			{
				PreferenceID: "apf_session",
				Scope:        preferencemodel.ScopeSession,
				Kind:         preferencemodel.KindReplyLength,
				Value:        "concise",
				Version:      2,
			},
		}, []preferencemodel.Snapshot{
			{
				PreferenceID: "apf_long_term",
				Scope:        preferencemodel.ScopeLongTerm,
				Kind:         preferencemodel.KindTone,
				Value:        "warm",
				Version:      1,
			},
		}, nil
}

func TestCreateTurnSnapshotsPreferencesWithoutMutatingQuestion(t *testing.T) {
	store := persistence.NewMemoryConversationRunStore()
	service := application.NewAssistantService(
		nil,
		nil,
		nil,
		application.WithConversationRunStore(store),
		application.WithPreferenceSnapshotReader(fixedPreferenceSnapshotReader{}),
	)
	conversation, err := service.CreateConversation(
		t.Context(),
		"persona-owner",
		assistant.CreateConversationInput{ClientRequestID: "create-preference-conversation"},
	)
	if err != nil {
		t.Fatalf("CreateConversation() error = %v", err)
	}
	const question = "请解释今天的安排"
	turn, err := service.CreateTurn(
		t.Context(),
		"persona-owner",
		conversation.ConversationID,
		assistant.CreateTurnInput{
			Input:           assistant.AssistantTurnInput{Text: question},
			ClientRequestID: "create-preference-turn",
		},
	)
	if err != nil {
		t.Fatalf("CreateTurn() error = %v", err)
	}
	if turn.Input.Text != question {
		t.Fatalf("turn question mutated: %q", turn.Input.Text)
	}
	if len(turn.SessionPreferenceFacts) != 1 ||
		turn.SessionPreferenceFacts[0].Value != "concise" {
		t.Fatalf("session preferences = %#v", turn.SessionPreferenceFacts)
	}
	if len(turn.LongTermPreferenceFacts) != 1 ||
		turn.LongTermPreferenceFacts[0].Value != "warm" {
		t.Fatalf("long-term preferences = %#v", turn.LongTermPreferenceFacts)
	}
}

func TestFormatModelPreferencesSessionOverridesLongTerm(t *testing.T) {
	prompt := application.FormatModelPreferencesForPrompt(
		[]preferencemodel.Snapshot{
			{
				Scope: preferencemodel.ScopeSession,
				Kind:  preferencemodel.KindReplyLength,
				Value: "concise",
			},
		},
		[]preferencemodel.Snapshot{
			{
				Scope: preferencemodel.ScopeLongTerm,
				Kind:  preferencemodel.KindReplyLength,
				Value: "detailed",
			},
			{
				Scope: preferencemodel.ScopeLongTerm,
				Kind:  preferencemodel.KindTone,
				Value: "professional",
			},
		},
	)
	if !strings.Contains(prompt, "回答保持简洁") {
		t.Fatalf("prompt missing session preference: %q", prompt)
	}
	if strings.Contains(prompt, "充分细节") {
		t.Fatalf("long-term preference must not override session: %q", prompt)
	}
	if !strings.Contains(prompt, "语气专业准确") {
		t.Fatalf("prompt missing long-term preference: %q", prompt)
	}
}
