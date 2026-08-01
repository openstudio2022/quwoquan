package skillcontext

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
)

type Assembler struct {
	registry *ResolverRegistry
	consents ConsentReader
	now      func() time.Time
}

func NewAssembler(
	registry *ResolverRegistry,
	consents ...ConsentReader,
) *Assembler {
	if registry == nil {
		panic("assistant context resolver registry is required")
	}
	var consentReader ConsentReader
	if len(consents) > 0 {
		consentReader = consents[0]
	}
	return &Assembler{
		registry: registry,
		consents: consentReader,
		now:      time.Now,
	}
}

func (a *Assembler) Assemble(
	ctx context.Context,
	profile Profile,
	request AssembleRequest,
) (Snapshot, error) {
	if err := validateProfile(profile); err != nil {
		return Snapshot{}, err
	}
	if strings.TrimSpace(request.RunID) == "" || strings.TrimSpace(request.SkillID) == "" {
		return Snapshot{}, ErrInvalidProfile
	}
	capturedAt := a.now().UTC()
	snapshot := Snapshot{CapturedAt: capturedAt}
	for _, requirement := range profile.Requirements {
		if len(requirement.ConsentScopes) > 0 {
			allowed, reason := a.contextConsentAllowed(
				ctx,
				request,
				requirement,
			)
			if !allowed {
				observeContextResolution("consent_rejected", request.Visibility)
				observeContextPrivacyRejection(reason, request.Visibility)
				if requirement.Required {
					snapshot.Missing = append(
						snapshot.Missing,
						missing(requirement, reason),
					)
				}
				continue
			}
		}
		resolver, ok := a.registry.resolve(requirement.ResolverRef)
		if !ok {
			observeContextResolution("resolver_unavailable", request.Visibility)
			if requirement.Required {
				snapshot.Missing = append(snapshot.Missing, missing(requirement, "resolver unavailable"))
			}
			continue
		}
		resolved, err := resolver.Resolve(ctx, ResolveRequest{
			RunID:       request.RunID,
			SkillID:     request.SkillID,
			Requirement: requirement,
		})
		if err != nil {
			observeContextResolution("dependency_unavailable", request.Visibility)
			if requirement.Required {
				snapshot.Missing = append(snapshot.Missing, missing(requirement, err.Error()))
			}
			continue
		}
		segment, err := a.segment(requirement, request, resolved, capturedAt)
		if err != nil {
			observeContextResolution("policy_rejected", request.Visibility)
			observeContextPrivacyRejection(err.Error(), request.Visibility)
			if requirement.Required {
				snapshot.Missing = append(snapshot.Missing, missing(requirement, err.Error()))
			}
			continue
		}
		snapshot.TokenCost += segment.TokenCost
		snapshot.Segments = append(snapshot.Segments, segment)
		observeContextResolution("resolved", request.Visibility)
	}
	snapshot.SnapshotID = snapshotDigest(profile, request, snapshot)
	return snapshot, nil
}

func (a *Assembler) contextConsentAllowed(
	ctx context.Context,
	request AssembleRequest,
	requirement Requirement,
) (bool, string) {
	if a.consents == nil || strings.TrimSpace(request.OwnerID) == "" {
		return false, ErrConsentUnavailable.Error()
	}
	allowed, err := a.consents.AllowsContext(
		ctx,
		strings.TrimSpace(request.OwnerID),
		strings.TrimSpace(request.SkillID),
		append([]string(nil), requirement.ConsentScopes...),
	)
	if err != nil {
		return false, ErrConsentUnavailable.Error()
	}
	if !allowed {
		return false, "assistant context consent required"
	}
	return true, ""
}

func (a *Assembler) segment(
	requirement Requirement,
	request AssembleRequest,
	resolved ResolvedContext,
	now time.Time,
) (Segment, error) {
	if strings.TrimSpace(resolved.Kind) == "" || strings.TrimSpace(resolved.SourceRef) == "" {
		return Segment{}, ErrContextRejected
	}
	if !contains(requirement.AcceptedSourceKinds, resolved.Kind) || resolved.Authority != requirement.Authority {
		return Segment{}, ErrContextRejected
	}
	if resolved.CapturedAt.IsZero() || resolved.CapturedAt.After(now.Add(time.Minute)) {
		return Segment{}, ErrContextRejected
	}
	if requirement.Freshness > 0 && now.Sub(resolved.CapturedAt) > requirement.Freshness {
		return Segment{}, ErrContextRejected
	}
	if !resolved.ExpiresAt.IsZero() && !resolved.ExpiresAt.After(now) {
		return Segment{}, ErrContextRejected
	}
	if !sensitivityAllowed(resolved.Sensitivity, request.AllowedSensitivity) ||
		!deliveryAllows(request.Visibility, resolved.Kind, resolved.Sensitivity) {
		return Segment{}, ErrContextRejected
	}
	value := cloneValue(resolved.Value)
	tokenCost := resolved.TokenCost
	artifactRef := strings.TrimSpace(resolved.ArtifactRef)
	if requirement.TokenBudget > 0 && tokenCost > requirement.TokenBudget {
		if artifactRef == "" || strings.TrimSpace(resolved.Summary) == "" {
			return Segment{}, ErrContextRejected
		}
		value = map[string]any{
			"summary":     strings.TrimSpace(resolved.Summary),
			"artifactRef": artifactRef,
		}
		tokenCost = requirement.TokenBudget
	}
	digest, err := valueDigest(value)
	if err != nil {
		return Segment{}, ErrContextRejected
	}
	return Segment{
		SegmentID:   "ctx_" + digest[:24],
		SlotID:      requirement.SlotID,
		Kind:        resolved.Kind,
		SourceRef:   resolved.SourceRef,
		Authority:   resolved.Authority,
		Sensitivity: resolved.Sensitivity,
		CapturedAt:  resolved.CapturedAt.UTC(),
		ExpiresAt:   resolved.ExpiresAt.UTC(),
		Digest:      digest,
		TokenCost:   tokenCost,
		Value:       value,
		ArtifactRef: artifactRef,
	}, nil
}

func validateProfile(profile Profile) error {
	if strings.TrimSpace(profile.ProfileID) == "" || strings.TrimSpace(profile.AssetDigest) == "" {
		return ErrInvalidProfile
	}
	seen := map[string]struct{}{}
	for _, requirement := range profile.Requirements {
		if strings.TrimSpace(requirement.SlotID) == "" || strings.TrimSpace(requirement.ResolverRef) == "" ||
			requirement.Authority == "" || requirement.Sensitivity == "" ||
			len(requirement.AcceptedSourceKinds) == 0 || requirement.TokenBudget < 0 {
			return ErrInvalidProfile
		}
		consentScopes := map[string]struct{}{}
		for _, scope := range requirement.ConsentScopes {
			scope = strings.TrimSpace(scope)
			if scope == "" {
				return ErrInvalidProfile
			}
			if _, duplicate := consentScopes[scope]; duplicate {
				return ErrInvalidProfile
			}
			consentScopes[scope] = struct{}{}
		}
		if _, ok := seen[requirement.SlotID]; ok {
			return ErrInvalidProfile
		}
		seen[requirement.SlotID] = struct{}{}
	}
	return nil
}

func sensitivityAllowed(
	actual generated.AssistantContextSensitivity,
	maximum generated.AssistantContextSensitivity,
) bool {
	rank := map[generated.AssistantContextSensitivity]int{
		generated.AssistantContextSensitivityPublic:     1,
		generated.AssistantContextSensitivityInternal:   2,
		generated.AssistantContextSensitivityPrivate:    3,
		generated.AssistantContextSensitivityRestricted: 4,
	}
	return rank[actual] > 0 && rank[actual] <= rank[maximum]
}

func deliveryAllows(
	visibility DeliveryVisibility,
	kind string,
	sensitivity generated.AssistantContextSensitivity,
) bool {
	if visibility == DeliveryPersonal {
		return true
	}
	if kind == "memory" && (sensitivity == generated.AssistantContextSensitivityPrivate ||
		sensitivity == generated.AssistantContextSensitivityRestricted) {
		return false
	}
	if visibility == DeliveryPublic {
		return sensitivity == generated.AssistantContextSensitivityPublic
	}
	return sensitivity == generated.AssistantContextSensitivityPublic ||
		sensitivity == generated.AssistantContextSensitivityInternal
}

func missing(requirement Requirement, reason string) MissingRequirement {
	return MissingRequirement{
		SlotID:         requirement.SlotID,
		FallbackPolicy: requirement.FallbackPolicy,
		Reason:         reason,
	}
}

func contains(values []string, wanted string) bool {
	for _, value := range values {
		if value == wanted {
			return true
		}
	}
	return false
}

func valueDigest(value map[string]any) (string, error) {
	raw, err := json.Marshal(value)
	if err != nil {
		return "", err
	}
	digest := sha256.Sum256(raw)
	return hex.EncodeToString(digest[:]), nil
}

func snapshotDigest(profile Profile, request AssembleRequest, snapshot Snapshot) string {
	digests := make([]string, 0, len(snapshot.Segments))
	for _, segment := range snapshot.Segments {
		digests = append(digests, segment.Digest)
	}
	sort.Strings(digests)
	value := fmt.Sprintf("%s\x00%s\x00%s\x00%s", profile.AssetDigest, request.RunID, request.SkillID, strings.Join(digests, ","))
	digest := sha256.Sum256([]byte(value))
	return "snapshot_" + hex.EncodeToString(digest[:16])
}

func cloneValue(value map[string]any) map[string]any {
	result := make(map[string]any, len(value))
	for key, item := range value {
		result[key] = item
	}
	return result
}
