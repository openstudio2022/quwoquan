package contextassembly

import (
	"context"
	"fmt"
	"strings"

	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	channelpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/channel"
	skillcontext "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/skillcontext"
	assistant "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/model"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
)

type ClientContext struct {
	SurfaceID string         `json:"surfaceId,omitempty"`
	Locale    string         `json:"locale,omitempty"`
	Region    string         `json:"region,omitempty"`
	Values    map[string]any `json:"values,omitempty"`
}

type DeviceContextResponse struct {
	Status           string         `json:"status"`
	DeviceContextRef string         `json:"deviceContextRef,omitempty"`
	Facts            map[string]any `json:"facts,omitempty"`
	Reason           string         `json:"reason,omitempty"`
}

type AvailableGeoContext struct {
	CountryCode   string  `json:"countryCode,omitempty"`
	CountryLabel  string  `json:"countryLabel,omitempty"`
	RegionCode    string  `json:"regionCode,omitempty"`
	RegionLabel   string  `json:"regionLabel,omitempty"`
	CityLabel     string  `json:"cityLabel,omitempty"`
	DistrictLabel string  `json:"districtLabel,omitempty"`
	Lat           float64 `json:"lat,omitempty"`
	Lng           float64 `json:"lng,omitempty"`
	Timezone      string  `json:"timezone,omitempty"`
	Source        string  `json:"source,omitempty"`
	Confidence    float64 `json:"confidence,omitempty"`
	CapturedAt    string  `json:"capturedAt,omitempty"`
	PrivacyTier   string  `json:"privacyTier,omitempty"`
}

type SlotValue struct {
	SlotID      string                             `json:"slotId"`
	Status      assistantgenerated.SlotValueStatus `json:"status"`
	Value       any                                `json:"value,omitempty"`
	Source      string                             `json:"source,omitempty"`
	Confidence  float64                            `json:"confidence,omitempty"`
	Note        string                             `json:"note,omitempty"`
	Candidates  []string                           `json:"candidates,omitempty"`
	EvidenceIDs []string                           `json:"evidenceIds,omitempty"`
}

type SlotState struct {
	DomainID     string               `json:"domainId"`
	Slots        map[string]SlotValue `json:"slots"`
	MissingSlots []string             `json:"missingSlots"`
}

type ContextFillTask struct {
	FillType             assistantgenerated.ContextFillType             `json:"fillType"`
	TargetSlot           assistantgenerated.ContextTargetSlot           `json:"targetSlot"`
	SlotID               string                                         `json:"slotId"`
	Reason               string                                         `json:"reason"`
	GeneratedConditions  []string                                       `json:"generatedQueryConditions,omitempty"`
	ScopeExpansionPolicy assistantgenerated.ContextScopeExpansionPolicy `json:"scopeExpansionPolicy"`
	RetryPolicy          assistantgenerated.ContextRetryPolicy          `json:"retryPolicy"`
	Prompt               string                                         `json:"prompt"`
	Suggestions          []string                                       `json:"suggestions,omitempty"`
	Required             bool                                           `json:"required"`
}

type GroundingEvidence struct {
	EvidenceID    string   `json:"evidenceId"`
	Kind          string   `json:"kind"`
	Text          string   `json:"text"`
	SourceRef     string   `json:"sourceRef,omitempty"`
	ObjectTypeRef string   `json:"objectTypeRef,omitempty"`
	ObjectID      string   `json:"objectId,omitempty"`
	SlotIDs       []string `json:"slotIds,omitempty"`
}

type AssemblyResult struct {
	ContextEnvelope      map[string]any         `json:"contextEnvelope"`
	SkillContextSnapshot *skillcontext.Snapshot `json:"skillContextSnapshot,omitempty"`
	FillTasks            []ContextFillTask      `json:"fillTasks"`
	CanEnterDomain       bool                   `json:"canEnterDomain"`
	SummaryText          string                 `json:"summaryText"`
	HasRealtimeNeed      bool                   `json:"hasRealtimeNeed"`
	HasLongtermNeed      bool                   `json:"hasLongtermNeed"`
	AvailableGeoContext  AvailableGeoContext    `json:"availableGeoContext"`
	DomainID             string                 `json:"domainId"`
	RecallHints          []RecallHint           `json:"recallHints"`
	SlotState            SlotState              `json:"slotState"`
	GroundingEvidence    []GroundingEvidence    `json:"groundingEvidence"`
	ChannelID            string                 `json:"channelId"`
	MemoryScope          string                 `json:"memoryScope"`
	AnswerBoundaryRule   string                 `json:"answerBoundaryRule"`
	MaxAnswerRunes       int                    `json:"maxAnswerRunes"`
}

type AssemblyInput struct {
	Turn         assistant.AssistantTurn
	Client       ClientContext
	Device       DeviceContextResponse
	DomainID     string
	ProblemClass string
	SlotSchema   skillpkg.SlotSchema
	Channel      channelpkg.AssistantChannel
}

type Assembler interface {
	Assemble(context.Context, AssemblyInput) (AssemblyResult, error)
}

type ContextOrchestrator struct {
	Recall      RecallCoordinator
	Router      DomainRouter
	SlotParsers *SlotParserRegistry
}

func NewContextOrchestrator() ContextOrchestrator {
	return ContextOrchestrator{
		Recall:      NewRecallCoordinator(),
		Router:      DefaultDomainRouter{},
		SlotParsers: DefaultSlotParserRegistry(),
	}
}

func (o ContextOrchestrator) Assemble(
	ctx context.Context,
	input AssemblyInput,
) (AssemblyResult, error) {
	if err := ctx.Err(); err != nil {
		return AssemblyResult{}, err
	}
	turn := input.Turn
	router := o.Router
	if router == nil || router.IsZero() {
		router = DefaultDomainRouter{}
	}
	recall := o.Recall
	if recall.IsZero() {
		recall = NewRecallCoordinator()
	}
	domainID := strings.TrimSpace(input.DomainID)
	if domainID == "" {
		domainID = router.Route(turn, input.Client)
	}
	hints, err := recall.Recall(ctx, RecallRequest{Turn: turn, DomainID: domainID})
	if err != nil {
		return AssemblyResult{}, err
	}
	channel := input.Channel
	if channel == nil {
		channel = channelpkg.Resolve(turn.TurnType, turn.Trigger)
	}
	slots, fillTasks, err := resolveSlots(
		input,
		domainID,
		hints,
		o.SlotParsers,
	)
	if err != nil {
		return AssemblyResult{}, err
	}
	geo := availableGeoContext(input, slots)
	grounding := groundingEvidence(turn.IntersectionEvidence, slots)
	realtimeNeed := hasRealtimeNeed(input.ProblemClass, turn.Input.Text)
	longtermNeed := len(slots.MissingSlots) > 0 &&
		input.SlotSchema.CarryOver &&
		channel.ContextPersistence() == channelpkg.ContextPersistencePrivateLongTerm
	result := AssemblyResult{
		ContextEnvelope: map[string]any{
			"surfaceId":         strings.TrimSpace(input.Client.SurfaceID),
			"pageContext":       turn.PageContext,
			"deviceContext":     input.Device,
			"triggerEnvelope":   turn.Trigger.Envelope,
			"recallHints":       hints,
			"slotState":         slots,
			"groundingEvidence": grounding,
		},
		FillTasks:           fillTasks,
		CanEnterDomain:      len(fillTasks) == 0,
		HasRealtimeNeed:     realtimeNeed,
		HasLongtermNeed:     longtermNeed,
		AvailableGeoContext: geo,
		DomainID:            domainID,
		RecallHints:         hints,
		SlotState:           slots,
		GroundingEvidence:   grounding,
		ChannelID:           string(channel.ID()),
		MemoryScope:         string(channel.ContextPersistence()),
		AnswerBoundaryRule:  channel.AnswerBoundary().PromptRule,
		MaxAnswerRunes:      channel.AnswerBoundary().MaxAnswerRunes,
	}
	result.SummaryText = assemblySummary(result)
	return result, nil
}

func assemblySummary(result AssemblyResult) string {
	parts := []string{fmt.Sprintf("领域=%s", result.DomainID)}
	if len(result.RecallHints) > 0 {
		parts = append(parts, fmt.Sprintf("召回=%d", len(result.RecallHints)))
	}
	if len(result.GroundingEvidence) > 0 {
		parts = append(parts, fmt.Sprintf("交集证据=%d", len(result.GroundingEvidence)))
	}
	if len(result.FillTasks) > 0 {
		parts = append(parts, "待补槽位="+strings.Join(result.SlotState.MissingSlots, ","))
	}
	return strings.Join(parts, "；")
}
