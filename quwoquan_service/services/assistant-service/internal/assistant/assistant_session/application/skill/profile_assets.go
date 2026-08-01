package skill

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"strings"
)

type AssetProof struct {
	ProfileID   string `json:"profileId"`
	AssetDigest string `json:"assetDigest"`
}

type ActivationProfile struct {
	ProfileID   string `json:"profileId"`
	Mode        string `json:"mode"`
	AssetDigest string `json:"assetDigest"`
}

type ContextRequirement struct {
	SlotID              string   `json:"slotId"`
	Required            bool     `json:"required,omitempty"`
	AcceptedSourceKinds []string `json:"acceptedSourceKinds"`
	Authority           string   `json:"authority"`
	Sensitivity         string   `json:"sensitivity"`
	ConsentScopes       []string `json:"consentScopes,omitempty"`
	FreshnessSeconds    int      `json:"freshnessSeconds,omitempty"`
	TokenBudget         int      `json:"tokenBudget,omitempty"`
	ResolverRef         string   `json:"resolverRef"`
	FallbackPolicy      string   `json:"fallbackPolicy,omitempty"`
}

type ContextProfile struct {
	ProfileID    string               `json:"profileId"`
	SlotSchema   SlotSchema           `json:"slotSchema,omitempty"`
	Requirements []ContextRequirement `json:"requirements"`
	AssetDigest  string               `json:"assetDigest"`
}

type CapabilityProfile struct {
	ProfileID   string     `json:"profileId"`
	ToolPolicy  ToolPolicy `json:"toolPolicy"`
	AssetDigest string     `json:"assetDigest"`
}

type PresentationProfile struct {
	ProfileID    string   `json:"profileId"`
	IconToken    string   `json:"iconToken"`
	TemplateRefs []string `json:"templateRefs"`
	AssetDigest  string   `json:"assetDigest"`
}

type EvaluationProfile struct {
	ProfileID   string   `json:"profileId"`
	FixtureRefs []string `json:"fixtureRefs"`
	AssetDigest string   `json:"assetDigest"`
}

type ProfileAssetCatalog struct {
	ActivationProfiles   []ActivationProfile   `json:"activationProfiles"`
	ContextProfiles      []ContextProfile      `json:"contextProfiles"`
	CapabilityProfiles   []CapabilityProfile   `json:"capabilityProfiles"`
	PresentationProfiles []PresentationProfile `json:"presentationProfiles"`
	EvaluationProfiles   []EvaluationProfile   `json:"evaluationProfiles"`
}

func (catalog ProfileAssetCatalog) Validate() error {
	if err := validateAssetSet("activation", catalog.ActivationProfiles, func(value ActivationProfile) string { return value.ProfileID }, activationDigest); err != nil {
		return err
	}
	for _, value := range catalog.ActivationProfiles {
		if value.Mode != ActivationReactive && value.Mode != ActivationProactive {
			return fmt.Errorf("activation profile %q has invalid mode %q", value.ProfileID, value.Mode)
		}
	}
	if err := validateAssetSet("context", catalog.ContextProfiles, func(value ContextProfile) string { return value.ProfileID }, contextDigest); err != nil {
		return err
	}
	for _, value := range catalog.ContextProfiles {
		seen := map[string]struct{}{}
		for _, requirement := range value.Requirements {
			slotID := strings.TrimSpace(requirement.SlotID)
			if slotID == "" || strings.TrimSpace(requirement.ResolverRef) == "" ||
				strings.TrimSpace(requirement.Authority) == "" || strings.TrimSpace(requirement.Sensitivity) == "" ||
				len(requirement.AcceptedSourceKinds) == 0 || requirement.FreshnessSeconds < 0 || requirement.TokenBudget < 0 {
				return fmt.Errorf("context profile %q has invalid requirement %q", value.ProfileID, slotID)
			}
			consentScopes := map[string]struct{}{}
			for _, scope := range requirement.ConsentScopes {
				scope = strings.TrimSpace(scope)
				if scope == "" {
					return fmt.Errorf("context profile %q has blank consent scope", value.ProfileID)
				}
				if _, duplicate := consentScopes[scope]; duplicate {
					return fmt.Errorf("context profile %q has duplicate consent scope %q", value.ProfileID, scope)
				}
				consentScopes[scope] = struct{}{}
			}
			if _, exists := seen[slotID]; exists {
				return fmt.Errorf("context profile %q has duplicate requirement %q", value.ProfileID, slotID)
			}
			seen[slotID] = struct{}{}
		}
	}
	if err := validateAssetSet("capability", catalog.CapabilityProfiles, func(value CapabilityProfile) string { return value.ProfileID }, capabilityDigest); err != nil {
		return err
	}
	if err := validateAssetSet("presentation", catalog.PresentationProfiles, func(value PresentationProfile) string { return value.ProfileID }, presentationDigest); err != nil {
		return err
	}
	if err := validateAssetSet("evaluation", catalog.EvaluationProfiles, func(value EvaluationProfile) string { return value.ProfileID }, evaluationDigest); err != nil {
		return err
	}
	return nil
}

func validateAssetSet[T any](kind string, values []T, id func(T) string, digest func(T) (string, string, error)) error {
	if len(values) == 0 {
		return fmt.Errorf("%s profile assets are empty", kind)
	}
	seen := map[string]struct{}{}
	for _, value := range values {
		profileID := strings.TrimSpace(id(value))
		if profileID == "" {
			return fmt.Errorf("%s profile id is required", kind)
		}
		if _, exists := seen[profileID]; exists {
			return fmt.Errorf("duplicate %s profile %q", kind, profileID)
		}
		seen[profileID] = struct{}{}
		declared, actual, err := digest(value)
		if err != nil {
			return err
		}
		if declared != actual {
			return fmt.Errorf("%s profile %q digest mismatch: declared %s actual %s", kind, profileID, declared, actual)
		}
	}
	return nil
}

// ResolveManifest verifies every immutable profile before exposing its values
// to the runtime. Profile refs are exact canonical IDs; aliases and fallback
// reads are deliberately unsupported.
func (catalog ProfileAssetCatalog) ResolveManifest(manifest Manifest) (Manifest, error) {
	activation, err := resolveAsset(manifest.ActivationProfileRef, catalog.ActivationProfiles, func(value ActivationProfile) string { return value.ProfileID }, activationDigest)
	if err != nil {
		return Manifest{}, fmt.Errorf("activation profile: %w", err)
	}
	contextProfile, err := resolveAsset(manifest.ContextProfileRef, catalog.ContextProfiles, func(value ContextProfile) string { return value.ProfileID }, contextDigest)
	if err != nil {
		return Manifest{}, fmt.Errorf("context profile: %w", err)
	}
	capability, err := resolveAsset(manifest.CapabilityProfileRef, catalog.CapabilityProfiles, func(value CapabilityProfile) string { return value.ProfileID }, capabilityDigest)
	if err != nil {
		return Manifest{}, fmt.Errorf("capability profile: %w", err)
	}
	presentation, err := resolveAsset(manifest.PresentationProfileRef, catalog.PresentationProfiles, func(value PresentationProfile) string { return value.ProfileID }, presentationDigest)
	if err != nil {
		return Manifest{}, fmt.Errorf("presentation profile: %w", err)
	}
	evaluation, err := resolveAsset(manifest.EvaluationProfileRef, catalog.EvaluationProfiles, func(value EvaluationProfile) string { return value.ProfileID }, evaluationDigest)
	if err != nil {
		return Manifest{}, fmt.Errorf("evaluation profile: %w", err)
	}
	manifest.Activation = activation.Mode
	manifest.SlotSchema = contextProfile.SlotSchema
	manifest.ToolPolicy = capability.ToolPolicy
	manifest.IconHint = presentation.IconToken
	manifest.ContextProfile = contextProfile
	manifest.Presentation = presentation
	manifest.Evaluation = evaluation
	manifest.ResolvedAssetRefs = map[string]AssetProof{
		"activation":   {ProfileID: activation.ProfileID, AssetDigest: activation.AssetDigest},
		"context":      {ProfileID: contextProfile.ProfileID, AssetDigest: contextProfile.AssetDigest},
		"capability":   {ProfileID: capability.ProfileID, AssetDigest: capability.AssetDigest},
		"presentation": {ProfileID: presentation.ProfileID, AssetDigest: presentation.AssetDigest},
		"evaluation":   {ProfileID: evaluation.ProfileID, AssetDigest: evaluation.AssetDigest},
	}
	return manifest, nil
}

func resolveAsset[T any](ref string, values []T, id func(T) string, digest func(T) (string, string, error)) (T, error) {
	var zero T
	ref = strings.TrimSpace(ref)
	if ref == "" {
		return zero, fmt.Errorf("profile ref is required")
	}
	for _, value := range values {
		if strings.TrimSpace(id(value)) != ref {
			continue
		}
		declared, actual, err := digest(value)
		if err != nil {
			return zero, err
		}
		if declared != actual {
			return zero, fmt.Errorf("profile %q digest mismatch: declared %s actual %s", ref, declared, actual)
		}
		return value, nil
	}
	return zero, fmt.Errorf("profile %q is missing", ref)
}

func activationDigest(value ActivationProfile) (string, string, error) {
	return assetDigest(value.AssetDigest, struct {
		ProfileID string `json:"profileId"`
		Mode      string `json:"mode"`
	}{value.ProfileID, value.Mode})
}

func contextDigest(value ContextProfile) (string, string, error) {
	return assetDigest(value.AssetDigest, struct {
		ProfileID    string               `json:"profileId"`
		SlotSchema   SlotSchema           `json:"slotSchema,omitempty"`
		Requirements []ContextRequirement `json:"requirements"`
	}{value.ProfileID, value.SlotSchema, value.Requirements})
}

func capabilityDigest(value CapabilityProfile) (string, string, error) {
	return assetDigest(value.AssetDigest, struct {
		ProfileID  string     `json:"profileId"`
		ToolPolicy ToolPolicy `json:"toolPolicy"`
	}{value.ProfileID, value.ToolPolicy})
}

func presentationDigest(value PresentationProfile) (string, string, error) {
	return assetDigest(value.AssetDigest, struct {
		ProfileID    string   `json:"profileId"`
		IconToken    string   `json:"iconToken"`
		TemplateRefs []string `json:"templateRefs"`
	}{value.ProfileID, value.IconToken, value.TemplateRefs})
}

func evaluationDigest(value EvaluationProfile) (string, string, error) {
	return assetDigest(value.AssetDigest, struct {
		ProfileID   string   `json:"profileId"`
		FixtureRefs []string `json:"fixtureRefs"`
	}{value.ProfileID, value.FixtureRefs})
}

func assetDigest(declared string, payload any) (string, string, error) {
	raw, err := json.Marshal(payload)
	if err != nil {
		return "", "", err
	}
	digest := sha256.Sum256(raw)
	return strings.TrimSpace(declared), "sha256:" + hex.EncodeToString(digest[:]), nil
}
