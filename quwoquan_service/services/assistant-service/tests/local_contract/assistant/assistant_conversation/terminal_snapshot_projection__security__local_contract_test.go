// spec_ref: specs/feature-tree/assistant-run-learning/run-stream-policy/run-sync-contract/spec.md#gwt-001
package local_contract

import (
	"encoding/json"
	assistantstreaming "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/streaming"
	"strings"
	"testing"

	rtfailures "quwoquan_service/runtime/failures"
	"quwoquan_service/runtime/streaming"
	orchestration "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
)

func TestProjectAssistantRunTerminalSnapshotUsesTypedTerminalFacts(t *testing.T) {
	t.Parallel()
	reference := assistant.AssistantRunVisibleReference{
		Title: "可信资料",
		Destination: assistant.CitationDestination{
			Kind: "external",
			URL:  "https://example.com/evidence",
		},
		Source:  "example.com",
		Snippet: "公开摘要",
	}
	process := assistant.AssistantRunVisibleProcess{
		ProcessID:              "assessing:1",
		Scope:                  "skill",
		Stage:                  "assessing",
		Status:                 "completed",
		Order:                  4,
		Summary:                "已核对可信资料",
		SkillID:                "weather",
		DomainID:               "weather",
		SearchedDocumentCount:  3,
		ProcessedDocumentCount: 2,
		AcceptedDocumentCount:  1,
		AcceptedReferences:     []assistant.AssistantRunVisibleReference{reference},
	}
	events := []streaming.Envelope{
		{
			Seq:       3,
			EventType: string(assistantstreaming.AssistantStreamEventProcessCommit),
			Payload:   map[string]any{"process": process},
		},
		{
			Seq:       1,
			EventType: string(assistantstreaming.AssistantStreamEventAnswerDelta),
			Payload:   map[string]any{"text": "草稿"},
		},
		{
			Seq:       4,
			EventType: string(assistantstreaming.AssistantStreamEventCompleted),
			Payload:   map[string]any{"finalAnswer": "最终回答"},
		},
		{
			Seq:       2,
			EventType: string(assistantstreaming.AssistantStreamEventProcessAppend),
			Payload: map[string]any{"process": assistant.AssistantRunVisibleProcess{
				ProcessID: "assessing:1",
				Scope:     "skill",
				Stage:     "assessing",
				Status:    "active",
				Order:     4,
			}},
		},
	}

	snapshot := orchestration.ProjectAssistantRunTerminalSnapshot(events, nil)

	if snapshot.AnswerText != "最终回答" {
		t.Fatalf("answer=%q want final answer", snapshot.AnswerText)
	}
	if len(snapshot.Processes) != 1 ||
		snapshot.Processes[0].Status != "completed" ||
		len(snapshot.Processes[0].AcceptedReferences) != 1 {
		t.Fatalf("terminal processes=%#v", snapshot.Processes)
	}
	if snapshot.Failure != nil {
		t.Fatalf("completed snapshot must not contain failure: %#v", snapshot.Failure)
	}
}

func TestProjectAssistantRunTerminalFailureDropsInternalMaterial(t *testing.T) {
	t.Parallel()
	failure := rtfailures.Failure{
		Code:   "ASSISTANT.MIDDLEWARE.weather_provider_unavailable",
		Origin: rtfailures.OriginRemoteDependency,
		Kind:   rtfailures.KindUnavailable,
		Nature: rtfailures.NatureTransient,
		Context: rtfailures.Context{Attributes: []rtfailures.ContextAttribute{
			{Key: "providerCredential", Value: "must-not-leak"},
		}},
	}
	snapshot := orchestration.ProjectAssistantRunTerminalSnapshot([]streaming.Envelope{
		{
			Seq:            1,
			EventType:      string(assistantstreaming.AssistantStreamEventFailed),
			Payload:        map[string]any{"providerDiagnostic": "must-not-leak"},
			RuntimeFailure: &failure,
		},
	}, nil)

	if snapshot.Failure == nil ||
		snapshot.Failure.Code != failure.Code ||
		snapshot.Failure.Origin != string(failure.Origin) ||
		snapshot.Failure.Kind != string(failure.Kind) ||
		snapshot.Failure.Nature != string(failure.Nature) {
		t.Fatalf("public failure=%#v", snapshot.Failure)
	}
	encoded, err := json.Marshal(snapshot)
	if err != nil {
		t.Fatalf("marshal terminal snapshot: %v", err)
	}
	for _, forbidden := range []string{
		"providerCredential",
		"must-not-leak",
		"providerDiagnostic",
		"location",
		"context",
	} {
		if strings.Contains(string(encoded), forbidden) {
			t.Fatalf("terminal snapshot leaked %q: %s", forbidden, encoded)
		}
	}
}
