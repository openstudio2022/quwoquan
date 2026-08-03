// spec_ref: specs/feature-tree/runtime/runtime-assistant/context-grounded-answering/spec.md#gwt-002
package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"testing"
	"time"

	runapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application"
	assistanthttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/adapters/inbound/http"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
)

type integrationIntersectionEvidenceReader struct {
	personaID string
	refs      []assistant.AssistantIntersectionEvidenceRef
	result    []assistant.AuthorizedIntersectionEvidence
	err       error
}

func (r *integrationIntersectionEvidenceReader) ResolveAuthorizedIntersectionEvidence(
	_ context.Context,
	personaID string,
	refs []assistant.AssistantIntersectionEvidenceRef,
) ([]assistant.AuthorizedIntersectionEvidence, error) {
	r.personaID = personaID
	r.refs = append([]assistant.AssistantIntersectionEvidenceRef(nil), refs...)
	return r.result, r.err
}

func TestAssistantRunAuthorizesIntersectionEvidenceAcrossHTTPBoundary(t *testing.T) {
	resetIntegrationState(t)
	capturedAt := time.Now().UTC()
	reader := &integrationIntersectionEvidenceReader{
		result: []assistant.AuthorizedIntersectionEvidence{{
			IntersectionID: "intersection-server",
			EvidenceID:     "evidence-server",
			SourceRef:      "same_school",
			ObjectTypeRef:  "content.post",
			ObjectID:       "post-server",
			PrimaryText:    "服务端授权后的共同学校事实",
			Dimension:      "education",
			VerifiedAt:     time.Date(2026, 7, 24, 1, 0, 0, 0, time.UTC),
		}},
	}
	handler := assistanthttp.NewHandler(
		newIntegrationAssistantService(),
		assistanthttp.WithRunContextResolver(runapplication.NewContextResolver(
			nil,
			runapplication.IntersectionEvidenceAuthorizerFunc(func(
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
				facts, authorizeErr := reader.ResolveAuthorizedIntersectionEvidence(
					ctx,
					personaID,
					requested,
				)
				if authorizeErr != nil {
					if authorizeErr == runapplication.ErrIntersectionEvidenceNotFound {
						return nil, runapplication.ErrIntersectionEvidenceNotFound
					}
					return nil, authorizeErr
				}
				result := make([]runapplication.AuthorizedIntersectionEvidence, 0, len(facts))
				for _, fact := range facts {
					result = append(result, runapplication.AuthorizedIntersectionEvidence{
						IntersectionID: fact.IntersectionID,
						EvidenceID:     fact.EvidenceID,
						SourceRef:      fact.SourceRef,
						ObjectTypeRef:  fact.ObjectTypeRef,
						ObjectID:       fact.ObjectID,
						PrimaryText:    fact.PrimaryText,
						Dimension:      fact.Dimension,
						VerifiedAt:     fact.VerifiedAt,
					})
				}
				return result, nil
			}),
		)),
	).Routes()

	create := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/sessions",
		"intersection-owner",
		map[string]any{
			"summary": "交集证据对话", "clientRequestId": "intersection-evidence-session",
		},
	)
	if create.Code != http.StatusCreated {
		t.Fatalf("create session status=%d body=%s", create.Code, create.Body.String())
	}
	var session assistant.AssistantSession
	if err := json.Unmarshal(create.Body.Bytes(), &session); err != nil {
		t.Fatalf("decode session: %v", err)
	}

	clientRef := map[string]any{
		"intersectionId": "intersection-client",
		"evidenceId":     "evidence-client",
		"sourceRef":      "same_school",
		"objectTypeRef":  "content.post",
		"objectId":       "post-client",
	}
	start := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/sessions/"+session.SessionID+"/runs",
		"intersection-owner",
		map[string]any{
			"intent": map[string]any{
				"kind": "answer", "answer": map[string]any{"text": "解释这条交集"},
			},
			"clientRequestId": "intersection-run-1",
			"contextSnapshot": map[string]any{
				"capturedAt":               capturedAt.Format(time.RFC3339Nano),
				"pageType":                 "intersection_detail",
				"intersectionEvidenceRefs": []map[string]any{clientRef},
			},
		},
	)
	if start.Code != http.StatusCreated {
		t.Fatalf("start run status=%d body=%s", start.Code, start.Body.String())
	}
	var envelope map[string]any
	if err := json.Unmarshal(start.Body.Bytes(), &envelope); err != nil {
		t.Fatalf("decode run envelope: %v", err)
	}
	if _, leaked := envelope["intersectionEvidence"]; leaked {
		t.Fatalf("run envelope leaked internal evidence: %#v", envelope)
	}
	runID, _ := envelope["runId"].(string)
	run, err := integrationRunRepository.Load(t.Context(), runID)
	if err != nil {
		t.Fatalf("load persisted run: %v", err)
	}
	if reader.personaID != "intersection-owner:persona" ||
		len(reader.refs) != 1 ||
		reader.refs[0].EvidenceID != "evidence-client" {
		t.Fatalf("reader actor/refs = %q %#v", reader.personaID, reader.refs)
	}
	encodedFacts, err := json.Marshal(run.ContextSnapshot["authorizedIntersectionEvidence"])
	if err != nil {
		t.Fatal(err)
	}
	var facts []runapplication.AuthorizedIntersectionEvidence
	if err := json.Unmarshal(encodedFacts, &facts); err != nil {
		t.Fatal(err)
	}
	if len(facts) != 1 || facts[0].EvidenceID != "evidence-server" ||
		facts[0].ObjectID != "post-server" {
		t.Fatalf("run persisted client payload instead of authorized evidence: %#v", facts)
	}

	reader.result = nil
	reader.err = runapplication.ErrIntersectionEvidenceNotFound
	rejected := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/sessions/"+session.SessionID+"/runs",
		"intersection-owner",
		map[string]any{
			"intent": map[string]any{
				"kind": "answer", "answer": map[string]any{"text": "再次解释"},
			},
			"clientRequestId": "intersection-run-2",
			"contextSnapshot": map[string]any{
				"capturedAt":               capturedAt.Add(time.Minute).Format(time.RFC3339Nano),
				"pageType":                 "intersection_detail",
				"intersectionEvidenceRefs": []map[string]any{clientRef},
			},
		},
	)
	if rejected.Code != http.StatusNotFound {
		t.Fatalf("stale evidence status=%d body=%s", rejected.Code, rejected.Body.String())
	}
}
