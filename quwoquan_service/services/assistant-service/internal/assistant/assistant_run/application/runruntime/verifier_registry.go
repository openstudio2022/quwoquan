package runruntime

import (
	"context"
	"errors"
	"fmt"
	"sort"
	"strings"
	"unicode"
	"unicode/utf8"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
)

type VerifierMode string

const (
	VerifierModeDeterministic    VerifierMode = "deterministic"
	VerifierModeConstrainedModel VerifierMode = "constrained_model"

	VerifierAnswerEvidence      = "platform.verifier.answer_evidence"
	VerifierGoalSatisfaction    = "platform.verifier.goal_satisfaction"
	VerifierTravelPlanIntegrity = "platform.verifier.travel_plan_integrity"
	VerifierSourceConflict      = "platform.verifier.source_conflict"
	VerifierChangeNotification  = "platform.verifier.change_notification"
	VerifierSharedPrivacy       = "platform.verifier.shared_surface_privacy"
	VerifierToolReceipt         = "platform.verifier.tool_receipt"
)

type VerificationInput struct {
	Run                   Run
	Result                ExecutionResult
	AvailableArtifactRefs []string
}

type VerificationRequest struct {
	Requirement string
	Input       VerificationInput
}

type RequirementVerifier interface {
	Verify(context.Context, VerificationRequest) (VerificationEvidence, error)
}

type RequirementVerifierFunc func(
	context.Context,
	VerificationRequest,
) (VerificationEvidence, error)

func (verify RequirementVerifierFunc) Verify(
	ctx context.Context,
	request VerificationRequest,
) (VerificationEvidence, error) {
	return verify(ctx, request)
}

type VerifierDescriptor struct {
	VerifierID       string
	Mode             VerifierMode
	RequirementTypes []string
	Verifier         RequirementVerifier
}

type VerifierRegistry struct {
	byRequirement map[string]VerifierDescriptor
	byID          map[string]VerifierDescriptor
}

// ConstrainedVerificationModel receives only the frozen completion contract,
// the public answer, bounded process summaries and artifact references. It
// cannot mutate Run state, tool policy or protected facts.
type ConstrainedVerificationModel interface {
	VerifyRequirement(
		context.Context,
		ConstrainedVerificationRequest,
	) (ConstrainedVerificationResponse, error)
}

type ConstrainedVerificationModelFunc func(
	context.Context,
	ConstrainedVerificationRequest,
) (ConstrainedVerificationResponse, error)

func (verify ConstrainedVerificationModelFunc) VerifyRequirement(
	ctx context.Context,
	request ConstrainedVerificationRequest,
) (ConstrainedVerificationResponse, error) {
	return verify(ctx, request)
}

type ConstrainedVerificationRequest struct {
	Requirement  string
	Goal         string
	Constraints  []string
	AnswerText   string
	ProcessNotes []string
	ArtifactRefs []string
}

type ConstrainedVerificationResponse struct {
	Passed        bool
	ArtifactRefs  []string
	Summary       string
	FixSuggestion string
}

func NewVerifierRegistry(
	descriptors ...VerifierDescriptor,
) (*VerifierRegistry, error) {
	registry := &VerifierRegistry{
		byRequirement: map[string]VerifierDescriptor{},
		byID:          map[string]VerifierDescriptor{},
	}
	for _, descriptor := range descriptors {
		descriptor.VerifierID = strings.TrimSpace(descriptor.VerifierID)
		if !validPolicyRef(descriptor.VerifierID) ||
			(descriptor.Mode != VerifierModeDeterministic &&
				descriptor.Mode != VerifierModeConstrainedModel) ||
			descriptor.Verifier == nil || len(descriptor.RequirementTypes) == 0 {
			return nil, fmt.Errorf("invalid AssistantRun verifier descriptor %q", descriptor.VerifierID)
		}
		if _, duplicate := registry.byID[descriptor.VerifierID]; duplicate {
			return nil, fmt.Errorf("duplicate AssistantRun verifier %q", descriptor.VerifierID)
		}
		normalizedRequirements := make([]string, 0, len(descriptor.RequirementTypes))
		for _, requirement := range descriptor.RequirementTypes {
			requirement = strings.TrimSpace(requirement)
			if !validRequirementType(requirement) {
				return nil, fmt.Errorf(
					"verifier %q has invalid requirement type %q",
					descriptor.VerifierID,
					requirement,
				)
			}
			if previous, duplicate := registry.byRequirement[requirement]; duplicate {
				return nil, fmt.Errorf(
					"requirement %q has multiple verifiers %q and %q",
					requirement,
					previous.VerifierID,
					descriptor.VerifierID,
				)
			}
			normalizedRequirements = append(normalizedRequirements, requirement)
			registry.byRequirement[requirement] = descriptor
		}
		descriptor.RequirementTypes = uniqueSorted(normalizedRequirements)
		registry.byID[descriptor.VerifierID] = descriptor
		for _, requirement := range descriptor.RequirementTypes {
			registry.byRequirement[requirement] = descriptor
		}
	}
	if len(registry.byID) == 0 {
		return nil, errors.New("AssistantRun verifier registry is empty")
	}
	return registry, nil
}

func NewPlatformVerifierRegistry(
	model ConstrainedVerificationModel,
) (*VerifierRegistry, error) {
	return NewVerifierRegistry(
		VerifierDescriptor{
			VerifierID: VerifierAnswerEvidence,
			Mode:       VerifierModeDeterministic,
			RequirementTypes: []string{
				"answer_present",
				"evidence_present",
				"citations_present",
				"time_sensitive_facts_have_sources",
			},
			Verifier: RequirementVerifierFunc(verifyAnswerAndEvidence),
		},
		VerifierDescriptor{
			VerifierID: VerifierGoalSatisfaction,
			Mode:       VerifierModeConstrainedModel,
			RequirementTypes: []string{
				"answer_satisfies_user_goal",
				"goal_and_constraints_are_explicit",
				"answer_has_an_actionable_next_step",
			},
			Verifier: constrainedRequirementVerifier{model: model},
		},
		VerifierDescriptor{
			VerifierID: VerifierTravelPlanIntegrity,
			Mode:       VerifierModeConstrainedModel,
			RequirementTypes: []string{
				"eat_play_stay_transport_are_coherent",
				"time_and_route_conflicts_are_checked",
			},
			Verifier: constrainedRequirementVerifier{model: model},
		},
		VerifierDescriptor{
			VerifierID:       VerifierSourceConflict,
			Mode:             VerifierModeDeterministic,
			RequirementTypes: []string{"source_conflicts_are_resolved"},
			Verifier:         RequirementVerifierFunc(verifySourceConflicts),
		},
		VerifierDescriptor{
			VerifierID:       VerifierChangeNotification,
			Mode:             VerifierModeDeterministic,
			RequirementTypes: []string{"plan_changes_are_expressed_as_revision_diff"},
			Verifier:         RequirementVerifierFunc(verifyChangeNotification),
		},
		VerifierDescriptor{
			VerifierID:       VerifierSharedPrivacy,
			Mode:             VerifierModeDeterministic,
			RequirementTypes: []string{"shared_surface_privacy_is_preserved"},
			Verifier:         RequirementVerifierFunc(verifySharedSurfacePrivacy),
		},
		VerifierDescriptor{
			VerifierID:       VerifierToolReceipt,
			Mode:             VerifierModeDeterministic,
			RequirementTypes: []string{"tool_receipts_are_verified"},
			Verifier:         RequirementVerifierFunc(verifyToolReceipts),
		},
	)
}

func (registry *VerifierRegistry) Verify(
	ctx context.Context,
	definition DefinitionOfDone,
	input VerificationInput,
) VerificationVerdict {
	available := uniqueSorted(input.AvailableArtifactRefs)
	availableSet := make(map[string]struct{}, len(available))
	for _, artifactRef := range available {
		availableSet[artifactRef] = struct{}{}
	}
	evidence := make([]VerificationEvidence, 0, len(definition.VerificationRequirements))
	for _, requirement := range definition.VerificationRequirements {
		requirement = strings.TrimSpace(requirement)
		descriptor, ok := registry.descriptorFor(requirement)
		if !ok {
			evidence = append(evidence, VerificationEvidence{
				Requirement:   requirement,
				Summary:       "no platform verifier is registered for this requirement",
				FixSuggestion: "register and bind a platform-owned verifier before retrying completion",
			})
			continue
		}
		row, err := descriptor.Verifier.Verify(ctx, VerificationRequest{
			Requirement: requirement,
			Input:       input,
		})
		row.Requirement = requirement
		row.VerifierID = descriptor.VerifierID
		row.ArtifactRefs = uniqueSorted(row.ArtifactRefs)
		row.Summary = boundedVerificationText(row.Summary, 512)
		row.FixSuggestion = boundedVerificationText(row.FixSuggestion, 512)
		if err != nil {
			row.Passed = false
			row.ArtifactRefs = nil
			row.Summary = "platform verifier could not produce a valid verdict"
			if row.FixSuggestion == "" {
				row.FixSuggestion = "repair verifier evidence or wait for the constrained verifier dependency"
			}
		}
		if row.Passed && !allArtifactsAvailable(row.ArtifactRefs, availableSet) {
			row.Passed = false
			row.Summary = "verifier evidence is not backed by the current Run artifact ledger"
			row.FixSuggestion = "produce artifact-backed evidence in the same Run before completion"
		}
		evidence = append(evidence, row)
	}
	return VerifyDefinitionOfDone(definition, evidence, available)
}

func (registry *VerifierRegistry) ValidateProfileRefs(
	requirements []string,
	verifierRefs []string,
) error {
	if registry == nil || len(verifierRefs) == 0 {
		return errors.New("Skill orchestration verifier refs are empty")
	}
	selected := map[string]VerifierDescriptor{}
	for _, ref := range verifierRefs {
		ref = strings.TrimSpace(ref)
		if _, duplicate := selected[ref]; duplicate {
			return fmt.Errorf("duplicate Skill verifier ref %q", ref)
		}
		descriptor, ok := registry.byID[ref]
		if !ok {
			return fmt.Errorf("Skill references unknown platform verifier %q", ref)
		}
		selected[ref] = descriptor
	}
	used := map[string]bool{}
	for _, requirement := range requirements {
		requirement = strings.TrimSpace(requirement)
		descriptor, ok := registry.byRequirement[requirement]
		if !ok {
			return fmt.Errorf("Skill requirement %q has no platform verifier", requirement)
		}
		if _, referenced := selected[descriptor.VerifierID]; !referenced {
			return fmt.Errorf(
				"Skill requirement %q does not reference verifier %q",
				requirement,
				descriptor.VerifierID,
			)
		}
		used[descriptor.VerifierID] = true
	}
	for ref := range selected {
		if !used[ref] {
			return fmt.Errorf("Skill verifier ref %q does not verify a declared requirement", ref)
		}
	}
	return nil
}

func (registry *VerifierRegistry) descriptorFor(
	requirement string,
) (VerifierDescriptor, bool) {
	if registry == nil {
		return VerifierDescriptor{}, false
	}
	descriptor, ok := registry.byRequirement[strings.TrimSpace(requirement)]
	return descriptor, ok
}

type constrainedRequirementVerifier struct {
	model ConstrainedVerificationModel
}

func (verifier constrainedRequirementVerifier) Verify(
	ctx context.Context,
	request VerificationRequest,
) (VerificationEvidence, error) {
	if verifier.model == nil {
		return VerificationEvidence{}, errors.New("constrained verification model is unavailable")
	}
	processNotes := make([]string, 0, len(request.Input.Result.Processes))
	for _, process := range request.Input.Result.Processes {
		note := strings.TrimSpace(process.Stage + ": " + process.Summary)
		if note != ":" && note != "" {
			processNotes = append(processNotes, boundedVerificationText(note, 512))
		}
	}
	response, err := verifier.model.VerifyRequirement(ctx, ConstrainedVerificationRequest{
		Requirement:  request.Requirement,
		Goal:         boundedVerificationText(request.Input.Run.DefinitionOfDone.Outcome, 2048),
		Constraints:  boundedVerificationStrings(request.Input.Run.DefinitionOfDone.Constraints, 32, 512),
		AnswerText:   boundedVerificationText(request.Input.Result.AnswerText, 8192),
		ProcessNotes: boundedVerificationStrings(processNotes, 64, 512),
		ArtifactRefs: uniqueSorted(request.Input.AvailableArtifactRefs),
	})
	if err != nil {
		return VerificationEvidence{}, err
	}
	return VerificationEvidence{
		Passed:        response.Passed,
		ArtifactRefs:  response.ArtifactRefs,
		Summary:       response.Summary,
		FixSuggestion: response.FixSuggestion,
	}, nil
}

func verifyAnswerAndEvidence(
	_ context.Context,
	request VerificationRequest,
) (VerificationEvidence, error) {
	answerRef := answerArtifactRef(request.Input.AvailableArtifactRefs)
	evidenceRefs := uniqueSorted(request.Input.Result.EvidenceRefs)
	switch request.Requirement {
	case "answer_present":
		passed := strings.TrimSpace(request.Input.Result.AnswerText) != "" && answerRef != ""
		return VerificationEvidence{
			Passed:        passed,
			ArtifactRefs:  nonEmptyRefs(answerRef),
			Summary:       chooseVerificationSummary(passed, "durable final answer is present", "durable final answer is absent"),
			FixSuggestion: chooseFixSuggestion(passed, "persist a non-empty final answer RunItem"),
		}, nil
	case "evidence_present":
		passed := len(evidenceRefs) > 0
		return VerificationEvidence{
			Passed:        passed,
			ArtifactRefs:  evidenceRefs,
			Summary:       chooseVerificationSummary(passed, "authoritative evidence references are present", "authoritative evidence references are absent"),
			FixSuggestion: chooseFixSuggestion(passed, "collect and persist authoritative evidence"),
		}, nil
	case "citations_present", "time_sensitive_facts_have_sources":
		passed := len(evidenceRefs) > 0 && executionResultHasAcceptedEvidence(request.Input.Result)
		return VerificationEvidence{
			Passed:        passed,
			ArtifactRefs:  evidenceRefs,
			Summary:       chooseVerificationSummary(passed, "accepted citations are bound to Run evidence", "accepted citation evidence is incomplete"),
			FixSuggestion: chooseFixSuggestion(passed, "re-check time-sensitive claims and bind accepted source references"),
		}, nil
	default:
		return VerificationEvidence{}, fmt.Errorf("unsupported answer/evidence requirement %q", request.Requirement)
	}
}

func verifySourceConflicts(
	_ context.Context,
	request VerificationRequest,
) (VerificationEvidence, error) {
	conflicts := recursiveStringSlice(request.Input.Run.ContextSnapshot, "sourceConflicts")
	resolved := recursiveStringSlice(request.Input.Result.Presentation, "resolvedSourceConflicts")
	if len(conflicts) == 0 {
		return VerificationEvidence{
			Passed:       true,
			ArtifactRefs: completionEvidenceRefs(request.Input),
			Summary:      "no unresolved source conflict is present",
		}, nil
	}
	unresolved := stringSetDifference(conflicts, resolved)
	passed := len(unresolved) == 0 && len(request.Input.Result.EvidenceRefs) > 0
	return VerificationEvidence{
		Passed:        passed,
		ArtifactRefs:  uniqueSorted(request.Input.Result.EvidenceRefs),
		Summary:       chooseVerificationSummary(passed, "source conflicts are explicitly resolved", "source conflicts remain unresolved"),
		FixSuggestion: chooseFixSuggestion(passed, "explain each conflicting source and record the chosen evidence"),
	}, nil
}

func verifyChangeNotification(
	_ context.Context,
	request VerificationRequest,
) (VerificationEvidence, error) {
	changeRequired := len(request.Input.Run.GoalHistory) > 1 ||
		recursiveHasKey(request.Input.Run.ContextSnapshot, "revisionDiff")
	if !changeRequired {
		return VerificationEvidence{
			Passed:       true,
			ArtifactRefs: completionEvidenceRefs(request.Input),
			Summary:      "no plan revision requires a change notification",
		}, nil
	}
	hasDiff := recursiveHasNonEmptyValue(request.Input.Result.Presentation, "revisionDiff")
	hasNotification := recursiveHasNonEmptyValue(request.Input.Result.Presentation, "changeNotification") ||
		recursiveHasNonEmptyValue(request.Input.Result.Presentation, "notificationRefs")
	passed := hasDiff && hasNotification
	return VerificationEvidence{
		Passed:        passed,
		ArtifactRefs:  completionEvidenceRefs(request.Input),
		Summary:       chooseVerificationSummary(passed, "plan revision diff and notification are ready", "plan change lacks a revision diff or notification"),
		FixSuggestion: chooseFixSuggestion(passed, "produce an explicit revision diff and affected-member notification"),
	}, nil
}

func verifySharedSurfacePrivacy(
	_ context.Context,
	request VerificationRequest,
) (VerificationEvidence, error) {
	surfaceKind := strings.ToLower(strings.TrimSpace(request.Input.Run.RequestContext.SurfaceKind))
	shared := surfaceKind == "conversation" || surfaceKind == "circle"
	violations := 0
	if shared {
		violations += countForbiddenPrivateKeys(request.Input.Result.Presentation)
	}
	passed := !shared || violations == 0
	return VerificationEvidence{
		Passed:        passed,
		ArtifactRefs:  completionEvidenceRefs(request.Input),
		Summary:       chooseVerificationSummary(passed, "shared-surface presentation contains no forbidden private fields", "shared-surface presentation exposes forbidden private fields"),
		FixSuggestion: chooseFixSuggestion(passed, "remove personal connectors, precise location, room and contact details from shared output"),
	}, nil
}

func verifyToolReceipts(
	_ context.Context,
	request VerificationRequest,
) (VerificationEvidence, error) {
	toolItems := make([]RunItem, 0)
	for _, item := range request.Input.Run.Items {
		if item.Kind == generated.AssistantRunItemKindToolUse {
			toolItems = append(toolItems, item)
		}
	}
	if len(toolItems) == 0 {
		return VerificationEvidence{
			Passed:       true,
			ArtifactRefs: completionEvidenceRefs(request.Input),
			Summary:      "completion did not require a tool receipt",
		}, nil
	}
	artifactRefs := []string{}
	passed := true
	for _, item := range toolItems {
		if item.Status != generated.AssistantRunItemStatusCompleted || len(item.ArtifactRefs) == 0 {
			passed = false
		}
		artifactRefs = append(artifactRefs, item.ArtifactRefs...)
	}
	return VerificationEvidence{
		Passed:        passed,
		ArtifactRefs:  uniqueSorted(artifactRefs),
		Summary:       chooseVerificationSummary(passed, "all tool calls have completed artifact-backed receipts", "one or more tool calls lack a completed artifact-backed receipt"),
		FixSuggestion: chooseFixSuggestion(passed, "wait for every tool receipt and persist its artifact reference"),
	}, nil
}

func answerArtifactRef(values []string) string {
	for _, value := range uniqueSorted(values) {
		if strings.HasPrefix(value, "assistant_run_item:answer:") {
			return value
		}
	}
	return ""
}

func completionEvidenceRefs(input VerificationInput) []string {
	refs := uniqueSorted(input.Result.EvidenceRefs)
	if len(refs) > 0 {
		return refs
	}
	return nonEmptyRefs(answerArtifactRef(input.AvailableArtifactRefs))
}

func executionResultHasAcceptedEvidence(result ExecutionResult) bool {
	for _, process := range result.Processes {
		if len(process.AcceptedReferences) > 0 || process.AcceptedDocumentCount > 0 {
			return true
		}
	}
	return false
}

func countForbiddenPrivateKeys(value any) int {
	forbidden := map[string]struct{}{
		"authorization": {}, "cookie": {}, "credentials": {}, "connectionref": {},
		"connectorconnectionref": {}, "hotelroomnumber": {}, "participantcontactdetails": {},
		"continuouspreciselocation": {}, "preciselocation": {}, "phonenumber": {},
	}
	count := 0
	var walk func(any)
	walk = func(current any) {
		switch typed := current.(type) {
		case map[string]any:
			for key, child := range typed {
				if _, found := forbidden[normalizedStructuredKey(key)]; found {
					count++
				}
				walk(child)
			}
		case []any:
			for _, child := range typed {
				walk(child)
			}
		case []map[string]any:
			for _, child := range typed {
				walk(child)
			}
		}
	}
	walk(value)
	return count
}

func recursiveStringSlice(value any, target string) []string {
	result := []string{}
	var walk func(any)
	walk = func(current any) {
		switch typed := current.(type) {
		case map[string]any:
			for key, child := range typed {
				if key == target {
					result = append(result, stringValues(child)...)
				}
				walk(child)
			}
		case []any:
			for _, child := range typed {
				walk(child)
			}
		case []map[string]any:
			for _, child := range typed {
				walk(child)
			}
		}
	}
	walk(value)
	return uniqueSorted(result)
}

func recursiveHasKey(value any, target string) bool {
	return recursiveHasValue(value, target, false)
}

func recursiveHasNonEmptyValue(value any, target string) bool {
	return recursiveHasValue(value, target, true)
}

func recursiveHasValue(value any, target string, requireNonEmpty bool) bool {
	switch typed := value.(type) {
	case map[string]any:
		for key, child := range typed {
			if key == target && (!requireNonEmpty || !emptyStructuredValue(child)) {
				return true
			}
			if recursiveHasValue(child, target, requireNonEmpty) {
				return true
			}
		}
	case []any:
		for _, child := range typed {
			if recursiveHasValue(child, target, requireNonEmpty) {
				return true
			}
		}
	case []map[string]any:
		for _, child := range typed {
			if recursiveHasValue(child, target, requireNonEmpty) {
				return true
			}
		}
	}
	return false
}

func emptyStructuredValue(value any) bool {
	switch typed := value.(type) {
	case nil:
		return true
	case string:
		return strings.TrimSpace(typed) == ""
	case []string:
		return len(typed) == 0
	case []any:
		return len(typed) == 0
	case map[string]any:
		return len(typed) == 0
	default:
		return false
	}
}

func stringValues(value any) []string {
	result := []string{}
	switch typed := value.(type) {
	case string:
		if value := strings.TrimSpace(typed); value != "" {
			result = append(result, value)
		}
	case []string:
		result = append(result, typed...)
	case []any:
		for _, item := range typed {
			if value, ok := item.(string); ok && strings.TrimSpace(value) != "" {
				result = append(result, strings.TrimSpace(value))
			}
		}
	}
	return result
}

func stringSetDifference(left []string, right []string) []string {
	rightSet := map[string]struct{}{}
	for _, value := range right {
		rightSet[strings.TrimSpace(value)] = struct{}{}
	}
	result := []string{}
	for _, value := range left {
		value = strings.TrimSpace(value)
		if _, found := rightSet[value]; !found {
			result = append(result, value)
		}
	}
	return uniqueSorted(result)
}

func nonEmptyRefs(values ...string) []string { return uniqueSorted(values) }

func chooseVerificationSummary(passed bool, accepted string, rejected string) string {
	if passed {
		return accepted
	}
	return rejected
}

func chooseFixSuggestion(passed bool, suggestion string) string {
	if passed {
		return ""
	}
	return suggestion
}

func boundedVerificationText(value string, maxRunes int) string {
	value = strings.TrimSpace(value)
	if maxRunes <= 0 || utf8.RuneCountInString(value) <= maxRunes {
		return value
	}
	return string([]rune(value)[:maxRunes])
}

func boundedVerificationStrings(values []string, maxItems int, maxRunes int) []string {
	if maxItems <= 0 {
		return nil
	}
	result := make([]string, 0, min(len(values), maxItems))
	for _, value := range values {
		value = boundedVerificationText(value, maxRunes)
		if value != "" {
			result = append(result, value)
		}
		if len(result) == maxItems {
			break
		}
	}
	return result
}

func validRequirementType(value string) bool {
	if value == "" || len(value) > 96 {
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

func validPolicyRef(value string) bool {
	if value == "" || len(value) > 128 {
		return false
	}
	for _, current := range value {
		if unicode.IsLower(current) || unicode.IsDigit(current) || current == '_' || current == '.' {
			continue
		}
		return false
	}
	return strings.Contains(value, ".")
}

func normalizedStructuredKey(value string) string {
	var builder strings.Builder
	for _, current := range strings.ToLower(strings.TrimSpace(value)) {
		if unicode.IsLetter(current) || unicode.IsDigit(current) {
			builder.WriteRune(current)
		}
	}
	return builder.String()
}

func sortedDescriptorIDs(values map[string]VerifierDescriptor) []string {
	result := make([]string, 0, len(values))
	for value := range values {
		result = append(result, value)
	}
	sort.Strings(result)
	return result
}
