// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/spec.md#sit-001
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/trajectory-replay-evaluation-gate/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/trajectory-replay-evaluation-gate/spec.md#gwt-002
package local_contract

import (
	"encoding/json"
	"reflect"
	"sort"
	"strings"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/simulator"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/skill"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/assistant"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/infrastructure/assets"
)

func TestAgentReplayEvaluationGate(t *testing.T) {
	catalog, err := orchestration.LoadAssistantDomainSkillCatalog()
	if err != nil {
		t.Fatalf("LoadAssistantDomainSkillCatalog(): %v", err)
	}
	corpus, err := simulator.LoadReplayCorpus(
		assistantSkillAssetRoot(t) + "/replay_corpus.v1.json",
	)
	if err != nil {
		t.Fatalf("LoadReplayCorpus(): %v", err)
	}
	assetsBySkill := assertReplayCorpusCoversCatalog(t, catalog, corpus)
	productionRouter := skillpkg.NewRouter(catalog)
	for _, manifest := range catalog {
		if !manifest.IsProactive() {
			assertReplayCorpusHasProductionRoutedCase(
				t,
				productionRouter,
				manifest,
				assetsBySkill[manifest.SkillID],
			)
		}
	}
	promptAssets, err := assets.NewDefaultPromptAssetLoader()
	if err != nil {
		t.Fatalf("NewDefaultPromptAssetLoader(): %v", err)
	}
	runner := simulator.Runner{
		Now: func() time.Time {
			return time.Date(2026, 7, 28, 10, 0, 0, 0, time.UTC)
		},
		PromptAssets: promptAssets,
		Catalog:      catalog,
	}
	seenCaseIDs := map[string]bool{}
	for _, manifest := range catalog {
		cases := replayCasesForManifest(t, manifest, assetsBySkill[manifest.SkillID])
		for _, evaluationCase := range cases {
			evaluationCase := evaluationCase
			if seenCaseIDs[evaluationCase.Replay.ReplayCaseID] {
				t.Fatalf("duplicate replayCaseId %q", evaluationCase.Replay.ReplayCaseID)
			}
			seenCaseIDs[evaluationCase.Replay.ReplayCaseID] = true
			t.Run(evaluationCase.Replay.ReplayCaseID, func(t *testing.T) {
				wireCase := roundTripReplayCase(t, evaluationCase.Replay)
				transcript, err := runner.Run(t.Context(), wireCase)
				if err != nil {
					t.Fatalf("Run(): %v", err)
				}
				poisoned := wireCase
				poisoned.Expectations.SelectedSkillID = "poisoned_skill"
				poisoned.Expectations.SelectedDomainID = "poisoned_domain"
				poisoned.Expectations.ExpectedToolNames = []string{"poisoned_tool"}
				poisoned.Expectations.FinalAnswerMode = "blocked"
				poisonedTranscript, err := runner.Run(t.Context(), poisoned)
				if err != nil {
					t.Fatalf("Run(poisoned expectations): %v", err)
				}
				if !reflect.DeepEqual(poisonedTranscript, transcript) {
					t.Fatalf(
						"expectation mutation changed execution transcript\noriginal=%#v\npoisoned=%#v",
						transcript,
						poisonedTranscript,
					)
				}
				assertReplayTrajectory(
					t,
					manifest,
					wireCase,
					evaluationCase.Scenario,
					transcript,
				)
			})
		}
	}
}

func assertReplayCorpusCoversCatalog(
	t *testing.T,
	catalog []skillpkg.Manifest,
	corpus simulator.ReplayCorpus,
) map[string]simulator.ReplayCorpusAsset {
	t.Helper()
	catalogIDs := map[string]bool{}
	assetsBySkill := make(map[string]simulator.ReplayCorpusAsset, len(corpus.Assets))
	seenAssetIDs := map[string]bool{}
	seenCaseIDs := map[string]bool{}
	for _, asset := range corpus.Assets {
		if seenAssetIDs[asset.AssetID] {
			t.Fatalf("duplicate replay assetId %q", asset.AssetID)
		}
		if _, duplicate := assetsBySkill[asset.SkillID]; duplicate {
			t.Fatalf("duplicate replay asset for skill %q", asset.SkillID)
		}
		seenAssetIDs[asset.AssetID] = true
		assetsBySkill[asset.SkillID] = asset
		for _, replayCase := range asset.Cases {
			if seenCaseIDs[replayCase.CaseID] {
				t.Fatalf("duplicate replay caseId %q", replayCase.CaseID)
			}
			seenCaseIDs[replayCase.CaseID] = true
		}
	}
	for _, manifest := range catalog {
		catalogIDs[manifest.SkillID] = true
		asset, ok := assetsBySkill[manifest.SkillID]
		if !ok {
			t.Fatalf("skill %q has no replay corpus", manifest.SkillID)
		}
		if err := asset.Validate(manifest); err != nil {
			t.Fatalf("validate replay asset for %s: %v", manifest.SkillID, err)
		}
		assertReplayAssetChangesSkillReleaseDigest(t, manifest, asset)
	}
	for skillID := range assetsBySkill {
		if !catalogIDs[skillID] {
			t.Fatalf("replay corpus references unknown skill %q", skillID)
		}
	}
	return assetsBySkill
}

func assertReplayCorpusHasProductionRoutedCase(
	t *testing.T,
	router skillpkg.Router,
	manifest skillpkg.Manifest,
	asset simulator.ReplayCorpusAsset,
) {
	t.Helper()
	for _, replayCase := range asset.Cases {
		routed := router.Route(assistant.AssistantTurn{
			Input: assistant.AssistantTurnInput{Text: replayCase.Input},
		})
		if routed.SkillID == manifest.SkillID {
			return
		}
	}
	t.Fatalf(
		"skill %q replay corpus has no input routed by production catalog",
		manifest.SkillID,
	)
}

func assertReplayAssetChangesSkillReleaseDigest(
	t *testing.T,
	manifest skillpkg.Manifest,
	asset simulator.ReplayCorpusAsset,
) {
	t.Helper()
	originalDigest, err := manifest.ResolvedReleaseDigest()
	if err != nil {
		t.Fatalf("resolve original skill release digest: %v", err)
	}
	mutated := asset
	mutated.Cases = append([]simulator.ReplayCorpusCase(nil), asset.Cases...)
	mutated.Cases[0].Input += "（digest mutation）"
	_, proof, err := (simulator.ReplayCorpus{
		SchemaVersion: 1,
		Assets:        []simulator.ReplayCorpusAsset{mutated},
	}).ResolveAsset(mutated.AssetID, mutated.SkillID)
	if err != nil {
		t.Fatalf("resolve mutated replay proof: %v", err)
	}
	mutatedManifest := manifest
	mutatedManifest.ResolvedAssetRefs = make(
		map[string]skillpkg.AssetProof,
		len(manifest.ResolvedAssetRefs),
	)
	for kind, current := range manifest.ResolvedAssetRefs {
		mutatedManifest.ResolvedAssetRefs[kind] = current
	}
	mutatedManifest.ResolvedAssetRefs["replay"] = proof
	mutatedDigest, err := mutatedManifest.ResolvedReleaseDigest()
	if err != nil {
		t.Fatalf("resolve mutated skill release digest: %v", err)
	}
	if mutatedDigest == originalDigest {
		t.Fatalf(
			"skill %q replay bytes did not change release digest %q",
			manifest.SkillID,
			originalDigest,
		)
	}
}

type replayEvaluationCase struct {
	Scenario string
	Replay   assistant.ReplayCase
}

func replayCasesForManifest(
	t *testing.T,
	manifest skillpkg.Manifest,
	asset simulator.ReplayCorpusAsset,
) []replayEvaluationCase {
	t.Helper()
	cases := make([]replayEvaluationCase, 0, len(asset.Cases))
	for _, corpusCase := range asset.Cases {
		prompt := corpusCase.Input
		caseID := corpusCase.CaseID
		clarificationSlotIDs := []string{}
		expectedToolNames := []string{}
		expectedReferenceURLs := []string{}
		finalAnswerMode := "full"
		modelScript := []assistant.ReplayModelStep{}
		toolScript := []assistant.ReplayToolStep{}
		switch corpusCase.Scenario {
		case "slot_clarification":
			clarificationSlotIDs = []string{manifest.SlotSchema.RequiredSlots[0]}
			finalAnswerMode = "clarify"
		case "direct_answer":
			modelScript = directAnswerScript(manifest, prompt)
		case "failure_recovery":
			toolName := manifest.ToolPolicy.PreferredTools[0]
			expectedToolNames = []string{toolName}
			finalAnswerMode = "blocked"
			modelScript = toolCallScript(manifest, prompt)
			toolScript = []assistant.ReplayToolStep{{
				ToolName: toolName,
				Input:    map[string]any{"query": prompt},
				Failure: map[string]any{
					"code": "ASSISTANT.DEPENDENCY.replay_tool_unavailable",
				},
			}}
		default:
			toolName := manifest.ToolPolicy.PreferredTools[0]
			referenceURL := "https://example.com/assistant-eval/" + caseID
			expectedToolNames = []string{toolName}
			expectedReferenceURLs = []string{referenceURL}
			modelScript = groundedAnswerScript(manifest, prompt, referenceURL)
			toolScript = []assistant.ReplayToolStep{{
				ToolName: toolName,
				Input:    map[string]any{"query": prompt},
				Result: map[string]any{
					"kind":     "tool_result",
					"summary":  manifest.DisplayName + " 已取得可核验结果。",
					"reliable": true,
					"references": []map[string]any{{
						"title":      manifest.DisplayName + " 权威资料",
						"objectType": "web.document",
						"url":        referenceURL,
						"source":     "assistant_eval_source",
						"snippet":    "该引用直接支持本 Case 的回答。",
					}},
				},
			}}
		}
		cases = append(cases, replayEvaluationCase{
			Scenario: corpusCase.Scenario,
			Replay: assistant.ReplayCase{
				ReplayCaseID: caseID,
				Title:        manifest.DisplayName + "轨迹回放",
				Request: assistant.ReplayRequest{
					SessionID:     "asn_" + caseID,
					TurnID:        "atn_" + caseID,
					UserID:        "persona_agent_eval",
					InputText:     prompt,
					SkillID:       manifest.SkillID,
					DomainID:      manifest.DomainID,
					ClientContext: map[string]any{"surfaceId": "assistant.personal"},
				},
				FakeModelScript: modelScript,
				FakeToolScript:  toolScript,
				Expectations: assistant.ReplayExpectations{
					SelectedSkillID:              manifest.SkillID,
					SelectedDomainID:             manifest.DomainID,
					ExpectedToolNames:            expectedToolNames,
					ExpectedClarificationSlotIDs: clarificationSlotIDs,
					ExpectedReferenceURLs:        expectedReferenceURLs,
					FinalAnswerMode:              finalAnswerMode,
				},
			},
		})
	}
	return cases
}

func toolCallScript(
	manifest skillpkg.Manifest,
	prompt string,
) []assistant.ReplayModelStep {
	return []assistant.ReplayModelStep{{
		Stage: "reasoning",
		Text:  "需要调用允许的工具取得资料。",
		StructuredDelta: map[string]any{
			"nextAction": "tool_call",
			"toolName":   manifest.ToolPolicy.PreferredTools[0],
			"toolInput":  map[string]any{"query": prompt},
		},
		FinishReason: "tool_use",
	}}
}

func groundedAnswerScript(
	manifest skillpkg.Manifest,
	prompt string,
	referenceURL string,
) []assistant.ReplayModelStep {
	accepted := map[string]any{
		"title":   manifest.DisplayName + " 权威资料",
		"source":  "assistant_eval_source",
		"snippet": "该引用直接支持本 Case 的回答。",
		"destination": map[string]any{
			"kind": "external",
			"url":  referenceURL,
		},
	}
	forged := map[string]any{
		"title":  "未由工具返回的伪造资料",
		"source": "forged",
		"destination": map[string]any{
			"kind": "external",
			"url":  "https://forged.invalid/not-from-tool",
		},
	}
	return []assistant.ReplayModelStep{
		{
			Stage: "reasoning",
			Text:  "需要调用允许的工具取得资料。",
			StructuredDelta: map[string]any{
				"nextAction": "tool_call",
				"toolName":   manifest.ToolPolicy.PreferredTools[0],
				"toolInput":  map[string]any{"query": prompt},
			},
			FinishReason: "tool_use",
		},
		{
			Stage: "evidence_processing",
			Text:  "已核对资料覆盖范围。",
			StructuredDelta: map[string]any{
				"retrievalProcessing": map[string]any{
					"processingSummary": "已核对资料覆盖范围。",
					"selectedKeyPoints": []string{"关键结论已获得资料支持"},
					"acceptedReferences": []map[string]any{
						forged,
						accepted,
					},
				},
				"evidenceSufficient": true,
			},
			FinishReason: "stop",
		},
		{
			Stage:        "final",
			Text:         manifest.DisplayName + "已基于可核验资料完成回答。",
			FinishReason: "stop",
		},
	}
}

func directAnswerScript(
	manifest skillpkg.Manifest,
	_ string,
) []assistant.ReplayModelStep {
	return []assistant.ReplayModelStep{
		{
			Stage: "reasoning",
			Text:  "该问题可直接回答。",
			StructuredDelta: map[string]any{
				"nextAction": "answer",
			},
			FinishReason: "stop",
		},
		{
			Stage:        "final",
			Text:         manifest.DisplayName + "已直接完成回答。",
			FinishReason: "stop",
		},
	}
}

func roundTripReplayCase(
	t *testing.T,
	replay assistant.ReplayCase,
) assistant.ReplayCase {
	t.Helper()
	raw, err := json.Marshal(replay)
	if err != nil {
		t.Fatalf("marshal assistant_replay_case: %v", err)
	}
	var decoded assistant.ReplayCase
	if err := json.Unmarshal(raw, &decoded); err != nil {
		t.Fatalf("unmarshal assistant_replay_case: %v", err)
	}
	if strings.TrimSpace(decoded.Expectations.SelectedSkillID) == "" ||
		strings.TrimSpace(decoded.Expectations.SelectedDomainID) == "" ||
		strings.TrimSpace(decoded.Expectations.FinalAnswerMode) == "" {
		t.Fatalf("assistant_replay_case lost required expectations: %#v", decoded.Expectations)
	}
	return decoded
}

func assertReplayTrajectory(
	t *testing.T,
	manifest skillpkg.Manifest,
	replay assistant.ReplayCase,
	scenario string,
	transcript simulator.Transcript,
) {
	t.Helper()
	expectations := replay.Expectations
	if scenario == "failure_recovery" {
		if transcript.Failure == nil {
			t.Fatal("failure recovery case completed without its scripted dependency failure")
		}
	} else if transcript.Failure != nil {
		t.Fatalf("runtimeFailure=%#v", transcript.Failure)
	}
	if transcript.SelectedSkillID != expectations.SelectedSkillID ||
		transcript.SelectedDomainID != expectations.SelectedDomainID {
		t.Fatalf(
			"selected skill/domain=%s/%s, want %s/%s",
			transcript.SelectedSkillID,
			transcript.SelectedDomainID,
			expectations.SelectedSkillID,
			expectations.SelectedDomainID,
		)
	}
	actualTools := make([]string, 0, len(transcript.ToolCalls))
	allowedTools := stringSetForReplay(manifest.ToolPolicy.AllowedTools)
	for _, call := range transcript.ToolCalls {
		actualTools = append(actualTools, call.ToolName)
		if !allowedTools[call.ToolName] {
			t.Fatalf(
				"tool %q is outside skill %q allowedTools=%v",
				call.ToolName,
				manifest.SkillID,
				manifest.ToolPolicy.AllowedTools,
			)
		}
	}
	if !reflect.DeepEqual(actualTools, expectations.ExpectedToolNames) {
		t.Fatalf("tool calls=%v, want %v", actualTools, expectations.ExpectedToolNames)
	}
	if !reflect.DeepEqual(
		transcript.ClarificationSlotIDs,
		expectations.ExpectedClarificationSlotIDs,
	) {
		t.Fatalf(
			"clarification slots=%v, want %v",
			transcript.ClarificationSlotIDs,
			expectations.ExpectedClarificationSlotIDs,
		)
	}
	actualReferences := sortedReplayStrings(transcript.ReferenceURLs)
	expectedReferences := sortedReplayStrings(expectations.ExpectedReferenceURLs)
	if !reflect.DeepEqual(actualReferences, expectedReferences) {
		t.Fatalf("reference URLs=%v, want %v", actualReferences, expectedReferences)
	}
	for _, referenceURL := range transcript.ReferenceURLs {
		if referenceURL == "https://forged.invalid/not-from-tool" {
			t.Fatal("user-visible references accepted a URL absent from tool results")
		}
	}
	if transcript.FinalAnswerMode != expectations.FinalAnswerMode {
		t.Fatalf(
			"finalAnswerMode=%q, want %q",
			transcript.FinalAnswerMode,
			expectations.FinalAnswerMode,
		)
	}
}

func sortedReplayStrings(values []string) []string {
	sorted := append([]string(nil), values...)
	sort.Strings(sorted)
	return sorted
}

func stringSetForReplay(values []string) map[string]bool {
	set := make(map[string]bool, len(values))
	for _, value := range values {
		set[value] = true
	}
	return set
}
