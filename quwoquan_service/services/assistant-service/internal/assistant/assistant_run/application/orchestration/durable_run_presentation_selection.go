package orchestration

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"sort"
	"strings"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	presentationpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/presentation"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/runruntime"
	skillcontext "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/skillcontext"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
)

const (
	presentationGroundingEnvelope = "presentation"
	presentationGroundedActions   = "actions"
	presentationGroundedMedia     = "media"
)

type resolvedPresentationCandidate struct {
	CandidateID string
	Template    presentationpkg.Template
	Data        map[string]any
	Document    presentationpkg.Document
}

// selectPresentationCandidate gives the model autonomy only over a bounded,
// server-resolved candidate set. The model never writes presentation data,
// nodes, actions, media or template references: candidateId is mapped back to
// an immutable, already validated Selection owned by the active Skill release.
func (e *DurableRunExecutor) selectPresentationCandidate(
	ctx context.Context,
	request runruntime.ExecutionRequest,
	prepared PreparedExecution,
	candidates []resolvedPresentationCandidate,
	capabilities presentationpkg.SurfaceCapabilities,
) (resolvedPresentationCandidate, bool, error) {
	if e == nil || e.loop == nil || e.loop.React.Model == nil || len(candidates) < 2 {
		return resolvedPresentationCandidate{}, false, nil
	}
	response, err := e.loop.React.Model.Complete(ctx, ModelRequest{
		TurnID:           request.RunID,
		TraceID:          request.RequestContext.TraceID,
		SkillID:          prepared.SkillID,
		SearchIntensity:  request.FrozenPolicySelection.Template.SearchIntensity,
		ProblemClass:     generated.ProblemClassGeneral.WireName(),
		ReasoningProfile: request.ReasoningProfile,
		Stage:            string(ports.ModelStagePresentation),
		UserQuestion:     request.Goal,
		Observation: presentationSelectionObservation(
			candidates,
			capabilities,
		),
	})
	if err != nil {
		return resolvedPresentationCandidate{}, false, nil
	}
	if err := consumeExecutionModelResponse(ctx, response); err != nil {
		return resolvedPresentationCandidate{}, false, err
	}
	candidateID, _ := response.StructuredDelta["candidateId"].(string)
	candidateID = strings.TrimSpace(candidateID)
	for _, candidate := range candidates {
		if candidate.CandidateID == candidateID {
			return candidate, true, nil
		}
	}
	return resolvedPresentationCandidate{}, false, nil
}

func presentationSelectionObservation(
	candidates []resolvedPresentationCandidate,
	capabilities presentationpkg.SurfaceCapabilities,
) map[string]any {
	values := make([]any, 0, len(candidates))
	for _, candidate := range candidates {
		nodeKinds := make([]string, 0, len(candidate.Template.Nodes))
		seenKinds := map[string]bool{}
		hasAction := false
		hasMedia := false
		for _, node := range candidate.Template.Nodes {
			kind := node.Kind.WireName()
			if !seenKinds[kind] {
				seenKinds[kind] = true
				nodeKinds = append(nodeKinds, kind)
			}
			hasAction = hasAction || node.Action != nil || node.Binding["action"] != ""
			hasMedia = hasMedia || node.Media != nil || node.Binding["media"] != ""
		}
		sort.Strings(nodeKinds)
		dataFields := make([]string, 0, len(candidate.Data))
		for field := range candidate.Data {
			dataFields = append(dataFields, field)
		}
		sort.Strings(dataFields)
		values = append(values, map[string]any{
			"candidateId": candidate.CandidateID,
			"templateId":  candidate.Template.TemplateID,
			"nodeKinds":   nodeKinds,
			"dataFields":  dataFields,
			"dataDigest":  candidate.Document.DataDigest,
			"hasAction":   hasAction,
			"hasMedia":    hasMedia,
		})
	}
	supportedKinds := make([]string, 0, len(capabilities.SupportedNodeKinds))
	for kind, supported := range capabilities.SupportedNodeKinds {
		if supported {
			supportedKinds = append(supportedKinds, kind.WireName())
		}
	}
	sort.Strings(supportedKinds)
	supportedActions := make([]string, 0, len(capabilities.SupportedActionIntents))
	for operation, supported := range capabilities.SupportedActionIntents {
		if supported {
			supportedActions = append(supportedActions, operation)
		}
	}
	sort.Strings(supportedActions)
	return map[string]any{
		"candidates": values,
		"surface": map[string]any{
			"viewportClass":          capabilities.ViewportClass,
			"density":                capabilities.Density.WireName(),
			"supportedNodeKinds":     supportedKinds,
			"supportedActionIntents": supportedActions,
		},
	}
}

func deterministicPresentationCandidate(
	candidates []resolvedPresentationCandidate,
) resolvedPresentationCandidate {
	ordered := append([]resolvedPresentationCandidate(nil), candidates...)
	sort.SliceStable(ordered, func(left, right int) bool {
		leftDefault := ordered[left].Template.TemplateID == "assistant.answer.default"
		rightDefault := ordered[right].Template.TemplateID == "assistant.answer.default"
		if leftDefault != rightDefault {
			return leftDefault
		}
		leftRisk := presentationCandidateRisk(ordered[left].Template)
		rightRisk := presentationCandidateRisk(ordered[right].Template)
		if leftRisk != rightRisk {
			return leftRisk < rightRisk
		}
		if len(ordered[left].Template.Nodes) != len(ordered[right].Template.Nodes) {
			return len(ordered[left].Template.Nodes) < len(ordered[right].Template.Nodes)
		}
		return ordered[left].CandidateID < ordered[right].CandidateID
	})
	return ordered[0]
}

func presentationCandidateRisk(template presentationpkg.Template) int {
	risk := 0
	for _, node := range template.Nodes {
		if node.Action != nil || node.Binding["action"] != "" {
			risk += 2
		}
		if node.Media != nil || node.Binding["media"] != "" {
			risk++
		}
	}
	return risk
}

// groundedPresentationPolicy is the runtime intersection between a signed
// Skill template, authoritative Context and the current App surface. Only
// action/media envelopes emitted by a domain-canonical Reader are eligible.
type groundedPresentationPolicy struct {
	actionDigests    map[string]struct{}
	mediaDigests     map[string]struct{}
	supportedActions map[string]bool
}

func newGroundedPresentationPolicy(
	snapshot *skillcontext.Snapshot,
	capabilities presentationpkg.SurfaceCapabilities,
) groundedPresentationPolicy {
	policy := groundedPresentationPolicy{
		actionDigests:    map[string]struct{}{},
		mediaDigests:     map[string]struct{}{},
		supportedActions: capabilities.SupportedActionIntents,
	}
	if snapshot == nil {
		return policy
	}
	for _, segment := range snapshot.Segments {
		if segment.Authority != generated.AssistantContextAuthorityDomainCanonical {
			continue
		}
		envelope := objectMap(segment.Value[presentationGroundingEnvelope])
		for _, raw := range anyList(envelope[presentationGroundedActions]) {
			action, ok := decodeGroundedValue[presentationpkg.ActionIntent](raw)
			if !ok {
				continue
			}
			if digest, ok := presentationGroundingDigest(action); ok {
				policy.actionDigests[digest] = struct{}{}
			}
		}
		for _, raw := range anyList(envelope[presentationGroundedMedia]) {
			media, ok := decodeGroundedValue[presentationpkg.MediaRef](raw)
			if !ok {
				continue
			}
			if digest, ok := presentationGroundingDigest(media); ok {
				policy.mediaDigests[digest] = struct{}{}
			}
		}
	}
	return policy
}

func (policy groundedPresentationPolicy) ValidateAction(
	_ context.Context,
	_ string,
	action presentationpkg.ActionIntent,
) error {
	if !policy.supportedActions[string(action.Kind)] {
		return presentationpkg.ErrActionRejected
	}
	digest, ok := presentationGroundingDigest(action)
	if !ok {
		return presentationpkg.ErrActionRejected
	}
	if _, grounded := policy.actionDigests[digest]; !grounded {
		return presentationpkg.ErrActionRejected
	}
	return nil
}

func (policy groundedPresentationPolicy) ValidateMedia(
	_ context.Context,
	media presentationpkg.MediaRef,
) error {
	digest, ok := presentationGroundingDigest(media)
	if !ok {
		return presentationpkg.ErrMediaRejected
	}
	if _, grounded := policy.mediaDigests[digest]; !grounded {
		return presentationpkg.ErrMediaRejected
	}
	return nil
}

func decodeGroundedValue[T any](value any) (T, bool) {
	var decoded T
	raw, err := json.Marshal(value)
	if err != nil {
		return decoded, false
	}
	decoder := json.NewDecoder(strings.NewReader(string(raw)))
	decoder.DisallowUnknownFields()
	decoder.UseNumber()
	if err := decoder.Decode(&decoded); err != nil {
		return decoded, false
	}
	if err := decoder.Decode(&struct{}{}); err != io.EOF {
		return decoded, false
	}
	return decoded, true
}

func presentationGroundingDigest(value any) (string, bool) {
	raw, err := json.Marshal(value)
	if err != nil {
		return "", false
	}
	sum := sha256.Sum256(raw)
	return "sha256:" + hex.EncodeToString(sum[:]), true
}
