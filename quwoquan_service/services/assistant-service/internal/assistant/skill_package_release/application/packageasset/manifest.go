package skill

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"strings"
	"unicode"
)

const (
	// ActivationReactive 表示技能只在用户提问时被选中。
	ActivationReactive = "reactive"
	// ActivationProactive 表示技能由订阅调度触发，不参与用户提问的技能选择。
	ActivationProactive = "proactive"
	// ActivationHybrid 表示同一个用户可见 Skill 同时接受用户调用与显式订阅触发。
	// 它不是两个 Skill 的兼容别名；响应式与主动式执行仍进入同一条 AssistantRun 管线。
	ActivationHybrid = "hybrid"
)

type Manifest struct {
	SkillID                 string   `json:"skillId"`
	DisplayName             string   `json:"displayName"`
	Description             string   `json:"description,omitempty"`
	DomainID                string   `json:"domainId"`
	ProblemClass            string   `json:"problemClass,omitempty"`
	TagRefs                 []string `json:"tagRefs,omitempty"`
	ExecutionTarget         string   `json:"executionTarget"`
	RoutingHints            []string `json:"routingHints,omitempty"`
	RoutingFallback         bool     `json:"routingFallback,omitempty"`
	CatalogProfileRef       string   `json:"catalogProfileRef"`
	ActivationProfileRef    string   `json:"activationProfileRef"`
	InputProfileRef         string   `json:"inputProfileRef"`
	ContextProfileRef       string   `json:"contextProfileRef"`
	CapabilityProfileRef    string   `json:"capabilityProfileRef"`
	OrchestrationProfileRef string   `json:"orchestrationProfileRef"`
	TriggerProfileRef       string   `json:"triggerProfileRef"`
	MemoryProfileRef        string   `json:"memoryProfileRef"`
	PresentationProfileRef  string   `json:"presentationProfileRef"`
	EvaluationProfileRef    string   `json:"evaluationProfileRef"`
	ReplayAssetRef          string   `json:"replayAssetRef"`
	PromptAssets            []string `json:"promptAssets,omitempty"`
	Examples                []string `json:"examples,omitempty"`

	// 以下字段只由 digest 校验后的 profile assets 派生，不能从 manifest JSON
	// 反序列化。这样运行时调用点可以渐进迁移，而不保留 inline/ref 双真相源。
	Activation        string                `json:"-"`
	ActivationProfile ActivationProfile     `json:"-"`
	IconHint          string                `json:"-"`
	SlotSchema        SlotSchema            `json:"-"`
	ToolPolicy        ToolPolicy            `json:"-"`
	CatalogProfile    CatalogProfile        `json:"-"`
	InputProfile      InputProfile          `json:"-"`
	ContextProfile    ContextProfile        `json:"-"`
	Orchestration     OrchestrationProfile  `json:"-"`
	Trigger           TriggerProfile        `json:"-"`
	Memory            MemoryProfile         `json:"-"`
	Presentation      PresentationProfile   `json:"-"`
	Evaluation        EvaluationProfile     `json:"-"`
	ResolvedAssetRefs map[string]AssetProof `json:"-"`
}

const (
	SlotValueTypeText     = "text"
	SlotValueTypeLocation = "location"
	SlotValueTypeDate     = "date"
	SlotValueTypeInteger  = "integer"
	SlotValueTypeMoney    = "money"

	SlotParserTextAfterAlias      = "primitive.text_after_alias"
	SlotParserLocationAfterAlias  = "primitive.location_after_alias"
	SlotParserLocationBeforeAlias = "primitive.location_before_alias"
	SlotParserTemporalExpression  = "primitive.temporal_expression"
	SlotParserIntegerBeforeAlias  = "primitive.integer_before_alias"
	SlotParserMoneyAfterAlias     = "primitive.money_after_alias"

	SlotSourceUserQuery      = "user_query"
	SlotSourceDevice         = "device"
	SlotSourceIntersection   = "intersection"
	SlotSourceSessionUser    = "session_user"
	SlotSourceSessionSummary = "session_summary"
	SlotSourceLongTermMemory = "longterm_memory"
	SlotSourcePageObject     = "page_object"

	SlotClarificationClarify = "clarify"
	SlotClarificationOmit    = "omit"
)

// SlotClarification is immutable product language and recovery policy from the
// selected Skill package. Runtime never derives prompts from slot ids.
type SlotClarification struct {
	Policy               string   `json:"policy"`
	TargetSlot           string   `json:"targetSlot,omitempty"`
	Prompt               string   `json:"prompt,omitempty"`
	Suggestions          []string `json:"suggestions,omitempty"`
	RetryPolicy          string   `json:"retryPolicy,omitempty"`
	ScopeExpansionPolicy string   `json:"scopeExpansionPolicy,omitempty"`
}

// SlotDefinition declares one structured input without giving AgentLoop any
// vertical-domain vocabulary. Aliases are semantic extraction hints owned by
// the immutable package, not alternate wire keys.
type SlotDefinition struct {
	SlotID         string            `json:"slotId"`
	Required       bool              `json:"required,omitempty"`
	ValueType      string            `json:"valueType"`
	ParserRefs     []string          `json:"parserRefs"`
	Aliases        []string          `json:"aliases,omitempty"`
	SourcePriority []string          `json:"sourcePriority"`
	Clarification  SlotClarification `json:"clarification"`
}

type SlotSchema struct {
	Slots       []SlotDefinition `json:"slots,omitempty"`
	CarryOver   bool             `json:"carryOver,omitempty"`
	StateID     string           `json:"stateId,omitempty"`
	NextStateID string           `json:"nextStateId,omitempty"`
}

func (schema SlotSchema) HasRequiredSlots() bool {
	for _, slot := range schema.Slots {
		if slot.Required {
			return true
		}
	}
	return false
}

// NormalizeSlotSchema validates the canonical asset shape. It intentionally
// has no legacy requiredSlots/optionalSlots path: every runtime reads the same
// descriptor list frozen into the release digest.
func NormalizeSlotSchema(schema SlotSchema) (SlotSchema, error) {
	if len(schema.Slots) > 16 {
		return SlotSchema{}, fmt.Errorf("slot schema declares too many slots")
	}
	schema.StateID = strings.TrimSpace(schema.StateID)
	schema.NextStateID = strings.TrimSpace(schema.NextStateID)
	seenSlots := map[string]struct{}{}
	for index := range schema.Slots {
		slot := &schema.Slots[index]
		slot.SlotID = strings.TrimSpace(slot.SlotID)
		slot.ValueType = strings.TrimSpace(slot.ValueType)
		if !validSlotID(slot.SlotID) {
			return SlotSchema{}, fmt.Errorf("invalid slot id %q", slot.SlotID)
		}
		if _, duplicate := seenSlots[slot.SlotID]; duplicate {
			return SlotSchema{}, fmt.Errorf("duplicate slot %q", slot.SlotID)
		}
		seenSlots[slot.SlotID] = struct{}{}
		if !allowedSlotValueType(slot.ValueType) {
			return SlotSchema{}, fmt.Errorf("slot %q has invalid value type %q", slot.SlotID, slot.ValueType)
		}
		parserRefs, err := canonicalSlotStrings(slot.ParserRefs, 4, 64)
		if err != nil || len(parserRefs) == 0 {
			return SlotSchema{}, fmt.Errorf("slot %q parser refs are invalid", slot.SlotID)
		}
		slot.ParserRefs = parserRefs
		for _, parserRef := range slot.ParserRefs {
			if !allowedSlotParser(parserRef) {
				return SlotSchema{}, fmt.Errorf("slot %q has invalid parser ref %q", slot.SlotID, parserRef)
			}
			if !slotParserAcceptsType(parserRef, slot.ValueType) {
				return SlotSchema{}, fmt.Errorf(
					"slot %q parser %q cannot produce %q",
					slot.SlotID,
					parserRef,
					slot.ValueType,
				)
			}
		}
		aliases, err := canonicalSlotStrings(slot.Aliases, 16, 64)
		if err != nil {
			return SlotSchema{}, fmt.Errorf("slot %q aliases: %w", slot.SlotID, err)
		}
		slot.Aliases = aliases
		if parsersRequireAliases(slot.ParserRefs) && len(slot.Aliases) == 0 {
			return SlotSchema{}, fmt.Errorf("slot %q parsers require aliases", slot.SlotID)
		}
		sources, err := canonicalSlotSources(slot.SourcePriority)
		if err != nil {
			return SlotSchema{}, fmt.Errorf("slot %q source priority: %w", slot.SlotID, err)
		}
		slot.SourcePriority = sources
		clarification, err := normalizeSlotClarification(*slot)
		if err != nil {
			return SlotSchema{}, err
		}
		slot.Clarification = clarification
	}
	return schema, nil
}

func validSlotID(value string) bool {
	if value == "" || len([]rune(value)) > 64 {
		return false
	}
	for _, current := range value {
		if unicode.IsLower(current) || unicode.IsDigit(current) || current == '_' {
			continue
		}
		return false
	}
	return true
}

func allowedSlotValueType(value string) bool {
	switch value {
	case SlotValueTypeText, SlotValueTypeLocation, SlotValueTypeDate,
		SlotValueTypeInteger, SlotValueTypeMoney:
		return true
	default:
		return false
	}
}

func allowedSlotParser(value string) bool {
	switch value {
	case SlotParserTextAfterAlias, SlotParserLocationAfterAlias,
		SlotParserLocationBeforeAlias, SlotParserTemporalExpression,
		SlotParserIntegerBeforeAlias, SlotParserMoneyAfterAlias:
		return true
	default:
		return false
	}
}

func parsersRequireAliases(values []string) bool {
	for _, value := range values {
		if value != SlotParserTemporalExpression {
			return true
		}
	}
	return false
}

func slotParserAcceptsType(parserRef, valueType string) bool {
	switch parserRef {
	case SlotParserTextAfterAlias:
		return valueType == SlotValueTypeText
	case SlotParserLocationAfterAlias, SlotParserLocationBeforeAlias:
		return valueType == SlotValueTypeLocation
	case SlotParserTemporalExpression:
		return valueType == SlotValueTypeDate
	case SlotParserIntegerBeforeAlias:
		return valueType == SlotValueTypeInteger
	case SlotParserMoneyAfterAlias:
		return valueType == SlotValueTypeMoney
	default:
		return false
	}
}

func canonicalSlotSources(values []string) ([]string, error) {
	if len(values) == 0 {
		return nil, fmt.Errorf("must not be empty")
	}
	allowed := map[string]struct{}{
		SlotSourceUserQuery: {}, SlotSourceDevice: {}, SlotSourceIntersection: {},
		SlotSourceSessionUser: {}, SlotSourceSessionSummary: {},
		SlotSourceLongTermMemory: {}, SlotSourcePageObject: {},
	}
	out, err := canonicalSlotStrings(values, len(allowed), 32)
	if err != nil {
		return nil, err
	}
	for _, value := range out {
		if _, ok := allowed[value]; !ok {
			return nil, fmt.Errorf("unsupported source %q", value)
		}
	}
	return out, nil
}

func canonicalSlotStrings(values []string, maxItems, maxRunes int) ([]string, error) {
	if len(values) > maxItems {
		return nil, fmt.Errorf("declares too many values")
	}
	seen := map[string]struct{}{}
	out := make([]string, 0, len(values))
	for _, raw := range values {
		value := strings.TrimSpace(raw)
		if value == "" || len([]rune(value)) > maxRunes {
			return nil, fmt.Errorf("contains invalid value %q", raw)
		}
		if _, duplicate := seen[value]; duplicate {
			return nil, fmt.Errorf("contains duplicate value %q", value)
		}
		seen[value] = struct{}{}
		out = append(out, value)
	}
	return out, nil
}

func normalizeSlotClarification(slot SlotDefinition) (SlotClarification, error) {
	value := slot.Clarification
	value.Policy = strings.TrimSpace(value.Policy)
	value.TargetSlot = strings.TrimSpace(value.TargetSlot)
	value.Prompt = strings.TrimSpace(value.Prompt)
	value.RetryPolicy = strings.TrimSpace(value.RetryPolicy)
	value.ScopeExpansionPolicy = strings.TrimSpace(value.ScopeExpansionPolicy)
	suggestions, err := canonicalSlotStrings(value.Suggestions, 8, 64)
	if err != nil {
		return SlotClarification{}, fmt.Errorf("slot %q clarification suggestions: %w", slot.SlotID, err)
	}
	value.Suggestions = suggestions
	if slot.Required {
		if value.Policy != SlotClarificationClarify || value.TargetSlot == "" ||
			value.Prompt == "" || value.RetryPolicy == "" {
			return SlotClarification{}, fmt.Errorf("required slot %q needs complete clarification semantics", slot.SlotID)
		}
		if !allowedClarificationTarget(value.TargetSlot) || value.RetryPolicy != "single_retry" ||
			!allowedScopeExpansionPolicy(value.ScopeExpansionPolicy) {
			return SlotClarification{}, fmt.Errorf("required slot %q has invalid clarification policy values", slot.SlotID)
		}
		return value, nil
	}
	if value.Policy != SlotClarificationOmit {
		return SlotClarification{}, fmt.Errorf("optional slot %q must use omit clarification policy", slot.SlotID)
	}
	if value.TargetSlot != "" || value.Prompt != "" || value.RetryPolicy != "" ||
		value.ScopeExpansionPolicy != "" || len(value.Suggestions) > 0 {
		return SlotClarification{}, fmt.Errorf("optional slot %q cannot declare an unreachable clarification prompt", slot.SlotID)
	}
	return value, nil
}

func allowedClarificationTarget(value string) bool {
	switch value {
	case "longterm_memory", "realtime_evidence", "answer_sufficiency", "gps_or_city_location":
		return true
	default:
		return false
	}
}

func allowedScopeExpansionPolicy(value string) bool {
	switch value {
	case "", "expand_time_window", "expand_scope_and_requery", "expand_provider_and_time_window":
		return true
	default:
		return false
	}
}

type ToolPolicy struct {
	AllowedTools              []string `json:"allowedTools,omitempty"`
	PreferredTools            []string `json:"preferredTools,omitempty"`
	MaxToolCalls              int      `json:"maxToolCalls,omitempty"`
	AllowDeviceContext        bool     `json:"allowDeviceContext,omitempty"`
	AllowDeviceActionProposal bool     `json:"allowDeviceActionProposal,omitempty"`
}

// ResolvedReleaseDigest binds a static Skill manifest to the exact immutable
// profile assets exposed to the runtime. Replay assets use this digest so a
// prompt/profile/catalog change cannot silently reuse an evaluation corpus
// built for another release.
func (m Manifest) ResolvedProfileDigest() (string, error) {
	return m.resolvedDigest(false)
}

func (m Manifest) ResolvedReleaseDigest() (string, error) {
	return m.resolvedDigest(true)
}

func (m Manifest) resolvedDigest(includeReplay bool) (string, error) {
	type asset struct {
		Kind        string `json:"kind"`
		ProfileID   string `json:"profileId"`
		AssetDigest string `json:"assetDigest"`
	}
	kinds := []string{
		"catalog",
		"activation",
		"input",
		"context",
		"capability",
		"orchestration",
		"trigger",
		"memory",
		"presentation",
		"evaluation",
	}
	if includeReplay {
		kinds = append(kinds, "replay")
	}
	assets := make([]asset, 0, len(kinds))
	for _, kind := range kinds {
		proof, found := m.ResolvedAssetRefs[kind]
		if !found ||
			strings.TrimSpace(proof.ProfileID) == "" ||
			!strings.HasPrefix(strings.TrimSpace(proof.AssetDigest), "sha256:") {
			return "", fmt.Errorf("skill %q has no resolved %s asset", m.SkillID, kind)
		}
		assets = append(assets, asset{
			Kind:        kind,
			ProfileID:   strings.TrimSpace(proof.ProfileID),
			AssetDigest: strings.TrimSpace(proof.AssetDigest),
		})
	}
	descriptor := struct {
		SkillID                 string   `json:"skillId"`
		DisplayName             string   `json:"displayName"`
		Description             string   `json:"description,omitempty"`
		DomainID                string   `json:"domainId"`
		ProblemClass            string   `json:"problemClass,omitempty"`
		TagRefs                 []string `json:"tagRefs,omitempty"`
		ExecutionTarget         string   `json:"executionTarget"`
		RoutingHints            []string `json:"routingHints,omitempty"`
		RoutingFallback         bool     `json:"routingFallback,omitempty"`
		CatalogProfileRef       string   `json:"catalogProfileRef"`
		ActivationProfileRef    string   `json:"activationProfileRef"`
		InputProfileRef         string   `json:"inputProfileRef"`
		ContextProfileRef       string   `json:"contextProfileRef"`
		CapabilityProfileRef    string   `json:"capabilityProfileRef"`
		OrchestrationProfileRef string   `json:"orchestrationProfileRef"`
		TriggerProfileRef       string   `json:"triggerProfileRef"`
		MemoryProfileRef        string   `json:"memoryProfileRef"`
		PresentationProfileRef  string   `json:"presentationProfileRef"`
		EvaluationProfileRef    string   `json:"evaluationProfileRef"`
		ReplayAssetRef          string   `json:"replayAssetRef,omitempty"`
		PromptAssets            []string `json:"promptAssets,omitempty"`
		Examples                []string `json:"examples,omitempty"`
		Assets                  []asset  `json:"assets"`
	}{
		SkillID:                 strings.TrimSpace(m.SkillID),
		DisplayName:             strings.TrimSpace(m.DisplayName),
		Description:             strings.TrimSpace(m.Description),
		DomainID:                strings.TrimSpace(m.DomainID),
		ProblemClass:            strings.TrimSpace(m.ProblemClass),
		TagRefs:                 m.TagRefs,
		ExecutionTarget:         strings.TrimSpace(m.ExecutionTarget),
		RoutingHints:            m.RoutingHints,
		RoutingFallback:         m.RoutingFallback,
		CatalogProfileRef:       strings.TrimSpace(m.CatalogProfileRef),
		ActivationProfileRef:    strings.TrimSpace(m.ActivationProfileRef),
		InputProfileRef:         strings.TrimSpace(m.InputProfileRef),
		ContextProfileRef:       strings.TrimSpace(m.ContextProfileRef),
		CapabilityProfileRef:    strings.TrimSpace(m.CapabilityProfileRef),
		OrchestrationProfileRef: strings.TrimSpace(m.OrchestrationProfileRef),
		TriggerProfileRef:       strings.TrimSpace(m.TriggerProfileRef),
		MemoryProfileRef:        strings.TrimSpace(m.MemoryProfileRef),
		PresentationProfileRef:  strings.TrimSpace(m.PresentationProfileRef),
		EvaluationProfileRef:    strings.TrimSpace(m.EvaluationProfileRef),
		PromptAssets:            m.PromptAssets,
		Examples:                m.Examples,
		Assets:                  assets,
	}
	if includeReplay {
		descriptor.ReplayAssetRef = strings.TrimSpace(m.ReplayAssetRef)
	}
	encoded, err := json.Marshal(descriptor)
	if err != nil {
		return "", fmt.Errorf("encode skill release descriptor: %w", err)
	}
	digest := sha256.Sum256(encoded)
	return "sha256:" + hex.EncodeToString(digest[:]), nil
}

func (m Manifest) IsProactive() bool {
	return m.Activation == ActivationProactive || m.Activation == ActivationHybrid
}

func (m Manifest) IsReactive() bool {
	return m.Activation == ActivationReactive || m.Activation == ActivationHybrid
}
