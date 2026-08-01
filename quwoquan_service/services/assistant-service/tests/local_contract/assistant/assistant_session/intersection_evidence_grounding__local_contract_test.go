// spec_ref: specs/feature-tree/runtime/runtime-assistant/context-grounded-answering/spec.md#gwt-002
package local_contract

import (
	"context"
	prompting "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/prompting"
	"strings"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/persistence"
)

type assistantSessionIntersectionEvidenceGroundingRecordingIntersectionEvidenceReader struct {
	personaID string
	refs      []assistant.AssistantIntersectionEvidenceRef
	result    []assistant.AuthorizedIntersectionEvidence
	err       error
}

func (r *assistantSessionIntersectionEvidenceGroundingRecordingIntersectionEvidenceReader) ResolveAuthorizedIntersectionEvidence(
	_ context.Context,
	personaID string,
	refs []assistant.AssistantIntersectionEvidenceRef,
) ([]assistant.AuthorizedIntersectionEvidence, error) {
	r.personaID = personaID
	r.refs = append([]assistant.AssistantIntersectionEvidenceRef(nil), refs...)
	return r.result, r.err
}

func TestCreateTurnAuthorizesIntersectionEvidenceBeforePersistence(t *testing.T) {
	reader := &assistantSessionIntersectionEvidenceGroundingRecordingIntersectionEvidenceReader{
		result: []assistant.AuthorizedIntersectionEvidence{{
			IntersectionID: "intersection-server",
			EvidenceID:     "snapshot-server",
			SourceRef:      "same_school",
			ObjectTypeRef:  "post",
			ObjectID:       "post-server",
			PrimaryText:    "服务端核验的共同学校事实",
			Dimension:      "education",
			VerifiedAt:     time.Date(2026, 7, 21, 12, 0, 0, 0, time.UTC),
		}},
	}
	service := orchestration.NewAssistantService(
		nil,
		nil,
		orchestration.WithSessionRunStore(persistence.NewMemorySessionRunStore()),
		orchestration.WithIntersectionEvidenceReader(reader),
		testFrozenPolicyOption(),
	)
	session, err := service.CreateSession(
		t.Context(),
		"persona-owner",
		assistant.CreateSessionInput{ClientRequestID: "intersection-evidence-session"},
	)
	if err != nil {
		t.Fatalf("CreateSession() error = %v", err)
	}
	ref := assistant.AssistantIntersectionEvidenceRef{
		IntersectionID: "intersection-client",
		EvidenceID:     "snapshot-client",
		SourceRef:      "same_school",
		ObjectTypeRef:  "post",
		ObjectID:       "post-client",
	}
	turn, err := service.CreateTurn(
		t.Context(),
		"persona-owner",
		session.SessionID,
		assistant.CreateTurnInput{
			Input:           assistant.AssistantTurnInput{Text: "解释这条交集"},
			ClientRequestID: "intersection-evidence-turn",
			ContextSnapshot: assistant.AssistantContextSnapshot{
				IntersectionEvidenceRefs: []assistant.AssistantIntersectionEvidenceRef{ref},
			},
			RequestContext: testRunRequestContext("persona-owner"),
		},
	)
	if err != nil {
		t.Fatalf("CreateTurn() error = %v", err)
	}
	if reader.personaID != "persona-owner" || len(reader.refs) != 1 ||
		reader.refs[0] != ref {
		t.Fatalf("reader actor/refs = %q %#v", reader.personaID, reader.refs)
	}
	if len(turn.IntersectionEvidence) != 1 ||
		turn.IntersectionEvidence[0].PrimaryText != "服务端核验的共同学校事实" ||
		turn.IntersectionEvidence[0].ObjectID != "post-server" {
		t.Fatalf("turn must persist only reader facts, got %#v", turn.IntersectionEvidence)
	}
	prompt := prompting.FormatAuthorizedIntersectionEvidenceForPrompt(
		turn.IntersectionEvidence,
	)
	if !strings.Contains(prompt, "服务端核验的共同学校事实") ||
		strings.Contains(prompt, "intersection-client") {
		t.Fatalf("grounding prompt = %q", prompt)
	}
}

func TestCreateTurnFailsClosedForMissingIntersectionEvidence(t *testing.T) {
	reader := &assistantSessionIntersectionEvidenceGroundingRecordingIntersectionEvidenceReader{
		err: orchestration.ErrIntersectionEvidenceNotFound,
	}
	service := orchestration.NewAssistantService(
		nil,
		nil,
		orchestration.WithSessionRunStore(persistence.NewMemorySessionRunStore()),
		orchestration.WithIntersectionEvidenceReader(reader),
		testFrozenPolicyOption(),
	)
	session, err := service.CreateSession(
		t.Context(),
		"persona-owner",
		assistant.CreateSessionInput{ClientRequestID: "missing-intersection-session"},
	)
	if err != nil {
		t.Fatalf("CreateSession() error = %v", err)
	}
	_, err = service.CreateTurn(
		t.Context(),
		"persona-owner",
		session.SessionID,
		assistant.CreateTurnInput{
			Input:           assistant.AssistantTurnInput{Text: "解释这条交集"},
			ClientRequestID: "missing-intersection-turn",
			ContextSnapshot: assistant.AssistantContextSnapshot{
				IntersectionEvidenceRefs: []assistant.AssistantIntersectionEvidenceRef{{
					IntersectionID: "forged",
					EvidenceID:     "stale",
					SourceRef:      "same_school",
					ObjectTypeRef:  "post",
					ObjectID:       "other-persona-post",
				}},
			},
			RequestContext: testRunRequestContext("persona-owner"),
		},
	)
	if err == nil || !strings.Contains(err.Error(), "ASSISTANT.USER.intersection_evidence_not_found") {
		t.Fatalf("CreateTurn() error = %v, want structured not-found failure", err)
	}
}
