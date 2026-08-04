// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/context-assembly-slot-filling/spec.md
package assistant_run_test

import (
	"testing"

	channelpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/channel"
	contextassembly "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/contextassembly"
	orchestration "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
)

func assetDrivenRequiredSlot(
	slotID string,
	valueType string,
	parserRefs []string,
	aliases []string,
	prompt string,
) skillpkg.SlotDefinition {
	return skillpkg.SlotDefinition{
		SlotID:         slotID,
		Required:       true,
		ValueType:      valueType,
		ParserRefs:     parserRefs,
		Aliases:        aliases,
		SourcePriority: []string{skillpkg.SlotSourceUserQuery},
		Clarification: skillpkg.SlotClarification{
			Policy:      skillpkg.SlotClarificationClarify,
			TargetSlot:  "answer_sufficiency",
			Prompt:      prompt,
			Suggestions: []string{"依赖反转", "上下文治理"},
			RetryPolicy: "single_retry",
		},
	}
}

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/context-assembly-slot-filling/spec.md#gwt-001
func TestWorkshopConfirmedSlotFreezesAndReturnsAsSessionSummaryRecall(t *testing.T) {
	definition := assetDrivenRequiredSlot(
		"workshop_topic",
		skillpkg.SlotValueTypeText,
		[]string{skillpkg.SlotParserTextAfterAlias},
		[]string{"议题", "主题"},
		"这次工作坊要讨论什么议题？",
	)
	first, err := contextassembly.NewContextOrchestrator().Assemble(
		t.Context(),
		contextassembly.AssemblyInput{
			Turn: assistant.AssistantTurn{
				Input: assistant.AssistantTurnInput{Text: "议题是依赖反转"},
			},
			DomainID:   "workshop",
			SlotSchema: skillpkg.SlotSchema{Slots: []skillpkg.SlotDefinition{definition}},
			Channel:    channelpkg.Personal(),
		},
	)
	if err != nil {
		t.Fatalf("assemble first turn: %v", err)
	}
	confirmed, err := contextassembly.FreezeConfirmedSlots(first.SlotState)
	if err != nil {
		t.Fatalf("freeze confirmed slots: %v", err)
	}
	mutated := first.SlotState.Slots[definition.SlotID]
	mutated.Value = "被外部修改"
	first.SlotState.Slots[definition.SlotID] = mutated
	if confirmed[definition.SlotID] != "依赖反转" {
		t.Fatalf("frozen confirmed slots were mutable: %#v", confirmed)
	}

	summary := orchestration.ProjectExecutionContextSummary(
		"run-workshop",
		&runruntime.SessionContinuity{
			SummaryID:      "summary-before-workshop",
			Text:           "此前只确认了工作坊地点。",
			FromTurnID:     "run-before-workshop",
			ToTurnID:       "run-before-workshop",
			TurnCount:      1,
			ConfirmedSlots: map[string]string{"meeting_place": "杭州"},
		},
		confirmed,
	)
	definition.SourcePriority = []string{skillpkg.SlotSourceSessionSummary}
	second, err := contextassembly.NewContextOrchestrator().Assemble(
		t.Context(),
		contextassembly.AssemblyInput{
			Turn: assistant.AssistantTurn{
				Input:          assistant.AssistantTurnInput{Text: "继续准备工作坊"},
				ContextSummary: summary,
			},
			DomainID:   "workshop",
			SlotSchema: skillpkg.SlotSchema{Slots: []skillpkg.SlotDefinition{definition}},
			Channel:    channelpkg.Personal(),
		},
	)
	if err != nil {
		t.Fatalf("assemble resumed turn: %v", err)
	}
	resumed := second.SlotState.Slots[definition.SlotID]
	if resumed.Value != "依赖反转" ||
		resumed.Source != skillpkg.SlotSourceSessionSummary ||
		resumed.Status.WireName() != "inferred" {
		t.Fatalf("resumed descriptor slot=%#v summary=%#v", resumed, summary)
	}
}

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/context-assembly-slot-filling/spec.md#gwt-001
func TestFrozenSlotDescriptorAddsVerticalInputWithoutRuntimeBranch(t *testing.T) {
	definition := assetDrivenRequiredSlot(
		"workshop_topic",
		skillpkg.SlotValueTypeText,
		[]string{skillpkg.SlotParserTextAfterAlias},
		[]string{"议题", "主题"},
		"这次工作坊要讨论什么议题？",
	)
	result, err := contextassembly.NewContextOrchestrator().Assemble(
		t.Context(),
		contextassembly.AssemblyInput{
			Turn: assistant.AssistantTurn{
				Input: assistant.AssistantTurnInput{Text: "议题是依赖反转"},
			},
			DomainID: "workshop",
			SlotSchema: skillpkg.SlotSchema{
				Slots:   []skillpkg.SlotDefinition{definition},
				StateID: "workshop_context",
			},
			Channel: channelpkg.Personal(),
		},
	)
	if err != nil {
		t.Fatalf("Assemble(): %v", err)
	}
	value := result.SlotState.Slots[definition.SlotID]
	if !result.CanEnterDomain || len(result.FillTasks) != 0 ||
		value.Value != "依赖反转" || value.Source != skillpkg.SlotSourceUserQuery ||
		value.Status.WireName() != "confirmed" {
		t.Fatalf("asset-driven slot result=%#v value=%#v", result, value)
	}
}

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/context-assembly-slot-filling/spec.md#gwt-001
func TestFrozenSlotDescriptorOwnsClarificationLanguage(t *testing.T) {
	definition := assetDrivenRequiredSlot(
		"workshop_topic",
		skillpkg.SlotValueTypeText,
		[]string{skillpkg.SlotParserTextAfterAlias},
		[]string{"议题", "主题"},
		"这次工作坊要讨论什么议题？",
	)
	result, err := contextassembly.NewContextOrchestrator().Assemble(
		t.Context(),
		contextassembly.AssemblyInput{
			Turn:       assistant.AssistantTurn{Input: assistant.AssistantTurnInput{Text: "帮我准备工作坊"}},
			DomainID:   "workshop",
			SlotSchema: skillpkg.SlotSchema{Slots: []skillpkg.SlotDefinition{definition}},
			Channel:    channelpkg.Personal(),
		},
	)
	if err != nil {
		t.Fatalf("Assemble(): %v", err)
	}
	if result.CanEnterDomain || len(result.FillTasks) != 1 {
		t.Fatalf("fill tasks=%#v canEnter=%v", result.FillTasks, result.CanEnterDomain)
	}
	task := result.FillTasks[0]
	if task.SlotID != definition.SlotID ||
		task.Prompt != definition.Clarification.Prompt ||
		len(task.Suggestions) != 2 || task.Suggestions[0] != "依赖反转" {
		t.Fatalf("fill task=%#v want frozen clarification semantics", task)
	}
}

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/context-assembly-slot-filling/spec.md#gwt-001
func TestRequiredSlotWithoutPackageClarificationPromptFailsClosed(t *testing.T) {
	definition := assetDrivenRequiredSlot(
		"workshop_topic",
		skillpkg.SlotValueTypeText,
		[]string{skillpkg.SlotParserTextAfterAlias},
		[]string{"议题", "主题"},
		"",
	)
	_, err := contextassembly.NewContextOrchestrator().Assemble(
		t.Context(),
		contextassembly.AssemblyInput{
			Turn: assistant.AssistantTurn{
				Input: assistant.AssistantTurnInput{Text: "帮我准备工作坊"},
			},
			DomainID:   "workshop",
			SlotSchema: skillpkg.SlotSchema{Slots: []skillpkg.SlotDefinition{definition}},
			Channel:    channelpkg.Personal(),
		},
	)
	if err == nil {
		t.Fatal("required slot without package-owned clarification prompt must fail closed")
	}
}

// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/context-assembly-slot-filling/spec.md#gwt-001
func TestFrozenSlotDescriptorControlsSourcePriorityWithoutSlotNameBranch(t *testing.T) {
	definition := skillpkg.SlotDefinition{
		SlotID:         "meeting_place",
		ValueType:      skillpkg.SlotValueTypeLocation,
		ParserRefs:     []string{skillpkg.SlotParserLocationBeforeAlias},
		Aliases:        []string{"会场"},
		SourcePriority: []string{skillpkg.SlotSourceDevice, skillpkg.SlotSourceUserQuery},
		Clarification:  skillpkg.SlotClarification{Policy: skillpkg.SlotClarificationOmit},
	}
	result, err := contextassembly.NewContextOrchestrator().Assemble(
		t.Context(),
		contextassembly.AssemblyInput{
			Turn: assistant.AssistantTurn{
				Input: assistant.AssistantTurnInput{Text: "苏州会场"},
			},
			Device: contextassembly.DeviceContextResponse{
				Status: "available",
				Facts:  map[string]any{"cityLabel": "杭州"},
			},
			DomainID:   "events",
			SlotSchema: skillpkg.SlotSchema{Slots: []skillpkg.SlotDefinition{definition}},
			Channel:    channelpkg.Personal(),
		},
	)
	if err != nil {
		t.Fatalf("Assemble(): %v", err)
	}
	value := result.SlotState.Slots[definition.SlotID]
	if value.Value != "杭州" || value.Source != skillpkg.SlotSourceDevice {
		t.Fatalf("slot=%#v want descriptor-prioritized device value", value)
	}
}
