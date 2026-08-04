package contextassembly

import (
	"fmt"
	"strings"

	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
)

func resolveSlots(
	input AssemblyInput,
	domainID string,
	hints []RecallHint,
	registry *SlotParserRegistry,
) (SlotState, []ContextFillTask, error) {
	schema, err := skillpkg.NormalizeSlotSchema(input.SlotSchema)
	if err != nil {
		return SlotState{}, nil, fmt.Errorf("invalid frozen skill slot schema: %w", err)
	}
	if registry == nil {
		registry = DefaultSlotParserRegistry()
	}
	state := SlotState{
		DomainID: domainID,
		Slots:    map[string]SlotValue{},
	}
	tasks := make([]ContextFillTask, 0, len(schema.Slots))
	for _, definition := range schema.Slots {
		resolved, ok := resolveSlotDefinition(
			definition,
			input.Turn.Input.Text,
			input.Device,
			hints,
			registry,
		)
		if !ok {
			resolved = SlotValue{
				SlotID: definition.SlotID,
				Status: assistantgenerated.SlotValueStatusMissing,
			}
		}
		state.Slots[definition.SlotID] = resolved
		if !definition.Required ||
			(resolved.Status != assistantgenerated.SlotValueStatusMissing &&
				resolved.Status != assistantgenerated.SlotValueStatusStale &&
				resolved.Status != assistantgenerated.SlotValueStatusConflicted) {
			continue
		}
		state.MissingSlots = append(state.MissingSlots, definition.SlotID)
		task, err := fillTaskForSlot(definition)
		if err != nil {
			return SlotState{}, nil, err
		}
		switch resolved.Status {
		case assistantgenerated.SlotValueStatusConflicted:
			task.Reason = fmt.Sprintf(
				"required slot %s has conflicting authorized values",
				definition.SlotID,
			)
		case assistantgenerated.SlotValueStatusStale:
			task.Reason = fmt.Sprintf(
				"required slot %s is stale and requires confirmation",
				definition.SlotID,
			)
		}
		tasks = append(tasks, task)
	}
	return state, tasks, nil
}

func resolveSlotDefinition(
	definition skillpkg.SlotDefinition,
	query string,
	device DeviceContextResponse,
	hints []RecallHint,
	registry *SlotParserRegistry,
) (SlotValue, bool) {
	var staleDevice SlotValue
	for _, source := range definition.SourcePriority {
		switch source {
		case skillpkg.SlotSourceUserQuery:
			value, ok := registry.parse(definition, query, source, "")
			if ok {
				return SlotValue{
					SlotID: definition.SlotID, Status: assistantgenerated.SlotValueStatusConfirmed,
					Value: value, Source: source, Confidence: 1,
				}, true
			}
		case skillpkg.SlotSourceDevice:
			value, ok := deviceSlotValue(definition, device)
			if !ok {
				continue
			}
			if value.Status == assistantgenerated.SlotValueStatusStale {
				staleDevice = value
				continue
			}
			return value, true
		default:
			value, ok := recalledSlotValue(definition, source, hints, registry)
			if ok {
				return value, true
			}
		}
	}
	if staleDevice.SlotID != "" {
		return staleDevice, true
	}
	return SlotValue{}, false
}

func recalledSlotValue(
	definition skillpkg.SlotDefinition,
	source string,
	hints []RecallHint,
	registry *SlotParserRegistry,
) (SlotValue, bool) {
	values := []string{}
	evidenceIDs := []string{}
	for _, hint := range hints {
		if strings.TrimSpace(hint.Source) != source {
			continue
		}
		value := strings.TrimSpace(hint.SlotContributions[definition.SlotID])
		ok := value != ""
		if !ok {
			value, ok = registry.parse(definition, hint.Text, source, hint.Kind)
		}
		if !ok {
			continue
		}
		values = appendUniqueStrings(values, value)
		evidenceIDs = appendUniqueStrings(evidenceIDs, hint.EvidenceIDs...)
	}
	if len(values) == 0 {
		return SlotValue{}, false
	}
	if len(values) > 1 {
		return SlotValue{
			SlotID: definition.SlotID, Status: assistantgenerated.SlotValueStatusConflicted,
			Source: source, Note: "authorized context contains conflicting values",
			Candidates: values, EvidenceIDs: evidenceIDs,
		}, true
	}
	return SlotValue{
		SlotID: definition.SlotID, Status: assistantgenerated.SlotValueStatusInferred,
		Value: values[0], Source: source, Confidence: 0.76, EvidenceIDs: evidenceIDs,
	}, true
}

func deviceSlotValue(
	definition skillpkg.SlotDefinition,
	device DeviceContextResponse,
) (SlotValue, bool) {
	if definition.ValueType != skillpkg.SlotValueTypeLocation {
		return SlotValue{}, false
	}
	status := strings.TrimSpace(device.Status)
	if status != "available" && status != "ok" && status != "stale" {
		return SlotValue{}, false
	}
	city := stringFact(device.Facts, "cityLabel", "city", "locality")
	if city == "" {
		return SlotValue{}, false
	}
	if status == "stale" {
		return SlotValue{
			SlotID: definition.SlotID, Status: assistantgenerated.SlotValueStatusStale,
			Value: city, Source: skillpkg.SlotSourceDevice,
			Note: "device location is stale and must be confirmed",
		}, true
	}
	return SlotValue{
		SlotID: definition.SlotID, Status: assistantgenerated.SlotValueStatusInferred,
		Value: city, Source: skillpkg.SlotSourceDevice, Confidence: 1,
	}, true
}

// ExtractDefinedSlotValue is the only deterministic extraction entry point for
// runtime and compaction. The frozen descriptor, rather than a slot-name switch,
// selects the platform primitive.
func ExtractDefinedSlotValue(
	definition skillpkg.SlotDefinition,
	text string,
) (string, bool) {
	return DefaultSlotParserRegistry().parse(
		definition,
		text,
		skillpkg.SlotSourceUserQuery,
		"",
	)
}

func fillTaskForSlot(definition skillpkg.SlotDefinition) (ContextFillTask, error) {
	prompt := strings.TrimSpace(definition.Clarification.Prompt)
	if prompt == "" {
		return ContextFillTask{}, fmt.Errorf(
			"slot %q has no package-owned clarification prompt",
			definition.SlotID,
		)
	}
	target, err := assistantgenerated.ParseContextTargetSlot(definition.Clarification.TargetSlot)
	if err != nil || target == assistantgenerated.ContextTargetSlotUnknown {
		return ContextFillTask{}, fmt.Errorf("slot %q has invalid clarification target", definition.SlotID)
	}
	retry, err := assistantgenerated.ParseContextRetryPolicy(definition.Clarification.RetryPolicy)
	if err != nil || retry == assistantgenerated.ContextRetryPolicyUnknown {
		return ContextFillTask{}, fmt.Errorf("slot %q has invalid clarification retry policy", definition.SlotID)
	}
	scope, err := assistantgenerated.ParseContextScopeExpansionPolicy(
		definition.Clarification.ScopeExpansionPolicy,
	)
	if err != nil {
		return ContextFillTask{}, fmt.Errorf("slot %q has invalid scope expansion policy", definition.SlotID)
	}
	return ContextFillTask{
		FillType:   assistantgenerated.ContextFillTypeContextFill,
		TargetSlot: target,
		SlotID:     definition.SlotID,
		Reason: fmt.Sprintf(
			"required slot %s is missing and cannot be inferred from authorized context",
			definition.SlotID,
		),
		ScopeExpansionPolicy: scope,
		RetryPolicy:          retry,
		Prompt:               prompt,
		Suggestions:          append([]string(nil), definition.Clarification.Suggestions...),
		Required:             true,
	}, nil
}

func availableGeoContext(input AssemblyInput, slots SlotState) AvailableGeoContext {
	facts := input.Device.Facts
	deviceStatus := strings.TrimSpace(input.Device.Status)
	if facts != nil && (deviceStatus == "available" || deviceStatus == "ok") {
		city := stringFact(facts, "cityLabel", "city", "locality")
		if city != "" {
			return AvailableGeoContext{
				CountryCode:   stringFact(facts, "countryCode"),
				CountryLabel:  stringFact(facts, "countryLabel", "country"),
				RegionCode:    stringFact(facts, "regionCode"),
				RegionLabel:   stringFact(facts, "regionLabel", "region"),
				CityLabel:     city,
				DistrictLabel: stringFact(facts, "districtLabel", "district"),
				Timezone:      stringFact(facts, "timezone"),
				Source:        "device",
				Confidence:    1,
				PrivacyTier:   stringFact(facts, "privacyTier"),
			}
		}
	}
	for _, definition := range input.SlotSchema.Slots {
		if definition.ValueType != skillpkg.SlotValueTypeLocation {
			continue
		}
		value, ok := slots.Slots[definition.SlotID]
		if !ok ||
			value.Status == assistantgenerated.SlotValueStatusMissing ||
			value.Status == assistantgenerated.SlotValueStatusStale ||
			value.Status == assistantgenerated.SlotValueStatusConflicted {
			continue
		}
		city := strings.TrimSpace(fmt.Sprint(value.Value))
		if city != "" {
			return AvailableGeoContext{
				CityLabel:   city,
				Source:      value.Source,
				Confidence:  value.Confidence,
				PrivacyTier: "coarse_city",
			}
		}
	}
	return AvailableGeoContext{}
}

func stringFact(facts map[string]any, keys ...string) string {
	for _, key := range keys {
		value := strings.TrimSpace(fmt.Sprint(facts[key]))
		if value != "" && value != "<nil>" {
			return value
		}
	}
	return ""
}

func groundingEvidence(
	items []assistant.AuthorizedIntersectionEvidence,
	slots SlotState,
) []GroundingEvidence {
	out := make([]GroundingEvidence, 0, len(items))
	for _, item := range items {
		text := strings.TrimSpace(item.PrimaryText)
		if text == "" {
			continue
		}
		slotIDs := make([]string, 0, 2)
		for slotID, value := range slots.Slots {
			for _, evidenceID := range value.EvidenceIDs {
				if evidenceID == item.EvidenceID {
					slotIDs = append(slotIDs, slotID)
					break
				}
			}
		}
		out = append(out, GroundingEvidence{
			EvidenceID:    item.EvidenceID,
			Kind:          "intersection",
			Text:          text,
			SourceRef:     item.SourceRef,
			ObjectTypeRef: item.ObjectTypeRef,
			ObjectID:      item.ObjectID,
			SlotIDs:       slotIDs,
		})
	}
	return out
}

func hasRealtimeNeed(problemClass, text string) bool {
	if strings.TrimSpace(problemClass) == "realtime_info" {
		return true
	}
	for _, marker := range []string{
		"今天", "明天", "实时", "现在", "天气", "交通", "拥堵", "航班",
		"酒店", "价格", "股价", "新闻", "附近", "营业",
	} {
		if strings.Contains(text, marker) {
			return true
		}
	}
	return false
}

func stringSet(values []string) map[string]bool {
	out := make(map[string]bool, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value != "" {
			out[value] = true
		}
	}
	return out
}

func appendUniqueStrings(base []string, values ...string) []string {
	seen := stringSet(base)
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" || seen[value] {
			continue
		}
		seen[value] = true
		base = append(base, value)
	}
	return base
}
