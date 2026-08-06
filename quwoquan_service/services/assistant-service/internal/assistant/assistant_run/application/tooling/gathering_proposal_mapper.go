package tooling

import (
	"fmt"
	"strings"
	"time"

	gatheringplanclient "quwoquan_service/generated/serviceclients/circlegatheringplan"
	runtimeauth "quwoquan_service/runtime/auth"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/presentation"
)

type CanonicalObjectRef struct {
	ObjectTypeRef string `json:"objectTypeRef"`
	ObjectID      string `json:"objectId"`
}

type GatheringSourceRef struct {
	ObjectRef    CanonicalObjectRef `json:"objectRef"`
	RouteID      string             `json:"routeId"`
	SourceDigest string             `json:"sourceDigest"`
}

type VerifiedGatheringHostAuthority struct {
	AccountID            string    `json:"accountId"`
	PersonaID            string    `json:"personaId"`
	GatheringID          string    `json:"gatheringId,omitempty"`
	HostSubjectKind      string    `json:"hostSubjectKind"`
	HostSubjectID        string    `json:"hostSubjectId"`
	AuthorityEvidenceRef string    `json:"authorityEvidenceRef"`
	AuthorityVersion     int64     `json:"authorityVersion"`
	AuthorityExpiresAt   time.Time `json:"authorityExpiresAt"`
}

type GatheringHostBinding struct {
	HostSubjectKind      string `json:"hostSubjectKind"`
	HostSubjectID        string `json:"hostSubjectId"`
	AuthorityEvidenceRef string `json:"authorityEvidenceRef"`
	AuthorityVersion     int64  `json:"authorityVersion"`
	AuthorityExpiresAt   string `json:"authorityExpiresAt,omitempty"`
}

type GatheringApplicationQuestionOption struct {
	OptionID string `json:"optionId"`
	Label    string `json:"label"`
}

type GatheringApplicationQuestion struct {
	QuestionID string                               `json:"questionId"`
	Prompt     string                               `json:"prompt"`
	Kind       string                               `json:"kind"`
	Options    []GatheringApplicationQuestionOption `json:"options"`
	Required   bool                                 `json:"required"`
}

type GatheringPurpose struct {
	Title            string               `json:"title,omitempty"`
	Summary          string               `json:"summary,omitempty"`
	CoverRef         *CanonicalObjectRef  `json:"coverRef,omitempty"`
	TopicRefs        []string             `json:"topicRefs"`
	RequirementRefs  []string             `json:"requirementRefs"`
	SourceObjectRefs []GatheringSourceRef `json:"sourceObjectRefs"`
	CostNotice       string               `json:"costNotice"`
	CostDescription  string               `json:"costDescription,omitempty"`
}

type GatheringSchedule struct {
	Timezone          string `json:"timezone,omitempty"`
	StartAt           string `json:"startAt,omitempty"`
	EndAt             string `json:"endAt,omitempty"`
	AdmissionClosesAt string `json:"admissionClosesAt,omitempty"`
}

type GatheringPlace struct {
	Mode              string              `json:"mode"`
	CoarsePlaceRef    *CanonicalObjectRef `json:"coarsePlaceRef,omitempty"`
	CoarsePlaceLabel  string              `json:"coarsePlaceLabel,omitempty"`
	ExactMeetingPoint string              `json:"exactMeetingPoint,omitempty"`
	OnlineLocationRef string              `json:"onlineLocationRef,omitempty"`
}

type GatheringCapacityPolicy struct {
	MaxParticipants int `json:"maxParticipants"`
}

type GatheringDisclosurePolicy struct {
	TimeDisclosure   string `json:"timeDisclosure"`
	PlaceDisclosure  string `json:"placeDisclosure"`
	RosterDisclosure string `json:"rosterDisclosure"`
}

type GatheringPolicySet struct {
	AudiencePolicy       string                         `json:"audiencePolicy"`
	AdmissionPolicy      string                         `json:"admissionPolicy"`
	CapacityPolicy       GatheringCapacityPolicy        `json:"capacityPolicy"`
	DisclosurePolicy     GatheringDisclosurePolicy      `json:"disclosurePolicy"`
	ApplicationQuestions []GatheringApplicationQuestion `json:"applicationQuestions"`
	RiskControlPolicyRef string                         `json:"riskControlPolicyRef"`
	PolicyDecisionRef    string                         `json:"policyDecisionRef,omitempty"`
	PolicyDigest         string                         `json:"policyDigest,omitempty"`
	ObligationDigest     string                         `json:"obligationDigest,omitempty"`
}

type GatheringCommitments struct {
	Title                string                         `json:"title"`
	Summary              string                         `json:"summary"`
	TopicRefs            []string                       `json:"topicRefs"`
	RequirementRefs      []string                       `json:"requirementRefs"`
	SourceRefs           []GatheringSourceRef           `json:"sourceRefs"`
	CostNotice           string                         `json:"costNotice"`
	CostDescription      string                         `json:"costDescription"`
	Timezone             string                         `json:"timezone"`
	StartAt              string                         `json:"startAt"`
	EndAt                string                         `json:"endAt"`
	AdmissionClosesAt    string                         `json:"admissionClosesAt"`
	PlaceMode            string                         `json:"placeMode"`
	CoarsePlaceRef       *CanonicalObjectRef            `json:"coarsePlaceRef,omitempty"`
	CoarsePlaceLabel     string                         `json:"coarsePlaceLabel"`
	ExactMeetingPoint    string                         `json:"exactMeetingPoint"`
	OnlineLocationRef    string                         `json:"onlineLocationRef"`
	AudiencePolicy       string                         `json:"audiencePolicy"`
	AdmissionPolicy      string                         `json:"admissionPolicy"`
	MaxParticipants      int                            `json:"maxParticipants"`
	TimeDisclosure       string                         `json:"timeDisclosure"`
	PlaceDisclosure      string                         `json:"placeDisclosure"`
	RosterDisclosure     string                         `json:"rosterDisclosure"`
	ApplicationQuestions []GatheringApplicationQuestion `json:"applicationQuestions"`
	RiskControlPolicyRef string                         `json:"riskControlPolicyRef"`
	PolicyDecisionRef    string                         `json:"policyDecisionRef"`
	PolicyDigest         string                         `json:"policyDigest"`
	ObligationDigest     string                         `json:"obligationDigest"`
}

type CreateGatheringDraftCommand struct {
	HostBinding         GatheringHostBinding `json:"hostBinding"`
	CreatorParticipates bool                 `json:"creatorParticipates"`
	Purpose             GatheringPurpose     `json:"purpose"`
	Schedule            GatheringSchedule    `json:"schedule"`
	Place               GatheringPlace       `json:"place"`
	PolicySet           GatheringPolicySet   `json:"policySet"`
}

type UpdateGatheringCommand struct {
	GatheringID               string               `json:"gatheringId"`
	ExpectedGatheringVersion  int64                `json:"expectedGatheringVersion"`
	Purpose                   GatheringPurpose     `json:"purpose"`
	Schedule                  GatheringSchedule    `json:"schedule"`
	Place                     GatheringPlace       `json:"place"`
	PolicySet                 GatheringPolicySet   `json:"policySet"`
	HostBinding               GatheringHostBinding `json:"hostBinding"`
	AcknowledgementDeadlineAt string               `json:"acknowledgementDeadlineAt,omitempty"`
}

type GatheringCreateDraftProposalInput struct {
	HostSubjectKind     string               `json:"hostSubjectKind"`
	HostSubjectID       string               `json:"hostSubjectId"`
	CreatorParticipates bool                 `json:"creatorParticipates"`
	Commitments         GatheringCommitments `json:"commitments"`
}

type GatheringUpdateProposalInput struct {
	GatheringID               string               `json:"gatheringId"`
	ExpectedGatheringVersion  int64                `json:"expectedGatheringVersion"`
	HostSubjectKind           string               `json:"hostSubjectKind"`
	HostSubjectID             string               `json:"hostSubjectId"`
	Commitments               GatheringCommitments `json:"commitments"`
	AcknowledgementDeadlineAt string               `json:"acknowledgementDeadlineAt"`
}

type GatheringProviderDegradation string

const (
	GatheringMapUnavailable      GatheringProviderDegradation = "map_unavailable"
	GatheringWeatherUnavailable  GatheringProviderDegradation = "weather_unavailable"
	GatheringCalendarUnavailable GatheringProviderDegradation = "calendar_unavailable"
)

type GatheringOptionalProviderState struct {
	MapAvailable      bool
	WeatherAvailable  bool
	CalendarAvailable bool
	Evidence          []GatheringProviderBindingEvidence
}

// GatheringProviderBindingEvidence is provider-neutral proposal evidence. It
// identifies the capability and managed binding reference only; adapter,
// endpoint and credential material never enter the proposal sent to Circle.
type GatheringProviderBindingEvidence struct {
	CapabilityKey string `json:"capabilityKey"`
	BindingKind   string `json:"bindingKind"`
	BindingRef    string `json:"bindingRef"`
}

type GatheringCoordinatorStep string

const (
	GatheringCoordinatorPrefillSources GatheringCoordinatorStep = "prefill_content_and_source_refs"
	GatheringCoordinatorAskCommitments GatheringCoordinatorStep = "ask_missing_commitments"
	GatheringCoordinatorDraftProposal  GatheringCoordinatorStep = "draft_typed_proposal"
	GatheringCoordinatorAwaitApproval  GatheringCoordinatorStep = "await_user_confirmation"
	GatheringCoordinatorBindOperation  GatheringCoordinatorStep = "bind_domain_operation"
)

// GatheringCoordinatorSequence is the runtime skill contract while official
// package profile/replay assets remain outside this M5 change. Room/Chat is the
// only working context; no Gathering workspace is introduced.
func GatheringCoordinatorSequence() []GatheringCoordinatorStep {
	return []GatheringCoordinatorStep{
		GatheringCoordinatorPrefillSources,
		GatheringCoordinatorAskCommitments,
		GatheringCoordinatorDraftProposal,
		GatheringCoordinatorAwaitApproval,
		GatheringCoordinatorBindOperation,
	}
}

// GatheringCoordinatorReferencedCapabilities reuses Tool Fabric capabilities.
// It does not define Gathering-specific map, route, weather or calendar tools.
func GatheringCoordinatorReferencedCapabilities() []string {
	return []string{
		"location.poi.search",
		"location.route.read",
		"weather.forecast.read",
		"calendar.event.create",
		"calendar.event.update",
		"calendar.event.delete",
	}
}

func (s GatheringOptionalProviderState) degradations() []GatheringProviderDegradation {
	degradations := make([]GatheringProviderDegradation, 0, 3)
	if !s.MapAvailable {
		degradations = append(degradations, GatheringMapUnavailable)
	}
	if !s.WeatherAvailable {
		degradations = append(degradations, GatheringWeatherUnavailable)
	}
	if !s.CalendarAvailable {
		degradations = append(degradations, GatheringCalendarUnavailable)
	}
	return degradations
}

func (s GatheringOptionalProviderState) evidence() []GatheringProviderBindingEvidence {
	available := map[string]bool{
		"location.poi.search":   s.MapAvailable,
		"location.route.read":   s.MapAvailable,
		"weather.forecast.read": s.WeatherAvailable,
		"calendar.event.create": s.CalendarAvailable,
		"calendar.event.update": s.CalendarAvailable,
		"calendar.event.delete": s.CalendarAvailable,
	}
	result := make([]GatheringProviderBindingEvidence, 0, len(s.Evidence))
	seen := make(map[string]struct{}, len(s.Evidence))
	for _, raw := range s.Evidence {
		evidence := GatheringProviderBindingEvidence{
			CapabilityKey: strings.TrimSpace(raw.CapabilityKey),
			BindingKind:   strings.TrimSpace(raw.BindingKind),
			BindingRef:    strings.TrimSpace(raw.BindingRef),
		}
		if !available[evidence.CapabilityKey] ||
			evidence.BindingKind != "public_provider" ||
			evidence.BindingRef == "" {
			continue
		}
		if _, found := seen[evidence.CapabilityKey]; found {
			continue
		}
		seen[evidence.CapabilityKey] = struct{}{}
		result = append(result, evidence)
	}
	return result
}

type GatheringApprovalIntentContext struct {
	IntentID       string
	JTI            string
	ApprovalPermit string
	IssuedAt       time.Time
	ExpiresAt      time.Time
}

type GatheringProposalEnvelope struct {
	ProposalID       string                             `json:"proposalId"`
	Status           string                             `json:"status"`
	Summary          string                             `json:"summary"`
	RequestDigest    string                             `json:"requestDigest"`
	Binding          DomainOperationBinding             `json:"binding"`
	Approval         *presentation.ActionIntent         `json:"approval,omitempty"`
	Degradations     []GatheringProviderDegradation     `json:"degradations"`
	ProviderEvidence []GatheringProviderBindingEvidence `json:"providerEvidence"`
}

type GatheringCreateDraftProposal struct {
	Envelope GatheringProposalEnvelope   `json:"envelope"`
	Command  CreateGatheringDraftCommand `json:"command"`
}

type GatheringUpdateProposal struct {
	Envelope GatheringProposalEnvelope `json:"envelope"`
	Command  UpdateGatheringCommand    `json:"command"`
}

type GatheringAvailabilityWatchProposal struct {
	Envelope GatheringProposalEnvelope         `json:"envelope"`
	Command  GatheringAvailabilityWatchCommand `json:"command"`
}

type GatheringPlanProposal struct {
	Envelope GatheringProposalEnvelope                       `json:"envelope"`
	Command  gatheringplanclient.ProposeGatheringPlanCommand `json:"command"`
}

func MapGatheringCreateDraftProposal(
	execution GatheringExecutionContext,
	definition GatheringToolDefinition,
	input GatheringCreateDraftProposalInput,
	authority VerifiedGatheringHostAuthority,
	intent GatheringApprovalIntentContext,
	providers GatheringOptionalProviderState,
	now time.Time,
) (GatheringCreateDraftProposal, error) {
	if definition.ToolName != GatheringProposeCreateDraftTool {
		return GatheringCreateDraftProposal{}, ErrGatheringBindingInvalid
	}
	hostBinding, err := validateGatheringHostAuthority(
		execution,
		input.HostSubjectKind,
		input.HostSubjectID,
		"",
		authority,
		now,
	)
	if err != nil {
		return GatheringCreateDraftProposal{}, err
	}
	if err := validateGatheringCommitments(input.Commitments); err != nil {
		return GatheringCreateDraftProposal{}, err
	}
	command := CreateGatheringDraftCommand{
		HostBinding:         hostBinding,
		CreatorParticipates: input.CreatorParticipates,
		Purpose:             input.Commitments.purpose(),
		Schedule:            input.Commitments.schedule(),
		Place:               input.Commitments.place(),
		PolicySet:           input.Commitments.policySet(),
	}
	requestDigest, err := CanonicalGatheringRequestDigest(command)
	if err != nil {
		return GatheringCreateDraftProposal{}, err
	}
	proposalID := gatheringProposalID(requestDigest)
	target := runtimeauth.DelegatedResourceConstraint{
		Type: "circle.gathering.draft",
		ID:   proposalID,
	}
	binding, err := NewDomainOperationBinding(definition, requestDigest, target)
	if err != nil {
		return GatheringCreateDraftProposal{}, err
	}
	approval, err := buildGatheringApproveToolIntent(
		execution,
		definition,
		requestDigest,
		intent,
	)
	if err != nil {
		return GatheringCreateDraftProposal{}, err
	}
	return GatheringCreateDraftProposal{
		Envelope: GatheringProposalEnvelope{
			ProposalID:       proposalID,
			Status:           "awaiting_user_confirmation",
			Summary:          "聚会草稿已准备，确认后才会提交 Circle。",
			RequestDigest:    requestDigest,
			Binding:          binding,
			Approval:         &approval,
			Degradations:     providers.degradations(),
			ProviderEvidence: providers.evidence(),
		},
		Command: command,
	}, nil
}

func MapGatheringUpdateProposal(
	execution GatheringExecutionContext,
	definition GatheringToolDefinition,
	input GatheringUpdateProposalInput,
	authority VerifiedGatheringHostAuthority,
	intent GatheringApprovalIntentContext,
	providers GatheringOptionalProviderState,
	now time.Time,
) (GatheringUpdateProposal, error) {
	if definition.ToolName != GatheringProposeUpdateTool ||
		input.ExpectedGatheringVersion < 1 {
		return GatheringUpdateProposal{}, ErrGatheringBindingInvalid
	}
	hostBinding, err := validateGatheringHostAuthority(
		execution,
		input.HostSubjectKind,
		input.HostSubjectID,
		input.GatheringID,
		authority,
		now,
	)
	if err != nil {
		return GatheringUpdateProposal{}, err
	}
	if err := validateGatheringCommitments(input.Commitments); err != nil {
		return GatheringUpdateProposal{}, err
	}
	command := UpdateGatheringCommand{
		GatheringID:               strings.TrimSpace(input.GatheringID),
		ExpectedGatheringVersion:  input.ExpectedGatheringVersion,
		Purpose:                   input.Commitments.purpose(),
		Schedule:                  input.Commitments.schedule(),
		Place:                     input.Commitments.place(),
		PolicySet:                 input.Commitments.policySet(),
		HostBinding:               hostBinding,
		AcknowledgementDeadlineAt: strings.TrimSpace(input.AcknowledgementDeadlineAt),
	}
	requestDigest, err := CanonicalGatheringRequestDigest(command)
	if err != nil {
		return GatheringUpdateProposal{}, err
	}
	binding, err := NewDomainOperationBinding(
		definition,
		requestDigest,
		gatheringTarget(command.GatheringID),
	)
	if err != nil {
		return GatheringUpdateProposal{}, err
	}
	approval, err := buildGatheringApproveToolIntent(
		execution,
		definition,
		requestDigest,
		intent,
	)
	if err != nil {
		return GatheringUpdateProposal{}, err
	}
	return GatheringUpdateProposal{
		Envelope: GatheringProposalEnvelope{
			ProposalID:       gatheringProposalID(requestDigest),
			Status:           "awaiting_user_confirmation",
			Summary:          "聚会变更已准备，确认后才会提交 Circle。",
			RequestDigest:    requestDigest,
			Binding:          binding,
			Approval:         &approval,
			Degradations:     providers.degradations(),
			ProviderEvidence: providers.evidence(),
		},
		Command: command,
	}, nil
}

func MapGatheringAvailabilityWatchProposal(
	execution GatheringExecutionContext,
	definition GatheringToolDefinition,
	request GatheringAvailabilityWatchCommand,
	intent GatheringApprovalIntentContext,
) (GatheringAvailabilityWatchProposal, error) {
	if definition.ToolName != GatheringWatchAvailabilityTool ||
		strings.TrimSpace(request.GatheringID) == "" ||
		request.ExpectedGatheringVersion < 1 ||
		request.ExpectedWatchVersion < 0 {
		return GatheringAvailabilityWatchProposal{}, ErrGatheringBindingInvalid
	}
	requestDigest, err := CanonicalGatheringRequestDigest(request)
	if err != nil {
		return GatheringAvailabilityWatchProposal{}, err
	}
	binding, err := NewDomainOperationBinding(
		definition,
		requestDigest,
		gatheringTarget(request.GatheringID),
	)
	if err != nil {
		return GatheringAvailabilityWatchProposal{}, err
	}
	approval, err := buildGatheringApproveToolIntent(
		execution,
		definition,
		requestDigest,
		intent,
	)
	if err != nil {
		return GatheringAvailabilityWatchProposal{}, err
	}
	return GatheringAvailabilityWatchProposal{
		Envelope: GatheringProposalEnvelope{
			ProposalID:    gatheringProposalID(requestDigest),
			Status:        "awaiting_user_confirmation",
			Summary:       "名额关注已准备，确认后只会创建提醒，不会自动加入或占座。",
			RequestDigest: requestDigest,
			Binding:       binding,
			Approval:      &approval,
		},
		Command: request,
	}, nil
}

func MapGatheringPlanProposal(
	execution GatheringExecutionContext,
	definition GatheringToolDefinition,
	request gatheringplanclient.ProposeGatheringPlanCommand,
	intent GatheringApprovalIntentContext,
) (GatheringPlanProposal, error) {
	if definition.ToolName != GatheringProposePlanTool ||
		strings.TrimSpace(request.PlanID) == "" ||
		request.ExpectedPlanVersion < 1 ||
		strings.TrimSpace(request.BaseRevisionID) == "" ||
		request.BaseRevisionNumber < 1 ||
		strings.TrimSpace(request.BaseRevisionDigest) == "" ||
		len(request.Items) == 0 {
		return GatheringPlanProposal{}, ErrGatheringBindingInvalid
	}
	packet, err := gatheringplanclient.EncodeProposeGatheringPlan(request)
	if err != nil {
		return GatheringPlanProposal{}, err
	}
	requestDigest := gatheringplanclient.CanonicalRequestDigest(
		packet.CanonicalRequest,
	)
	binding, err := NewDomainOperationBinding(
		definition,
		requestDigest,
		gatheringPlanTarget(request.PlanID),
	)
	if err != nil {
		return GatheringPlanProposal{}, err
	}
	approval, err := buildGatheringApproveToolIntent(
		execution,
		definition,
		requestDigest,
		intent,
	)
	if err != nil {
		return GatheringPlanProposal{}, err
	}
	return GatheringPlanProposal{
		Envelope: GatheringProposalEnvelope{
			ProposalID:    gatheringProposalID(requestDigest),
			Status:        "awaiting_user_confirmation",
			Summary:       "计划提议已准备；确认后只会提交 Proposal，不会自动接受或推进当前 Revision。",
			RequestDigest: requestDigest,
			Binding:       binding,
			Approval:      &approval,
		},
		Command: request,
	}, nil
}

func buildGatheringApproveToolIntent(
	execution GatheringExecutionContext,
	definition GatheringToolDefinition,
	requestDigest string,
	intent GatheringApprovalIntentContext,
) (presentation.ActionIntent, error) {
	if err := execution.validate(); err != nil ||
		strings.TrimSpace(intent.IntentID) == "" ||
		strings.TrimSpace(intent.JTI) == "" ||
		strings.TrimSpace(intent.ApprovalPermit) == "" ||
		intent.IssuedAt.IsZero() ||
		!intent.ExpiresAt.After(intent.IssuedAt) ||
		!definition.ApprovalPolicy.UserConfirmationRequiredBeforeEffect {
		return presentation.ActionIntent{}, ErrGatheringBindingInvalid
	}
	return presentation.ActionIntent{
		IntentID:      intent.IntentID,
		Kind:          presentation.ActionIntentApproveTool,
		RequestDigest: requestDigest,
		JTI:           intent.JTI,
		IssuedAt:      intent.IssuedAt.UTC(),
		ExpiresAt:     intent.ExpiresAt.UTC(),
		ApproveTool: &presentation.ApproveToolIntent{
			RunID:            execution.RunID,
			ToolInvocationID: execution.ToolInvocationID,
			Decision:         "approve",
			Capability:       definition.RequiredCapability,
			InputDigest:      requestDigest,
			ApprovalPermit:   intent.ApprovalPermit,
		},
	}, nil
}

func validateGatheringHostAuthority(
	execution GatheringExecutionContext,
	hostSubjectKind string,
	hostSubjectID string,
	gatheringID string,
	authority VerifiedGatheringHostAuthority,
	now time.Time,
) (GatheringHostBinding, error) {
	if err := execution.validate(); err != nil {
		return GatheringHostBinding{}, err
	}
	if authority.AccountID != execution.AccountID ||
		authority.PersonaID != execution.PersonaID ||
		authority.HostSubjectKind != strings.TrimSpace(hostSubjectKind) ||
		authority.HostSubjectID != strings.TrimSpace(hostSubjectID) ||
		strings.TrimSpace(authority.AuthorityEvidenceRef) == "" ||
		authority.AuthorityVersion < 1 ||
		authority.AuthorityExpiresAt.IsZero() ||
		!authority.AuthorityExpiresAt.After(now.UTC()) {
		return GatheringHostBinding{}, ErrGatheringHostUnauthorized
	}
	if strings.TrimSpace(gatheringID) != "" &&
		authority.GatheringID != strings.TrimSpace(gatheringID) {
		return GatheringHostBinding{}, ErrGatheringHostUnauthorized
	}
	return GatheringHostBinding{
		HostSubjectKind:      authority.HostSubjectKind,
		HostSubjectID:        authority.HostSubjectID,
		AuthorityEvidenceRef: authority.AuthorityEvidenceRef,
		AuthorityVersion:     authority.AuthorityVersion,
		AuthorityExpiresAt:   authority.AuthorityExpiresAt.UTC().Format(time.RFC3339),
	}, nil
}

func validateGatheringCommitments(commitments GatheringCommitments) error {
	if strings.TrimSpace(commitments.Title) == "" ||
		strings.TrimSpace(commitments.CostNotice) == "" ||
		strings.TrimSpace(commitments.PlaceMode) == "" ||
		strings.TrimSpace(commitments.AudiencePolicy) == "" ||
		strings.TrimSpace(commitments.AdmissionPolicy) == "" ||
		commitments.MaxParticipants < 2 ||
		strings.TrimSpace(commitments.TimeDisclosure) == "" ||
		strings.TrimSpace(commitments.PlaceDisclosure) == "" ||
		strings.TrimSpace(commitments.RosterDisclosure) == "" ||
		strings.TrimSpace(commitments.RiskControlPolicyRef) == "" ||
		len(commitments.SourceRefs) == 0 {
		return ErrGatheringBindingInvalid
	}
	for _, source := range commitments.SourceRefs {
		if strings.TrimSpace(source.ObjectRef.ObjectTypeRef) == "" ||
			strings.TrimSpace(source.ObjectRef.ObjectID) == "" ||
			strings.TrimSpace(source.RouteID) == "" ||
			validateSHA256Digest(source.SourceDigest) != nil {
			return ErrGatheringBindingInvalid
		}
	}
	return nil
}

func (c GatheringCommitments) purpose() GatheringPurpose {
	return GatheringPurpose{
		Title:            strings.TrimSpace(c.Title),
		Summary:          strings.TrimSpace(c.Summary),
		TopicRefs:        append([]string(nil), c.TopicRefs...),
		RequirementRefs:  append([]string(nil), c.RequirementRefs...),
		SourceObjectRefs: append([]GatheringSourceRef(nil), c.SourceRefs...),
		CostNotice:       strings.TrimSpace(c.CostNotice),
		CostDescription:  strings.TrimSpace(c.CostDescription),
	}
}

func (c GatheringCommitments) schedule() GatheringSchedule {
	return GatheringSchedule{
		Timezone:          strings.TrimSpace(c.Timezone),
		StartAt:           strings.TrimSpace(c.StartAt),
		EndAt:             strings.TrimSpace(c.EndAt),
		AdmissionClosesAt: strings.TrimSpace(c.AdmissionClosesAt),
	}
}

func (c GatheringCommitments) place() GatheringPlace {
	return GatheringPlace{
		Mode:              strings.TrimSpace(c.PlaceMode),
		CoarsePlaceRef:    c.CoarsePlaceRef,
		CoarsePlaceLabel:  strings.TrimSpace(c.CoarsePlaceLabel),
		ExactMeetingPoint: strings.TrimSpace(c.ExactMeetingPoint),
		OnlineLocationRef: strings.TrimSpace(c.OnlineLocationRef),
	}
}

func (c GatheringCommitments) policySet() GatheringPolicySet {
	return GatheringPolicySet{
		AudiencePolicy:  strings.TrimSpace(c.AudiencePolicy),
		AdmissionPolicy: strings.TrimSpace(c.AdmissionPolicy),
		CapacityPolicy:  GatheringCapacityPolicy{MaxParticipants: c.MaxParticipants},
		DisclosurePolicy: GatheringDisclosurePolicy{
			TimeDisclosure:   strings.TrimSpace(c.TimeDisclosure),
			PlaceDisclosure:  strings.TrimSpace(c.PlaceDisclosure),
			RosterDisclosure: strings.TrimSpace(c.RosterDisclosure),
		},
		ApplicationQuestions: append(
			[]GatheringApplicationQuestion(nil),
			c.ApplicationQuestions...,
		),
		RiskControlPolicyRef: strings.TrimSpace(c.RiskControlPolicyRef),
		PolicyDecisionRef:    strings.TrimSpace(c.PolicyDecisionRef),
		PolicyDigest:         strings.TrimSpace(c.PolicyDigest),
		ObligationDigest:     strings.TrimSpace(c.ObligationDigest),
	}
}

func gatheringProposalID(requestDigest string) string {
	return fmt.Sprintf("gathering-proposal-%s", strings.TrimPrefix(requestDigest, "sha256:")[:24])
}
