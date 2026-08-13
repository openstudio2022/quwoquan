// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/spec.md#sit-001
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/trajectory-replay-evaluation-gate/spec.md#gwt-001
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/trajectory-replay-evaluation-gate/spec.md#gwt-001.t1
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/trajectory-replay-evaluation-gate/spec.md#gwt-001.t2
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/trajectory-replay-evaluation-gate/spec.md#gwt-001.t3
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/trajectory-replay-evaluation-gate/spec.md#gwt-002
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/trajectory-replay-evaluation-gate/spec.md#gwt-002.t1
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/trajectory-replay-evaluation-gate/spec.md#gwt-002.t2
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/trajectory-replay-evaluation-gate/spec.md#gwt-002.t3
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/trajectory-replay-evaluation-gate/spec.md#gwt-002.t4
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/trajectory-replay-evaluation-gate/spec.md#gwt-002.t5
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/trajectory-replay-evaluation-gate/spec.md#gwt-002.t6
// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/trajectory-replay-evaluation-gate/spec.md#gwt-002.t7
package assistant_run_test

import (
	"encoding/json"
	"fmt"
	"reflect"
	"sort"
	"strings"
	"testing"
	"time"

	rtfailures "quwoquan_service/runtime/failures"
	orchestration "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	simulator "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/replay"
	assistantstreaming "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/streaming"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	resourcebuilder "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/infrastructure/resource"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
	"quwoquan_service/services/assistant-service/tests/support/promptassets"
)

func TestAgentReplayEvaluationGate(t *testing.T) {
	bundle, err := resourcebuilder.NewSourceBuilder().Compile(t.Context())
	if err != nil {
		t.Fatalf("CompileAssistantSkillSource(): %v", err)
	}
	catalog, err := orchestration.ValidateAssistantDomainSkillCatalog(
		bundle.ResolvedManifests,
	)
	if err != nil {
		t.Fatalf("ValidateAssistantDomainSkillCatalog(): %v", err)
	}
	corpus := bundle.ReplayCorpus
	assetsBySkill := assertReplayCorpusCoversCatalog(t, catalog, corpus)
	assertReplayCorpusProductionRouting(t, catalog, assetsBySkill)
	runner := simulator.Runner{
		Now: func() time.Time {
			return time.Date(2026, 7, 28, 10, 0, 0, 0, time.UTC)
		},
		PromptAssets: promptassets.MustResolver(t),
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
	corpus skillpkg.ReplayCorpus,
) map[string]skillpkg.ReplayCorpusAsset {
	t.Helper()
	catalogIDs := map[string]bool{}
	assetsBySkill := make(map[string]skillpkg.ReplayCorpusAsset, len(corpus.Assets))
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

// assertReplayCorpusProductionRouting 要求全部 reactive Case 的输入都必须由
// production Router（与生产相同的 reactive 候选收窄）路由到期望技能；任何
// 偏离都逐条列出并整体硬失败，不接受「至少一条可路由」的弱口径。
func assertReplayCorpusProductionRouting(
	t *testing.T,
	catalog []skillpkg.Manifest,
	assetsBySkill map[string]skillpkg.ReplayCorpusAsset,
) {
	t.Helper()
	reactiveCatalog := make([]skillpkg.Manifest, 0, len(catalog))
	for _, manifest := range catalog {
		if manifest.IsReactive() {
			reactiveCatalog = append(reactiveCatalog, manifest)
		}
	}
	router := skillpkg.NewRouter(reactiveCatalog)
	violations := []string{}
	for _, manifest := range catalog {
		if !manifest.IsReactive() {
			continue
		}
		for _, replayCase := range assetsBySkill[manifest.SkillID].Cases {
			if replayCase.TriggerType == skillpkg.ReplayTriggerTypeProactive {
				continue
			}
			routed := router.Route(assistant.AssistantTurn{
				Input: assistant.AssistantTurnInput{Text: replayCase.Input},
			})
			if routed.SkillID != manifest.SkillID {
				violations = append(violations, fmt.Sprintf(
					"case %s input %q routed to %q, want %q",
					replayCase.CaseID,
					replayCase.Input,
					routed.SkillID,
					manifest.SkillID,
				))
			}
		}
	}
	if len(violations) > 0 {
		t.Fatalf(
			"%d replay cases are not production-routable:\n%s",
			len(violations),
			strings.Join(violations, "\n"),
		)
	}
}

func assertReplayAssetChangesSkillReleaseDigest(
	t *testing.T,
	manifest skillpkg.Manifest,
	asset skillpkg.ReplayCorpusAsset,
) {
	t.Helper()
	originalDigest, err := manifest.ResolvedReleaseDigest()
	if err != nil {
		t.Fatalf("resolve original skill release digest: %v", err)
	}
	mutated := asset
	mutated.Cases = append([]skillpkg.ReplayCorpusCase(nil), asset.Cases...)
	mutated.Cases[0].Input += "（digest mutation）"
	_, proof, err := (skillpkg.ReplayCorpus{
		Assets: []skillpkg.ReplayCorpusAsset{mutated},
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
	asset skillpkg.ReplayCorpusAsset,
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
			slotID := strings.TrimSpace(corpusCase.ClarificationSlotID)
			if slotID == "" {
				for _, definition := range manifest.SlotSchema.Slots {
					if definition.Required {
						slotID = definition.SlotID
						break
					}
				}
			}
			if slotID == "" {
				t.Fatalf("slot clarification replay %q has no clarificationSlotId", caseID)
			}
			clarificationSlotIDs = []string{slotID}
			finalAnswerMode = "clarify"
			modelScript = clarificationScript(slotID)
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
		case "recovery", "retry":
			// 恢复/重试轨迹：首次工具失败（恢复合同 skip_tool），第二次成功并
			// 产出可核验引用；最终回答必须完整且引用只被计入一次。
			toolName := manifest.ToolPolicy.PreferredTools[0]
			referenceURL := "https://example.com/assistant-eval/" + caseID
			expectedToolNames = []string{toolName, toolName}
			expectedReferenceURLs = []string{referenceURL}
			modelScript = retryToolCallScript(manifest, prompt, referenceURL)
			toolScript = []assistant.ReplayToolStep{
				{
					ToolName: toolName,
					Input:    map[string]any{"query": prompt},
					Failure: map[string]any{
						"code":           "ASSISTANT.DEPENDENCY.replay_tool_unavailable",
						"recoveryAction": "skip_tool",
					},
				},
				successToolStep(manifest, toolName, prompt, referenceURL),
			}
		case "timeout":
			// 超时轨迹：工具按恢复合同 fail_turn 超时失败，必须产生结构化
			// timeout 失败并阻断最终回答。
			toolName := manifest.ToolPolicy.PreferredTools[0]
			expectedToolNames = []string{toolName}
			finalAnswerMode = "blocked"
			modelScript = toolCallScript(manifest, prompt)
			toolScript = []assistant.ReplayToolStep{{
				ToolName: toolName,
				Input:    map[string]any{"query": prompt},
				Failure: map[string]any{
					"code": "ASSISTANT.DEPENDENCY.replay_tool_timeout",
					"kind": "timeout",
				},
			}}
		case "approval":
			// 审批轨迹：工具返回待确认提案，运行进入 waiting_approval 中断态；
			// 没有最终回答，expectations.finalAnswerMode 以 blocked 声明该事实。
			toolName := manifest.ToolPolicy.PreferredTools[0]
			expectedToolNames = []string{toolName}
			finalAnswerMode = "blocked"
			modelScript = toolCallScript(manifest, prompt)
			toolScript = []assistant.ReplayToolStep{{
				ToolName: toolName,
				Input:    map[string]any{"query": prompt},
				Status:   "waiting_confirmation",
				Result: map[string]any{
					"proposal": map[string]any{
						"actionKind": "assistant_eval_action",
						"summary":    manifest.DisplayName + " 待用户审批的动作提案。",
					},
				},
			}}
		default:
			toolName := manifest.ToolPolicy.PreferredTools[0]
			referenceURL := "https://example.com/assistant-eval/" + caseID
			expectedToolNames = []string{toolName}
			expectedReferenceURLs = []string{referenceURL}
			modelScript = groundedAnswerScript(manifest, prompt, referenceURL)
			toolScript = []assistant.ReplayToolStep{
				successToolStep(manifest, toolName, prompt, referenceURL),
			}
		}
		request := assistant.ReplayRequest{
			SessionID:     "asn_" + caseID,
			TurnID:        "atn_" + caseID,
			UserID:        "persona_agent_eval",
			InputText:     prompt,
			SkillID:       manifest.SkillID,
			DomainID:      manifest.DomainID,
			TriggerType:   strings.TrimSpace(corpusCase.TriggerType),
			ClientContext: map[string]any{"surfaceId": "assistant.personal"},
		}
		if request.TriggerType == skillpkg.ReplayTriggerTypeProactive {
			// 与生产 Trigger→AssistantRun 相同形状的受信 trigger identity；
			// 缺失或不完整的 proactive Case 由 Runner fail-closed。
			request.TrustedTriggerIdentity = &assistant.AssistantTriggerEnvelope{
				Kind:              "schedule",
				TriggerID:         "trg_" + caseID,
				OccurredAt:        time.Date(2026, 7, 28, 9, 30, 0, 0, time.UTC),
				SubscriptionRef:   "sks_" + caseID,
				Reason:            "subscription_due",
				DedupeKey:         "trg_" + caseID,
				DeliveryPolicyRef: "delivery.quiet_hours.default",
			}
		}
		cases = append(cases, replayEvaluationCase{
			Scenario: corpusCase.Scenario,
			Replay: assistant.ReplayCase{
				ReplayCaseID:    caseID,
				Title:           manifest.DisplayName + "轨迹回放",
				Request:         request,
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

// successToolStep 是带单条可核验引用的确定性成功工具步骤。
func successToolStep(
	manifest skillpkg.Manifest,
	toolName string,
	prompt string,
	referenceURL string,
) assistant.ReplayToolStep {
	return assistant.ReplayToolStep{
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
	}
}

func clarificationScript(slotID string) []assistant.ReplayModelStep {
	return []assistant.ReplayModelStep{{
		Stage: "reasoning",
		Text:  "需要用户确认关键目标后才能安全继续。",
		StructuredDelta: map[string]any{
			"nextAction": "ask_user",
			"askUser": map[string]any{
				"slotId":   slotID,
				"prompt":   "请先确认要处理的旅行信息。",
				"required": true,
			},
		},
		FinishReason: "stop",
	}}
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

// retryToolCallScript 声明「首次失败、第二次成功」的确定性脚本：两轮 reasoning
// 依序请求同一工具，成功后的证据处理只接受一条引用，最终回答完整。
func retryToolCallScript(
	manifest skillpkg.Manifest,
	prompt string,
	referenceURL string,
) []assistant.ReplayModelStep {
	grounded := groundedAnswerScript(manifest, prompt, referenceURL)
	retryReasoning := assistant.ReplayModelStep{
		Stage: "reasoning",
		Text:  "工具暂时不可用，按恢复合同重试同一工具。",
		StructuredDelta: map[string]any{
			"nextAction": "retry",
			"toolName":   manifest.ToolPolicy.PreferredTools[0],
			"toolInput":  map[string]any{"query": prompt},
		},
		FinishReason: "tool_use",
	}
	script := []assistant.ReplayModelStep{grounded[0], retryReasoning}
	return append(script, grounded[1:]...)
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
	switch scenario {
	case "failure_recovery":
		if transcript.Failure == nil {
			t.Fatal("failure recovery case completed without its scripted dependency failure")
		}
	case "timeout":
		if transcript.Failure == nil {
			t.Fatal("timeout case completed without its scripted timeout failure")
		}
		if transcript.Failure.Kind != rtfailures.KindTimeout ||
			transcript.Failure.Code != "ASSISTANT.DEPENDENCY.replay_tool_timeout" {
			t.Fatalf(
				"timeout case failure kind=%q code=%q, want structured timeout failure",
				transcript.Failure.Kind,
				transcript.Failure.Code,
			)
		}
	default:
		if transcript.Failure != nil {
			t.Fatalf("runtimeFailure=%#v", transcript.Failure)
		}
	}
	if scenario == "approval" {
		assertWaitingApprovalTrajectory(t, transcript)
	}
	if scenario == "retry" || scenario == "recovery" {
		assertSingleChargedRecoveryTrajectory(t, transcript)
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
	if scenario == "approval" {
		// waiting_approval 是中断态：turn 没有聚合终态事件，expectations 以
		// blocked 声明「没有最终回答」，transcript 不得伪造 finalAnswerMode。
		if expectations.FinalAnswerMode != "blocked" || transcript.FinalAnswerMode != "" {
			t.Fatalf(
				"approval case finalAnswerMode=%q (expectations %q), want interrupted run without a final answer",
				transcript.FinalAnswerMode,
				expectations.FinalAnswerMode,
			)
		}
		return
	}
	if transcript.FinalAnswerMode != expectations.FinalAnswerMode {
		t.Fatalf(
			"finalAnswerMode=%q, want %q",
			transcript.FinalAnswerMode,
			expectations.FinalAnswerMode,
		)
	}
}

// assertWaitingApprovalTrajectory 断言审批轨迹进入 waiting_approval 中断态：
// 恰有一条携带完整续跑凭据与动作提案的事件，且没有聚合完成事件。
func assertWaitingApprovalTrajectory(
	t *testing.T,
	transcript simulator.Transcript,
) {
	t.Helper()
	waitingEvents := 0
	for _, event := range transcript.Events {
		if event.EventType == string(assistantstreaming.AssistantStreamEventCompleted) {
			t.Fatal("approval case emitted a completed event while waiting for approval")
		}
		if event.EventType != string(assistantstreaming.AssistantStreamEventWaitingApproval) {
			continue
		}
		waitingEvents++
		token, _ := event.Payload["continuationToken"].(string)
		toolUseID, _ := event.Payload["toolUseId"].(string)
		proposal, _ := event.Payload["proposal"].(map[string]any)
		if strings.TrimSpace(token) == "" ||
			strings.TrimSpace(toolUseID) == "" || len(proposal) == 0 {
			t.Fatalf("waiting approval payload is incomplete: %#v", event.Payload)
		}
	}
	if waitingEvents != 1 {
		t.Fatalf("waiting approval events=%d, want exactly 1", waitingEvents)
	}
}

// assertSingleChargedRecoveryTrajectory 断言恢复/重试轨迹恰好完成一次：
// 只有一条聚合完成事件，且重试成功后的引用只被计入一次，不重复计费。
func assertSingleChargedRecoveryTrajectory(
	t *testing.T,
	transcript simulator.Transcript,
) {
	t.Helper()
	completedEvents := 0
	for _, event := range transcript.Events {
		if event.EventType != string(assistantstreaming.AssistantStreamEventCompleted) {
			continue
		}
		completedEvents++
		skillRuns, _ := event.Payload["skillRuns"].([]map[string]any)
		if len(skillRuns) != 1 {
			t.Fatalf("recovery/retry completed skillRuns=%d, want 1", len(skillRuns))
		}
		referenceCount, _ := skillRuns[0]["referenceCount"].(int)
		if referenceCount != 1 {
			t.Fatalf(
				"recovery/retry referenceCount=%d, want the retried reference counted once",
				referenceCount,
			)
		}
	}
	if completedEvents != 1 {
		t.Fatalf("recovery/retry completed events=%d, want exactly 1", completedEvents)
	}
	seenReferences := map[string]bool{}
	for _, referenceURL := range transcript.ReferenceURLs {
		if seenReferences[referenceURL] {
			t.Fatalf("recovery/retry duplicated reference %q", referenceURL)
		}
		seenReferences[referenceURL] = true
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
