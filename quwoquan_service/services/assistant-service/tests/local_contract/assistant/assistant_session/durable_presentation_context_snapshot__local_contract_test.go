// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/adaptive-presentation-runtime/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/adaptive-presentation-runtime/spec.md#gwt-002
package local_contract

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
	"testing"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	presentationpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/presentation"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	skillcontext "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/skillcontext"
	readermodel "quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/domain/model"
	readerresource "quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/infrastructure/resource"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
)

type durablePresentationCatalog struct {
	manifest      skillpkg.Manifest
	template      json.RawMessage
	templates     map[string]json.RawMessage
	loadCalls     int
	templateCalls int
}

func (catalog *durablePresentationCatalog) Load(
	ctx context.Context,
) ([]skillpkg.Manifest, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	catalog.loadCalls++
	return []skillpkg.Manifest{catalog.manifest}, nil
}

func (catalog *durablePresentationCatalog) ResolvePresentationTemplate(
	ctx context.Context,
	templateID string,
	skillID string,
) (json.RawMessage, bool, error) {
	if err := ctx.Err(); err != nil {
		return nil, false, err
	}
	catalog.templateCalls++
	if raw, found := catalog.templates[templateID]; found &&
		skillID == catalog.manifest.SkillID {
		return append(json.RawMessage(nil), raw...), true, nil
	}
	if templateID != "test.context.card" || skillID != catalog.manifest.SkillID {
		return nil, false, nil
	}
	return append(json.RawMessage(nil), catalog.template...), true, nil
}

type durablePresentationContextResolver struct {
	calls int
	err   error
}

func (resolver *durablePresentationContextResolver) Resolve(
	_ context.Context,
	_ skillcontext.ResolveRequest,
) (skillcontext.ResolvedContext, error) {
	resolver.calls++
	if resolver.err != nil {
		return skillcontext.ResolvedContext{}, resolver.err
	}
	capturedAt := time.Now().UTC().Add(-time.Minute)
	return skillcontext.ResolvedContext{
		Kind: "domain",
		SourceRef: "circle.Gathering:gathering-1@sha256:" +
			strings.Repeat("d", 64),
		Authority:   generated.AssistantContextAuthorityDomainCanonical,
		Sensitivity: generated.AssistantContextSensitivityInternal,
		CapturedAt:  capturedAt,
		ExpiresAt:   capturedAt.Add(24 * time.Hour),
		TokenCost:   8,
		Value: map[string]any{
			"gatheringId": "gathering-1",
		},
	}, nil
}

type durablePresentationModel struct {
	snapshotIDs             []string
	segmentDigests          []string
	presentationCandidateID string
	presentationCalls       int
}

func (*durablePresentationModel) ModelExecutionCapabilities() orchestration.ModelExecutionCapabilities {
	return durableTestModelCapabilities()
}

func (model *durablePresentationModel) Complete(
	_ context.Context,
	request orchestration.ModelRequest,
) (orchestration.ModelResponse, error) {
	if request.ContextAssembly != nil &&
		request.ContextAssembly.SkillContextSnapshot != nil {
		snapshot := request.ContextAssembly.SkillContextSnapshot
		model.snapshotIDs = append(model.snapshotIDs, snapshot.SnapshotID)
		if len(snapshot.Segments) > 0 {
			model.segmentDigests = append(
				model.segmentDigests,
				snapshot.Segments[0].Digest,
			)
		}
	}
	if request.Stage == "reasoning" {
		return orchestration.ModelResponse{
			Text:            `{"nextAction":"answer"}`,
			StructuredDelta: map[string]any{"nextAction": "answer"},
		}, nil
	}
	if request.Stage == "presentation" {
		model.presentationCalls++
		return orchestration.ModelResponse{
			Text: model.presentationCandidateID,
			StructuredDelta: map[string]any{
				"candidateId": model.presentationCandidateID,
			},
		}, nil
	}
	return orchestration.ModelResponse{
		Text:            "已根据冻结行程生成回答。",
		StructuredDelta: map[string]any{"userMarkdown": "已根据冻结行程生成回答。"},
	}, nil
}

func TestDurablePresentationUsesTheInferenceSkillContextSnapshotExactlyOnce(
	t *testing.T,
) {
	resolver := &durablePresentationContextResolver{}
	executor, catalog, model := durablePresentationExecutor(t, resolver)

	result, err := executor.Execute(
		t.Context(),
		durablePresentationRequest(t),
		func(runruntime.ExecutionItemUpdate) error { return nil },
	)
	if err != nil {
		t.Fatalf("Execute() error=%v", err)
	}
	if resolver.calls != 1 {
		t.Fatalf("Skill context assembled %d times, want exactly once", resolver.calls)
	}
	if catalog.loadCalls != 1 {
		t.Fatalf("Skill manifest resolved %d times, want exactly once", catalog.loadCalls)
	}
	if catalog.templateCalls != 1 {
		t.Fatalf("presentation template resolved %d times, want once", catalog.templateCalls)
	}
	if len(model.snapshotIDs) == 0 || len(model.segmentDigests) == 0 {
		t.Fatalf("model did not receive typed Skill context: %+v", model)
	}
	for _, snapshotID := range model.snapshotIDs[1:] {
		if snapshotID != model.snapshotIDs[0] {
			t.Fatalf("model snapshot drift: %v", model.snapshotIDs)
		}
	}
	for _, digest := range model.segmentDigests[1:] {
		if digest != model.segmentDigests[0] {
			t.Fatalf("model context digest drift: %v", model.segmentDigests)
		}
	}
	if title := presentationNodeTitle(result.Presentation, "gathering"); title != "gathering-1" {
		t.Fatalf(
			"presentation did not use inference context: title=%q document=%#v",
			title,
			result.Presentation,
		)
	}
}

func TestDurablePresentationKeepsTemplateBoundFallbackForLegacySurface(
	t *testing.T,
) {
	resolver := &durablePresentationContextResolver{}
	executor, _, _ := durablePresentationExecutor(t, resolver)
	request := durablePresentationRequest(t)
	request.SurfaceCapabilities = nil
	result, err := executor.Execute(
		t.Context(),
		request,
		func(runruntime.ExecutionItemUpdate) error { return nil },
	)
	if err != nil {
		t.Fatalf("Execute() error=%v", err)
	}
	templateDigest, _ := result.Presentation["templateDigest"].(string)
	if result.Presentation == nil ||
		result.Presentation["fallbackMarkdown"] != "已根据冻结行程生成回答。" ||
		strings.TrimSpace(templateDigest) == "" {
		t.Fatalf("legacy presentation fallback=%#v", result.Presentation)
	}
	if nodes, found := result.Presentation["nodes"].([]any); found && len(nodes) != 0 {
		t.Fatalf("legacy surface received unsupported nodes=%#v", nodes)
	}
}

func TestDurablePresentationExecutorHandsOffUncommittedSnapshot(t *testing.T) {
	resolver := &durablePresentationContextResolver{}
	executor, _, _ := durablePresentationExecutor(t, resolver)
	result, err := executor.Execute(
		t.Context(),
		durablePresentationRequest(t),
		func(runruntime.ExecutionItemUpdate) error { return nil },
	)
	if err != nil {
		t.Fatalf("Execute() error=%v", err)
	}
	committedAt, ok := result.Presentation["committedAt"].(string)
	if !ok || committedAt != "" {
		t.Fatalf(
			"executor handed RunRuntime a pre-committed presentation: %#v",
			result.Presentation,
		)
	}
}

func TestDurablePresentationModelSelectsOnlyAResolvedFrozenCandidate(t *testing.T) {
	resolver := &durablePresentationContextResolver{}
	executor, catalog, model := durablePresentationExecutor(t, resolver)
	answerTemplate := durableAnswerPresentationTemplate(t, catalog.manifest.SkillID)
	catalog.templates = map[string]json.RawMessage{
		"test.context.card":        catalog.template,
		"assistant.answer.default": answerTemplate,
	}
	catalog.manifest.Presentation.TemplateRefs = []string{
		"test.context.card",
		"assistant.answer.default",
	}
	contextTemplate, err := presentationpkg.DecodeTemplate(catalog.template)
	if err != nil {
		t.Fatal(err)
	}
	model.presentationCandidateID = presentationpkg.TemplateRef(contextTemplate)

	result, err := executor.Execute(
		t.Context(),
		durablePresentationRequest(t),
		func(runruntime.ExecutionItemUpdate) error { return nil },
	)
	if err != nil {
		t.Fatalf("Execute() error=%v", err)
	}
	if model.presentationCalls != 1 ||
		result.Presentation["templateRef"] != model.presentationCandidateID {
		t.Fatalf(
			"model selection calls=%d document=%#v",
			model.presentationCalls,
			result.Presentation,
		)
	}

	model.presentationCandidateID = "forged.template@sha256:" + strings.Repeat("f", 64)
	result, err = executor.Execute(
		t.Context(),
		durablePresentationRequest(t),
		func(runruntime.ExecutionItemUpdate) error { return nil },
	)
	if err != nil {
		t.Fatalf("Execute() forged selection error=%v", err)
	}
	answer, err := presentationpkg.DecodeTemplate(answerTemplate)
	if err != nil {
		t.Fatal(err)
	}
	if result.Presentation["templateRef"] != presentationpkg.TemplateRef(answer) {
		t.Fatalf("forged selection did not degrade safely: %#v", result.Presentation)
	}
}

func TestDurablePresentationFailsClosedForContextOrTemplateFailure(t *testing.T) {
	t.Run("required context assembly", func(t *testing.T) {
		resolver := &durablePresentationContextResolver{err: errors.New("gathering reader unavailable")}
		executor, catalog, _ := durablePresentationExecutor(t, resolver)
		result, err := executor.Execute(
			t.Context(),
			durablePresentationRequest(t),
			func(runruntime.ExecutionItemUpdate) error { return nil },
		)
		var executionFailure *runruntime.ExecutionFailure
		if !errors.As(err, &executionFailure) || executionFailure.Code == "" {
			t.Fatalf("context failure was not observable: result=%#v err=%v", result, err)
		}
		if catalog.templateCalls != 0 {
			t.Fatalf("presentation ran after context failure: calls=%d", catalog.templateCalls)
		}
	})

	t.Run("template decode", func(t *testing.T) {
		resolver := &durablePresentationContextResolver{}
		executor, catalog, _ := durablePresentationExecutor(t, resolver)
		catalog.template = json.RawMessage(`{"templateId":`)
		result, err := executor.Execute(
			t.Context(),
			durablePresentationRequest(t),
			func(runruntime.ExecutionItemUpdate) error { return nil },
		)
		if err == nil || !strings.Contains(err.Error(), "decode adaptive presentation template") {
			t.Fatalf("template failure was not propagated: result=%#v err=%v", result, err)
		}
		if result.Presentation != nil {
			t.Fatalf("invalid template produced presentation=%#v", result.Presentation)
		}
		if resolver.calls != 1 {
			t.Fatalf("template failure reassembled context %d times", resolver.calls)
		}
	})
}

func durablePresentationExecutor(
	t *testing.T,
	resolver *durablePresentationContextResolver,
) (*orchestration.DurableRunExecutor, *durablePresentationCatalog, *durablePresentationModel) {
	t.Helper()
	descriptor, err := readermodel.NewDescriptor(readermodel.Descriptor{
		DescriptorID:        "circle.gathering_plan_context",
		ResolverRef:         "gathering.plan_context",
		OwnerService:        "circle-service",
		OwnerOperationRefs:  []string{"circle.gathering_plan.GetGatheringPlan"},
		InputSchemaRef:      "circle.GatheringPlanByGatheringQuery",
		OutputSchemaRef:     "assistant.ContextSegment",
		ObjectTypeRefs:      []string{"circle.Gathering"},
		AcceptedSourceKinds: []string{"domain"},
		Authority:           generated.AssistantContextAuthorityDomainCanonical,
		Sensitivity:         generated.AssistantContextSensitivityInternal,
		SurfaceKinds: []readermodel.SurfaceKind{
			readermodel.SurfacePersonal,
		},
		ArtifactPolicy: readermodel.ArtifactInlineOrStored,
		CitationPolicy: readermodel.CitationEntityReference,
	})
	if err != nil {
		t.Fatal(err)
	}
	readerCatalog, err := readerresource.NewCatalog([]readermodel.Descriptor{descriptor})
	if err != nil {
		t.Fatal(err)
	}
	registry, err := skillcontext.NewResolverRegistry(readerCatalog, skillcontext.RegisteredResolver{
		ResolverRef: descriptor.ResolverRef,
		Resolver:    resolver,
	})
	if err != nil {
		t.Fatal(err)
	}
	manifest := skillpkg.Manifest{
		SkillID:      "context_skill",
		DisplayName:  "Gathering 计划上下文测试",
		DomainID:     "circle",
		ProblemClass: "coordination",
		ContextProfile: skillpkg.ContextProfile{
			ProfileID:   "context.test",
			AssetDigest: "sha256:" + strings.Repeat("a", 64),
			Requirements: []skillpkg.ContextRequirement{{
				SlotID:              "gathering.plan",
				Required:            true,
				AcceptedSourceKinds: []string{"domain"},
				Authority: generated.AssistantContextAuthorityDomainCanonical.
					WireName(),
				Sensitivity:      generated.AssistantContextSensitivityInternal.WireName(),
				FreshnessSeconds: 86400,
				TokenBudget:      32,
				ResolverRef:      "gathering.plan_context",
				FallbackPolicy:   "block",
			}},
		},
		Presentation: skillpkg.PresentationProfile{
			ProfileID:    "presentation.test",
			TemplateRefs: []string{"test.context.card"},
			AssetDigest:  "sha256:" + strings.Repeat("b", 64),
		},
	}
	catalog := &durablePresentationCatalog{
		manifest: manifest,
		template: durablePresentationTemplate(t, manifest.SkillID),
	}
	model := &durablePresentationModel{}
	loop := orchestration.NewAgentLoop(
		nil,
		orchestration.ReactRuntime{Model: model},
		func() time.Time { return time.Date(2026, 8, 3, 9, 0, 0, 0, time.UTC) },
	)
	loop.Catalog = catalog
	loop.SkillContexts = skillcontext.NewAssembler(registry)
	return orchestration.NewDurableRunExecutor(loop), catalog, model
}

func durablePresentationRequest(t *testing.T) runruntime.ExecutionRequest {
	t.Helper()
	policy, err := testRunPolicyResolver().ResolveFrozenPolicy(
		t.Context(),
		"assistant-default",
		"user-context",
		"context_skill",
		"circle",
	)
	if err != nil {
		t.Fatal(err)
	}
	return runruntime.ExecutionRequest{
		RunID:                     "run-presentation-context",
		UserID:                    "user-context",
		SessionID:                 "session-context",
		Goal:                      "根据 Gathering 计划给我建议",
		RequestedSkillID:          "context_skill",
		RequestedDomainID:         "circle",
		SkillPackageID:            "quwoquan.official",
		SkillPackageReleaseDigest: "sha256:" + strings.Repeat("c", 64),
		FrozenPolicySelection:     policy,
		ReasoningProfile:          generated.AssistantReasoningProfileBalanced,
		ReasoningPolicy:           durableTestReasoningPolicy(t),
		SurfaceCapabilities: map[string]any{
			"supportedNodeKinds": []string{"card", "text", "markdown"},
			"viewportClass":      "narrow",
		},
		IdempotencyPrefix: "presentation-context",
	}
}

func durablePresentationTemplate(t *testing.T, skillID string) json.RawMessage {
	t.Helper()
	style := presentationpkg.Style{
		Tone:           generated.AssistantPresentationToneNeutral,
		Density:        generated.AssistantPresentationDensityStandard,
		Emphasis:       "normal",
		Variant:        "standard",
		Alignment:      "start",
		SpacingRole:    "related",
		ResponsiveSpan: 12,
	}
	template := presentationpkg.Template{
		TemplateID: "test.context.card",
		SkillID:    skillID,
		InputSchema: map[string]any{
			"type":                 "object",
			"additionalProperties": false,
			"properties": map[string]any{
				"gatheringId": map[string]any{"type": "string"},
				"answer":      map[string]any{"type": "string"},
			},
			"required": []any{"gatheringId", "answer"},
		},
		RootNodeID: "root",
		Nodes: []presentationpkg.Node{
			{NodeID: "root", Kind: generated.AssistantPresentationNodeKindCard, Style: style},
			{
				NodeID:       "gathering",
				ParentNodeID: "root",
				Kind:         generated.AssistantPresentationNodeKindText,
				Binding:      map[string]string{"title": "$.gatheringId"},
				Style:        style,
			},
			{
				NodeID:       "answer",
				ParentNodeID: "root",
				Order:        1,
				Kind:         generated.AssistantPresentationNodeKindMarkdown,
				Binding:      map[string]string{"body": "$.answer"},
				Style:        style,
			},
		},
		FallbackMarkdown:        "无法展示行程回答。",
		FallbackMarkdownBinding: "$.answer",
	}
	withoutDigest, err := json.Marshal(template)
	if err != nil {
		t.Fatal(err)
	}
	var document map[string]any
	if err := json.Unmarshal(withoutDigest, &document); err != nil {
		t.Fatal(err)
	}
	delete(document, "assetDigest")
	canonical, err := json.Marshal(document)
	if err != nil {
		t.Fatal(err)
	}
	digest := sha256.Sum256(canonical)
	template.AssetDigest = "sha256:" + hex.EncodeToString(digest[:])
	raw, err := json.Marshal(template)
	if err != nil {
		t.Fatal(err)
	}
	return raw
}

func durableAnswerPresentationTemplate(t *testing.T, skillID string) json.RawMessage {
	t.Helper()
	template := presentationpkg.Template{
		TemplateID: "assistant.answer.default",
		SkillID:    skillID,
		InputSchema: map[string]any{
			"type":                 "object",
			"additionalProperties": false,
			"properties": map[string]any{
				"answer": map[string]any{"type": "string"},
			},
			"required": []any{"answer"},
		},
		RootNodeID: "answer",
		Nodes: []presentationpkg.Node{{
			NodeID: "answer",
			Kind:   generated.AssistantPresentationNodeKindMarkdown,
			Binding: map[string]string{
				"body": "$.answer",
			},
			Style: presentationpkg.Style{
				Tone:           generated.AssistantPresentationToneNeutral,
				Density:        generated.AssistantPresentationDensityStandard,
				Emphasis:       "normal",
				Variant:        "standard",
				Alignment:      "start",
				SpacingRole:    "related",
				ResponsiveSpan: 12,
			},
		}},
		FallbackMarkdown:        "无法展示回答。",
		FallbackMarkdownBinding: "$.answer",
	}
	// Match presentation.Catalog digest rules: hash the JSON document with
	// assetDigest removed, not the struct marshal that still contains "".
	withoutDigest, err := json.Marshal(template)
	if err != nil {
		t.Fatal(err)
	}
	var document map[string]any
	if err := json.Unmarshal(withoutDigest, &document); err != nil {
		t.Fatal(err)
	}
	delete(document, "assetDigest")
	canonical, err := json.Marshal(document)
	if err != nil {
		t.Fatal(err)
	}
	sum := sha256.Sum256(canonical)
	template.AssetDigest = "sha256:" + hex.EncodeToString(sum[:])
	raw, err := json.Marshal(template)
	if err != nil {
		t.Fatal(err)
	}
	return raw
}

func presentationNodeTitle(document map[string]any, nodeID string) string {
	nodes, _ := document["nodes"].([]any)
	for _, value := range nodes {
		node, _ := value.(map[string]any)
		if node["nodeId"] == nodeID {
			title, _ := node["title"].(string)
			return title
		}
	}
	return ""
}
