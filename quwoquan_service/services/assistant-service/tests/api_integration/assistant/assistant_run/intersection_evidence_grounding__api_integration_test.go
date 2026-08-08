// spec_ref: specs/feature-tree/runtime/runtime-assistant/context-grounded-answering/spec.md#gwt-002
// readiness_case: start-assistant-run-api
package assistant_run_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
	"quwoquan_service/runtime/operation"
	runhttp "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/adapters/inbound/http"
	runapplication "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	runpersistence "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure"
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
	database := requirePublicWebMongo(t)
	for _, collection := range []string{
		"assistant_runs",
		"assistant_run_events",
		"assistant_run_command_receipts",
	} {
		if _, err := database.Collection(collection).DeleteMany(t.Context(), map[string]any{}); err != nil {
			t.Fatalf("reset %s: %v", collection, err)
		}
	}
	repository := runpersistence.NewMongoRunRepository(database)
	if err := repository.EnsureIndexes(t.Context()); err != nil {
		t.Fatalf("ensure AssistantRun indexes: %v", err)
	}
	commands := runruntime.NewCommandService(
		repository,
		runruntime.SessionResolverFunc(func(context.Context, string, string) (runruntime.SessionContinuity, error) {
			return runruntime.SessionContinuity{}, nil
		}),
		runruntime.StaticSkillPackageIdentityResolver{
			PackageID:     "assistant.session.skills",
			ReleaseDigest: "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
		},
		runruntime.AllowAllStartAccessPolicy{},
		time.Now,
		nil,
		runruntime.WithPolicyResolver(intersectionEvidencePolicyResolver()),
	)
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
	handler := runhttp.NewHandler(
		commands,
		runhttp.WithContextResolver(runapplication.NewContextResolver(
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

	clientRef := map[string]any{
		"intersectionId": "intersection-client",
		"evidenceId":     "evidence-client",
		"sourceRef":      "same_school",
		"objectTypeRef":  "content.post",
		"objectId":       "post-client",
	}
	start := assistantRunAPIRequest(
		t,
		handler,
		"intersection-owner",
		"intersection-evidence-session",
		"intersection-run-1",
		capturedAt,
		clientRef,
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
	run, err := repository.Load(t.Context(), runID)
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
	rejected := assistantRunAPIRequest(
		t,
		handler,
		"intersection-owner",
		"intersection-evidence-session",
		"intersection-run-2",
		capturedAt.Add(time.Minute),
		clientRef,
	)
	if rejected.Code != http.StatusNotFound {
		t.Fatalf("stale evidence status=%d body=%s", rejected.Code, rejected.Body.String())
	}
}

func assistantRunAPIRequest(
	t *testing.T,
	handler http.Handler,
	accountID string,
	sessionID string,
	clientRequestID string,
	capturedAt time.Time,
	clientRef map[string]any,
) *httptest.ResponseRecorder {
	t.Helper()
	payload, err := json.Marshal(map[string]any{
		"intent": map[string]any{
			"kind": "answer", "answer": map[string]any{"text": "解释这条交集"},
		},
		"clientRequestId": clientRequestID,
		"contextSnapshot": map[string]any{
			"capturedAt":               capturedAt.Format(time.RFC3339Nano),
			"pageType":                 "intersection_detail",
			"intersectionEvidenceRefs": []map[string]any{clientRef},
		},
	})
	if err != nil {
		t.Fatalf("marshal request: %v", err)
	}
	request := httptest.NewRequest(
		http.MethodPost,
		"/assistant/sessions/"+sessionID+"/runs",
		bytes.NewReader(payload),
	)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", clientRequestID)
	request.Header.Set("X-Client-User-Id", accountID)
	request = request.WithContext(rtauth.WithPrincipal(
		request.Context(),
		rtauth.Principal{Actor: operation.ActorContext{
			AccountID: accountID,
			PersonaID: accountID + ":persona",
		}},
	))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}

func intersectionEvidencePolicyResolver() runruntime.PolicyResolver {
	return runruntime.PolicyResolverFunc(func(
		_ context.Context,
		policyID string,
		_ string,
		skillID string,
		domainID string,
	) (runruntime.FrozenPolicySelection, error) {
		if policyID == "" {
			policyID = "assistant-default"
		}
		if strings.TrimSpace(skillID) == "" {
			skillID = "fallback_general_search"
		}
		if strings.TrimSpace(domainID) == "" {
			domainID = "assistant"
		}
		return runruntime.FrozenPolicySelection{
			PolicyID:        policyID,
			ReleaseDigest:   "e1a0a7e3379c544c2551da7aafba674ddae2ac9c7d08fdb5762301e9097c771d",
			Cohort:          "control",
			RolloutRevision: 1,
			RuleID:          "intersection-evidence-api-integration",
			Template: runruntime.FrozenPolicyTemplate{
				TemplateID:      "intersection-evidence-api-integration",
				SkillID:         skillID,
				DomainID:        domainID,
				PromptPolicy:    "intersection evidence API integration",
				AllowedTools:    []string{},
				SearchIntensity: "medium",
			},
		}, nil
	})
}
