package assistant_run

import (
	"context"
	"strings"
	"testing"
	"time"

	publicwebtool "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/adapters/outbound/tool"
	publicweb "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/publicweb"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/tool"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
)

type recordingDiscoveryLedger struct {
	runID      string
	references []publicweb.SearchReference
}

func (l *recordingDiscoveryLedger) RecordSearchReferences(
	_ context.Context,
	runID string,
	references []publicweb.SearchReference,
) ([]publicweb.DiscoveredSource, error) {
	l.runID = runID
	l.references = append([]publicweb.SearchReference{}, references...)
	return []publicweb.DiscoveredSource{{
		SourceID:      "src_search_truth",
		NormalizedURL: "https://example.com/source",
	}}, nil
}

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/autonomous-web-exploration/spec.md#gwt-001
func TestWebSearchAdapterCommitsServerOwnedSourceLedgerIdentity(t *testing.T) {
	ledger := &recordingDiscoveryLedger{}
	delegate := func(
		_ context.Context,
		_ toolpkg.Request,
	) (toolpkg.Result, error) {
		return toolpkg.Result{Output: map[string]any{
			"summary":  "search summary",
			"reliable": true,
			"references": []map[string]any{{
				"title":   "Source",
				"source":  "example.com",
				"snippet": "fact",
				"destination": map[string]any{
					"kind": "external", "url": "https://example.com/source#fragment",
				},
			}},
		}}, nil
	}
	registry := toolpkg.BaseRegistry()
	registry.Register(
		toolpkg.WebSearchMetadata(),
		publicwebtool.SearchHandler(delegate, ledger),
	)
	result, err := registry.Execute(context.Background(), toolpkg.Request{
		ToolName: "web_search",
		Input: map[string]any{
			"runId": "run_truth", "skillId": "knowledge_general", "query": "source",
		},
	})
	if err != nil {
		t.Fatalf("execute web_search: %v", err)
	}
	if ledger.runID != "run_truth" || len(ledger.references) != 1 {
		t.Fatalf("ledger run=%q references=%v", ledger.runID, ledger.references)
	}
	references := result.Output["references"].([]map[string]any)
	if references[0]["sourceId"] != "src_search_truth" {
		t.Fatalf("server source identity missing: %#v", references[0])
	}
	assessment := result.Output["evidenceAssessment"].(map[string]any)
	if assessment["status"] != "insufficient" ||
		assessment["replanRequired"] != true ||
		assessment["reason"] != "open_authoritative_source" {
		t.Fatalf("search discovery assessment = %#v", assessment)
	}
}

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/autonomous-web-exploration/spec.md#gwt-002
func TestToolCoordinatorReplacesForgedServerInjectedRunAndSkill(t *testing.T) {
	registry := toolpkg.BaseRegistry()
	var captured toolpkg.Request
	registry.Register(toolpkg.WebOpenMetadata(), func(
		_ context.Context,
		request toolpkg.Request,
	) (toolpkg.Result, error) {
		captured = request
		return toolpkg.Result{Output: map[string]any{
			"document": map[string]any{}, "reference": map[string]any{},
			"evidenceAssessment": map[string]any{
				"status": "accepted", "evidenceSufficient": true,
				"replanRequired": false, "reason": "test_evidence",
				"targetIds": []any{}, "documentIds": []any{},
				"artifactRefs": []any{}, "sourceIds": []any{},
			},
		}}, nil
	})
	coordinator := orchestration.DefaultToolCoordinator{Registry: registry}
	execution, err := coordinator.Execute(context.Background(), orchestration.ToolRequest{
		Turn: assistant.AssistantTurn{
			TurnID: "run_truth", Input: assistant.AssistantTurnInput{Text: "open"},
		},
		Skill:    orchestration.SkillSelection{SkillID: "skill_truth"},
		ToolName: "web_open",
		Input: map[string]any{
			"runId": "run_forged", "skillId": "skill_forged",
			"target": map[string]any{"kind": "url", "value": "https://example.com"},
		},
	})
	if err != nil || execution.Failure != nil {
		t.Fatalf("execute web_open err=%v failure=%v", err, execution.Failure)
	}
	if captured.Input["runId"] != "run_truth" || captured.Input["skillId"] != "skill_truth" {
		t.Fatalf("server inputs were not authoritative: %#v", captured.Input)
	}
	declaration := registry.ModelDeclarations([]string{"web_open"})[0]
	properties := declaration.Parameters["properties"].(map[string]any)
	if _, exists := properties["runId"]; exists {
		t.Fatal("model declaration must not expose runId")
	}
	if _, exists := properties["skillId"]; exists {
		t.Fatal("model declaration must not expose skillId")
	}
}

type fixedTargetResolver struct{}

func (fixedTargetResolver) ResolveTarget(
	_ context.Context,
	_ string,
	_ publicweb.Target,
) (publicweb.ResolvedTarget, error) {
	return publicweb.ResolvedTarget{URL: "https://example.com", Origin: "url"}, nil
}

type rejectingTargetResolver struct{}

func (rejectingTargetResolver) ResolveTarget(
	_ context.Context,
	_ string,
	_ publicweb.Target,
) (publicweb.ResolvedTarget, error) {
	return publicweb.ResolvedTarget{}, publicweb.ErrTargetUnavailable
}

type longDocumentFetcher struct{ body []byte }

func (f longDocumentFetcher) Fetch(
	_ context.Context,
	_ publicweb.NetworkRequest,
) (publicweb.NetworkResult, error) {
	return publicweb.NetworkResult{
		FinalURL: "https://example.com", ContentType: "text/plain",
		Body: f.body, FetchedAt: time.Date(2026, 7, 31, 1, 2, 3, 0, time.UTC),
	}, nil
}

type recordingEvidenceStore struct{ record publicweb.EvidenceRecord }

func (s *recordingEvidenceStore) CommitEvidence(
	_ context.Context,
	record publicweb.EvidenceRecord,
) error {
	s.record = record
	return nil
}

func (s *recordingEvidenceStore) ReadDocument(
	_ context.Context,
	runID string,
	documentID string,
) (publicweb.Document, error) {
	if s.record.Document.Source.RunID != runID ||
		s.record.Document.DocumentID != documentID {
		return publicweb.Document{}, publicweb.ErrTargetUnavailable
	}
	return s.record.Document, nil
}

func (s *recordingEvidenceStore) RecordSearchReferences(
	_ context.Context,
	runID string,
	references []publicweb.SearchReference,
) ([]publicweb.DiscoveredSource, error) {
	result := make([]publicweb.DiscoveredSource, 0, len(references))
	for index, reference := range references {
		result = append(result, publicweb.DiscoveredSource{
			SourceID:      "src_recorded_" + string(rune('a'+index)),
			NormalizedURL: strings.TrimSuffix(reference.URL, "#fragment"),
		})
	}
	return result, nil
}

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/autonomous-web-exploration/spec.md#gwt-001
func TestWebOpenAdapterKeepsFullArtifactOutsideBoundedModelOutput(t *testing.T) {
	body := []byte(strings.Repeat("证", 21_000))
	store := &recordingEvidenceStore{}
	service := publicweb.NewService(
		fixedTargetResolver{},
		longDocumentFetcher{body: body},
		store,
		publicweb.NewRunBudgetGate(publicweb.RunBudgetLimits{
			MaxPages: 2, MaxBytes: 2 << 20,
		}),
		publicweb.DefaultDocumentParser(),
	)
	registry := toolpkg.BaseRegistry()
	registry.Register(toolpkg.WebOpenMetadata(), publicwebtool.OpenHandler(service))
	result, err := registry.Execute(context.Background(), toolpkg.Request{
		ToolName: "web_open",
		Input: map[string]any{
			"runId": "run_truth", "skillId": "knowledge_general",
			"target": map[string]any{"kind": "url", "value": "https://example.com"},
		},
	})
	if err != nil {
		t.Fatalf("execute web_open: %v", err)
	}
	document := result.Output["document"].(map[string]any)
	if len([]rune(document["contentText"].(string))) != 20_000 || document["truncated"] != true {
		t.Fatalf("model document projection is not bounded: %#v", document)
	}
	if len(store.record.Artifact.Body) != len(body) || store.record.Document.ArtifactRef == "" {
		t.Fatalf("artifact store lost full evidence: bytes=%d document=%#v", len(store.record.Artifact.Body), store.record.Document)
	}
	assessment := result.Output["evidenceAssessment"].(map[string]any)
	if assessment["evidenceSufficient"] != true ||
		assessment["replanRequired"] != false {
		t.Fatalf("open evidence assessment = %#v", assessment)
	}
}

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/autonomous-web-exploration/spec.md#gwt-001
func TestPublicWebFabricInjectsDurableRunIdentityAndReturnsAssessment(t *testing.T) {
	store := &recordingEvidenceStore{}
	service := publicweb.NewService(
		fixedTargetResolver{},
		longDocumentFetcher{body: []byte("durable evidence")},
		store,
		publicweb.NewRunBudgetGate(publicweb.RunBudgetLimits{
			MaxPages: 2, MaxBytes: 2 << 20,
		}),
		publicweb.DefaultDocumentParser(),
	)
	fabric := publicwebtool.NewPublicWebFabric(
		func(_ context.Context, _ toolpkg.Request) (toolpkg.Result, error) {
			return toolpkg.Result{Output: map[string]any{
				"summary": "discovery", "references": []map[string]any{},
				"reliable": false,
			}}, nil
		},
		store,
		service,
		publicweb.NewFinder(store),
	)
	result, err := fabric.Execute(context.Background(), publicwebtool.DurableRequest{
		ToolName: "web_open",
		RunID:    "run_authoritative",
		SkillID:  "skill_authoritative",
		Input: map[string]any{
			"runId": "run_forged", "skillId": "skill_forged",
			"target": map[string]any{"kind": "url", "value": "https://example.com"},
		},
	})
	if err != nil {
		t.Fatalf("execute durable public web fabric: %v", err)
	}
	if store.record.Source.RunID != "run_authoritative" ||
		store.record.Source.SkillID != "skill_authoritative" {
		t.Fatalf("fabric trusted caller input: %#v", store.record.Source)
	}
	assessment := result.Output["evidenceAssessment"].(map[string]any)
	if assessment["status"] != "accepted" ||
		assessment["evidenceSufficient"] != true ||
		assessment["replanRequired"] != false {
		t.Fatalf("durable assessment = %#v", assessment)
	}
}

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/autonomous-web-exploration/spec.md#gwt-002
func TestWebOpenSafetyRejectionKeepsCanonicalFailureSemantics(t *testing.T) {
	service := publicweb.NewService(
		rejectingTargetResolver{},
		longDocumentFetcher{body: []byte("unused")},
		&recordingEvidenceStore{},
		publicweb.NewRunBudgetGate(publicweb.RunBudgetLimits{
			MaxPages: 2, MaxBytes: 2 << 20,
		}),
		publicweb.DefaultDocumentParser(),
	)
	registry := toolpkg.BaseRegistry()
	registry.Register(toolpkg.WebOpenMetadata(), publicwebtool.OpenHandler(service))
	coordinator := orchestration.DefaultToolCoordinator{Registry: registry}
	execution, err := coordinator.Execute(context.Background(), orchestration.ToolRequest{
		Turn: assistant.AssistantTurn{
			TurnID: "run_rejected", Input: assistant.AssistantTurnInput{Text: "open"},
		},
		Skill:    orchestration.SkillSelection{SkillID: "knowledge_general"},
		ToolName: "web_open",
		Input: map[string]any{
			"target": map[string]any{"kind": "source", "value": "src_unknown"},
		},
	})
	if err != nil || execution.Failure == nil {
		t.Fatalf("execute web_open err=%v failure=%v", err, execution.Failure)
	}
	failure := execution.Failure
	if failure.Code != "ASSISTANT.USER.web_target_rejected" ||
		failure.Origin != "user" || failure.Kind != "permission" ||
		failure.Nature != "permanent" {
		t.Fatalf("canonical safety failure lost: %+v", failure)
	}
	for _, attribute := range failure.Context.Attributes {
		if attribute.Key == "reason" && attribute.Value != "web_target_rejected" {
			t.Fatalf("unsafe or unstable reason leaked: %+v", failure.Context.Attributes)
		}
	}
}
