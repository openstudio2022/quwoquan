// spec_ref: specs/feature-tree/runtime/runtime-assistant/context-grounded-answering/spec.md#gwt-002
package local_contract

import (
	"context"
	"encoding/json"
	"strings"
	"testing"
	"time"

	runapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	rundomain "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
	assistantruntest "quwoquan_service/services/assistant-service/tests/support/assistantrun"
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
	ref := assistant.AssistantIntersectionEvidenceRef{
		IntersectionID: "intersection-client",
		EvidenceID:     "snapshot-client",
		SourceRef:      "same_school",
		ObjectTypeRef:  "post",
		ObjectID:       "post-client",
	}
	useCases := newIntersectionRunUseCases(reader)
	run, err := useCases.Start(
		t.Context(),
		"persona-owner",
		"intersection-evidence-session",
		"trace-intersection",
		runapplication.StartInput{
			ClientRequestID: "intersection-evidence-run",
			Intent: rundomain.Intent{
				Kind:   "answer",
				Answer: &rundomain.AnswerIntent{Text: "解释这条交集"},
			},
			ContextSnapshot: map[string]any{
				"intersectionEvidenceRefs": []any{map[string]any{
					"intersectionId": ref.IntersectionID,
					"evidenceId":     ref.EvidenceID,
					"sourceRef":      ref.SourceRef,
					"objectTypeRef":  ref.ObjectTypeRef,
					"objectId":       ref.ObjectID,
				}},
			},
			TrustedPersonaID: "persona-owner",
		},
	)
	if err != nil {
		t.Fatalf("Start() error = %v", err)
	}
	if reader.personaID != "persona-owner" || len(reader.refs) != 1 ||
		reader.refs[0] != ref {
		t.Fatalf("reader actor/refs = %q %#v", reader.personaID, reader.refs)
	}
	encoded, err := json.Marshal(run.ContextSnapshot["authorizedIntersectionEvidence"])
	if err != nil {
		t.Fatal(err)
	}
	var authorized []runapplication.AuthorizedIntersectionEvidence
	if err := json.Unmarshal(encoded, &authorized); err != nil {
		t.Fatal(err)
	}
	if len(authorized) != 1 ||
		authorized[0].PrimaryText != "服务端核验的共同学校事实" ||
		authorized[0].ObjectID != "post-server" {
		t.Fatalf("run must persist only authorized facts, got %#v", authorized)
	}
}

func TestCreateTurnFailsClosedForMissingIntersectionEvidence(t *testing.T) {
	reader := &assistantSessionIntersectionEvidenceGroundingRecordingIntersectionEvidenceReader{
		err: runapplication.ErrIntersectionEvidenceNotFound,
	}
	_, err := newIntersectionRunUseCases(reader).Start(
		t.Context(),
		"persona-owner",
		"missing-intersection-session",
		"trace-missing-intersection",
		runapplication.StartInput{
			ClientRequestID: "missing-intersection-run",
			Intent: rundomain.Intent{
				Kind:   "answer",
				Answer: &rundomain.AnswerIntent{Text: "解释这条交集"},
			},
			ContextSnapshot: map[string]any{
				"intersectionEvidenceRefs": []any{map[string]any{
					"intersectionId": "forged",
					"evidenceId":     "stale",
					"sourceRef":      "same_school",
					"objectTypeRef":  "post",
					"objectId":       "other-persona-post",
				}},
			},
			TrustedPersonaID: "persona-owner",
		},
	)
	if err == nil || !strings.Contains(err.Error(), "ASSISTANT.USER.intersection_evidence_not_found") {
		t.Fatalf("CreateTurn() error = %v, want structured not-found failure", err)
	}
}

func newIntersectionRunUseCases(
	reader *assistantSessionIntersectionEvidenceGroundingRecordingIntersectionEvidenceReader,
) *runapplication.UseCases {
	runtime := assistantruntest.NewMemoryRuntime()
	commands := runruntime.NewCommandService(
		runtime,
		runruntime.SessionAuthorizerFunc(func(context.Context, string, string) error { return nil }),
		testSkillPackageIdentityResolver(),
		runruntime.AllowAllStartAccessPolicy{},
		nil,
		nil,
		testRunPolicyResolver(),
	)
	authorizer := runapplication.IntersectionEvidenceAuthorizerFunc(func(
		ctx context.Context,
		personaID string,
		references []runapplication.IntersectionEvidenceRef,
	) ([]runapplication.AuthorizedIntersectionEvidence, error) {
		requested := make([]assistant.AssistantIntersectionEvidenceRef, 0, len(references))
		for _, reference := range references {
			requested = append(requested, assistant.AssistantIntersectionEvidenceRef{
				IntersectionID: reference.IntersectionID,
				EvidenceID:     reference.EvidenceID,
				SourceRef:      reference.SourceRef,
				ObjectTypeRef:  reference.ObjectTypeRef,
				ObjectID:       reference.ObjectID,
			})
		}
		evidence, err := reader.ResolveAuthorizedIntersectionEvidence(ctx, personaID, requested)
		if err != nil {
			if err == runapplication.ErrIntersectionEvidenceNotFound {
				return nil, runapplication.ErrIntersectionEvidenceNotFound
			}
			return nil, err
		}
		result := make([]runapplication.AuthorizedIntersectionEvidence, 0, len(evidence))
		for _, item := range evidence {
			result = append(result, runapplication.AuthorizedIntersectionEvidence{
				IntersectionID: item.IntersectionID,
				EvidenceID:     item.EvidenceID,
				SourceRef:      item.SourceRef,
				ObjectTypeRef:  item.ObjectTypeRef,
				ObjectID:       item.ObjectID,
				PrimaryText:    item.PrimaryText,
				Dimension:      item.Dimension,
				VerifiedAt:     item.VerifiedAt,
			})
		}
		return result, nil
	})
	return runapplication.NewUseCases(
		commands,
		runapplication.WithContextResolver(
			runapplication.NewContextResolver(nil, authorizer),
		),
	)
}
