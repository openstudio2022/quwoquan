// spec_ref: specs/feature-tree/runtime/runtime-assistant/context-grounded-answering/spec.md#gwt-002
package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"testing"
	"time"

	assistanthttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/adapters/inbound/http"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
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
		newIntegrationAssistantService(
			application.WithIntersectionEvidenceReader(reader),
		),
	).Routes()

	create := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/conversations",
		"intersection-owner",
		map[string]any{
			"summary": "交集证据对话", "clientRequestId": "intersection-evidence-conversation",
		},
	)
	if create.Code != http.StatusCreated {
		t.Fatalf("create conversation status=%d body=%s", create.Code, create.Body.String())
	}
	var conversation assistant.AssistantConversation
	if err := json.Unmarshal(create.Body.Bytes(), &conversation); err != nil {
		t.Fatalf("decode conversation: %v", err)
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
		"/assistant/conversations/"+conversation.ConversationID+"/runs",
		"intersection-owner",
		map[string]any{
			"input":           map[string]any{"text": "解释这条交集"},
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
	turnID, _ := envelope["turnId"].(string)
	turn, found, err := integrationConversationRunStore.GetTurn(t.Context(), turnID)
	if err != nil || !found {
		t.Fatalf("load persisted turn found=%v err=%v", found, err)
	}
	if reader.personaID != "intersection-owner" ||
		len(reader.refs) != 1 ||
		reader.refs[0].EvidenceID != "evidence-client" {
		t.Fatalf("reader actor/refs = %q %#v", reader.personaID, reader.refs)
	}
	if len(turn.IntersectionEvidence) != 1 ||
		turn.IntersectionEvidence[0].EvidenceID != "evidence-server" ||
		turn.IntersectionEvidence[0].ObjectID != "post-server" {
		t.Fatalf("turn persisted client payload instead of authorized evidence: %#v", turn.IntersectionEvidence)
	}

	reader.result = nil
	reader.err = application.ErrIntersectionEvidenceNotFound
	rejected := assistantAPIRequest(
		t,
		handler,
		http.MethodPost,
		"/assistant/conversations/"+conversation.ConversationID+"/runs",
		"intersection-owner",
		map[string]any{
			"input":           map[string]any{"text": "再次解释"},
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
