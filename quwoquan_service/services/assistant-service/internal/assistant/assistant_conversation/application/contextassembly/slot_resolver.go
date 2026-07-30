package contextassembly

import (
	"fmt"
	"regexp"
	"strconv"
	"strings"

	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_conversation"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
)

var (
	datePattern          = regexp.MustCompile(`(?i)(今天|明天|后天|本周末|这周末|周末|本周|下周|\d{4}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}月\d{1,2}(?:日|号)?)`)
	originPattern        = regexp.MustCompile(`(?i)(?:从|出发地(?:是|为)?)([\p{Han}A-Za-z·]{2,16}?)(?:出发|去|到|前往)`)
	destinationPattern   = regexp.MustCompile(`(?i)(?:去|到|前往|目的地(?:是|为)?)([\p{Han}A-Za-z·]{2,16})`)
	locationTopicPattern = regexp.MustCompile(`(?i)([\p{Han}A-Za-z·]{2,12}?)(?:今天|明天|后天|本周末|这周末|周末|本周|下周)?(?:的)?(?:天气|气温|降雨|美食|餐厅|景点|酒店)`)
	partyPattern         = regexp.MustCompile(`(?i)(\d{1,2}|一|二|两|三|四|五|六|七|八|九|十)(?:个)?人`)
	budgetPattern        = regexp.MustCompile(`(?i)(?:预算(?:是|为|大约|约)?|控制在|不超过)\s*([0-9]+(?:\.[0-9]+)?\s*(?:元|块|k|K|千|万)?)`)
)

func resolveSlots(
	input AssemblyInput,
	domainID string,
	hints []RecallHint,
) (SlotState, []ContextFillTask) {
	state := SlotState{
		DomainID: domainID,
		Slots:    map[string]SlotValue{},
	}
	allSlots := append([]string(nil), input.SlotSchema.RequiredSlots...)
	allSlots = appendUniqueStrings(allSlots, input.SlotSchema.OptionalSlots...)
	required := stringSet(input.SlotSchema.RequiredSlots)
	for _, slotID := range allSlots {
		value, ok := inferSlotValue(slotID, input.Turn.Input.Text)
		if ok {
			state.Slots[slotID] = SlotValue{
				SlotID:     slotID,
				Status:     assistantgenerated.SlotValueStatusConfirmed,
				Value:      value,
				Source:     "user_query",
				Confidence: 1,
			}
			continue
		}
		if deviceValue, ok := deviceSlotValue(slotID, input.Device, false); ok {
			state.Slots[slotID] = deviceValue
			continue
		}
		if recalled, ok := inferRecalledSlotValue(slotID, hints); ok {
			state.Slots[slotID] = recalled
			if recalled.Status == assistantgenerated.SlotValueStatusConflicted &&
				required[slotID] {
				state.MissingSlots = append(state.MissingSlots, slotID)
			}
			continue
		}
		if staleDeviceValue, ok := deviceSlotValue(slotID, input.Device, true); ok {
			state.Slots[slotID] = staleDeviceValue
			if required[slotID] {
				state.MissingSlots = append(state.MissingSlots, slotID)
			}
			continue
		}
		state.Slots[slotID] = SlotValue{
			SlotID: slotID,
			Status: assistantgenerated.SlotValueStatusMissing,
		}
		if required[slotID] {
			state.MissingSlots = append(state.MissingSlots, slotID)
		}
	}
	tasks := make([]ContextFillTask, 0, len(state.MissingSlots))
	for _, slotID := range state.MissingSlots {
		task := fillTaskForSlot(slotID)
		switch state.Slots[slotID].Status {
		case assistantgenerated.SlotValueStatusConflicted:
			task.Reason = fmt.Sprintf(
				"required slot %s has conflicting authorized values",
				slotID,
			)
		case assistantgenerated.SlotValueStatusStale:
			task.Reason = fmt.Sprintf(
				"required slot %s is stale and requires confirmation",
				slotID,
			)
		}
		tasks = append(tasks, task)
	}
	return state, tasks
}

func inferRecalledSlotValue(
	slotID string,
	hints []RecallHint,
) (SlotValue, bool) {
	values := []string{}
	sources := []string{}
	evidenceIDs := []string{}
	for _, hint := range hints {
		if hint.Source != "intersection" &&
			hint.Source != "conversation_user" &&
			hint.Source != "longterm_memory" &&
			hint.Source != "conversation_summary" {
			continue
		}
		value := strings.TrimSpace(hint.SlotContributions[slotID])
		ok := value != ""
		if !ok {
			value, ok = inferSlotValue(slotID, hint.Text)
		}
		if !ok &&
			hint.Source == "longterm_memory" &&
			hint.Kind == "frequent_locations" {
			switch slotID {
			case "location", "city", "geo_location":
				candidate := strings.TrimSpace(hint.Text)
				if validTopicLocation(candidate) && len([]rune(candidate)) <= 32 {
					value, ok = candidate, true
				}
			}
		}
		if !ok {
			continue
		}
		values = appendUniqueStrings(values, value)
		sources = appendUniqueStrings(sources, hint.Source)
		evidenceIDs = appendUniqueStrings(evidenceIDs, hint.EvidenceIDs...)
	}
	if len(values) == 0 {
		return SlotValue{}, false
	}
	if len(values) > 1 {
		return SlotValue{
			SlotID:      slotID,
			Status:      assistantgenerated.SlotValueStatusConflicted,
			Source:      strings.Join(sources, "+"),
			Note:        "authorized context contains conflicting values",
			Candidates:  values,
			EvidenceIDs: evidenceIDs,
		}, true
	}
	return SlotValue{
		SlotID:      slotID,
		Status:      assistantgenerated.SlotValueStatusInferred,
		Value:       values[0],
		Source:      strings.Join(sources, "+"),
		Confidence:  0.76,
		EvidenceIDs: evidenceIDs,
	}, true
}

func deviceSlotValue(
	slotID string,
	device DeviceContextResponse,
	stale bool,
) (SlotValue, bool) {
	switch slotID {
	case "location", "city", "geo_location":
	default:
		return SlotValue{}, false
	}
	status := strings.TrimSpace(device.Status)
	if stale != (status == "stale") {
		return SlotValue{}, false
	}
	if !stale && status != "available" && status != "ok" {
		return SlotValue{}, false
	}
	city := stringFact(device.Facts, "cityLabel", "city", "locality")
	if city == "" {
		return SlotValue{}, false
	}
	if stale {
		return SlotValue{
			SlotID: slotID,
			Status: assistantgenerated.SlotValueStatusStale,
			Value:  city,
			Source: "device",
			Note:   "device location is stale and must be confirmed",
		}, true
	}
	return SlotValue{
		SlotID:     slotID,
		Status:     assistantgenerated.SlotValueStatusInferred,
		Value:      city,
		Source:     "device",
		Confidence: 1,
	}, true
}

func inferSlotValue(slotID, text string) (string, bool) {
	text = strings.TrimSpace(text)
	if text == "" {
		return "", false
	}
	switch slotID {
	case "origin", "departure", "departure_location":
		return firstMatch(originPattern, text)
	case "destination":
		if value, ok := firstMatch(destinationPattern, text); ok {
			return trimLocationCandidate(value), true
		}
		return topicLocation(text)
	case "location", "city", "geo_location":
		if value, ok := topicLocation(text); ok {
			return value, true
		}
		if value, ok := firstMatch(destinationPattern, text); ok {
			return trimLocationCandidate(value), true
		}
	case "date", "travel_date", "departure_date":
		return firstMatch(datePattern, text)
	case "party_size", "traveler_count":
		if value, ok := firstMatch(partyPattern, text); ok {
			return normalizePartySize(value), true
		}
	case "budget":
		return firstMatch(budgetPattern, text)
	}
	return "", false
}

// ExtractSlotValue applies the same deterministic slot rules used by runtime
// assembly, so conversation compaction cannot create a second extraction path.
func ExtractSlotValue(slotID, text string) (string, bool) {
	return inferSlotValue(strings.TrimSpace(slotID), text)
}

func firstMatch(pattern *regexp.Regexp, text string) (string, bool) {
	matches := pattern.FindStringSubmatch(text)
	if len(matches) < 2 {
		return "", false
	}
	value := strings.TrimSpace(matches[1])
	return value, value != ""
}

func topicLocation(text string) (string, bool) {
	value, ok := firstMatch(locationTopicPattern, text)
	if !ok {
		return "", false
	}
	value = trimLocationCandidate(value)
	return value, validTopicLocation(value)
}

func trimLocationCandidate(value string) string {
	value = strings.TrimSpace(value)
	for _, suffix := range []string{"玩几天", "玩", "旅行", "旅游", "出差", "度假", "看看", "的"} {
		value = strings.TrimSuffix(value, suffix)
	}
	return strings.TrimSpace(value)
}

func validTopicLocation(value string) bool {
	value = strings.TrimSpace(value)
	if value == "" {
		return false
	}
	for _, generic := range []string{
		"查一下", "看一下", "帮我", "请问", "想知道", "告诉我",
		"今天", "明天", "后天", "周末", "本周", "下周",
	} {
		if strings.Contains(value, generic) {
			return false
		}
	}
	return true
}

func normalizePartySize(raw string) string {
	numbers := map[string]int{
		"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5,
		"六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
	}
	if value, ok := numbers[raw]; ok {
		return strconv.Itoa(value)
	}
	return raw
}

func fillTaskForSlot(slotID string) ContextFillTask {
	task := ContextFillTask{
		FillType:             assistantgenerated.ContextFillTypeContextFill,
		TargetSlot:           assistantgenerated.ContextTargetSlotAnswerSufficiency,
		SlotID:               slotID,
		Reason:               fmt.Sprintf("required slot %s is missing and cannot be inferred from authorized context", slotID),
		ScopeExpansionPolicy: assistantgenerated.ContextScopeExpansionPolicyNone,
		RetryPolicy:          assistantgenerated.ContextRetryPolicySingleRetry,
		Required:             true,
	}
	switch slotID {
	case "origin", "departure", "departure_location":
		task.TargetSlot = assistantgenerated.ContextTargetSlotGpsOrCityLocation
		task.Prompt = "你从哪座城市出发？"
	case "destination", "location", "city", "geo_location":
		task.TargetSlot = assistantgenerated.ContextTargetSlotGpsOrCityLocation
		task.Prompt = "你想查询或前往哪座城市？"
	case "date", "travel_date", "departure_date":
		task.TargetSlot = assistantgenerated.ContextTargetSlotRealtimeEvidence
		task.Prompt = "你计划哪天出发或查询哪一天？"
		task.Suggestions = []string{"今天", "明天", "本周末", "下周"}
	case "party_size", "traveler_count":
		task.Prompt = "这次一共有几个人？"
		task.Suggestions = []string{"1人", "2人", "3人", "4人以上"}
	case "budget":
		task.Prompt = "这次的总预算大约是多少？"
	default:
		task.Prompt = "请补充完成这件事所需的关键信息。"
	}
	return task
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
	for _, slotID := range []string{"location", "city", "destination"} {
		value, ok := slots.Slots[slotID]
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
