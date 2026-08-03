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
	ProfileID           string   `json:"profileId"`
	Mode                string   `json:"mode"`
	AllowedSurfaceKinds []string `json:"allowedSurfaceKinds,omitempty"`
	AssetDigest         string   `json:"assetDigest"`
}

type CatalogProfile struct {
	ProfileID        string   `json:"profileId"`
	IconToken        string   `json:"iconToken"`
	CoverMediaRef    string   `json:"coverMediaRef,omitempty"`
	TargetUsers      []string `json:"targetUsers"`
	ValueDescription string   `json:"valueDescription"`
	ExampleRefs      []string `json:"exampleRefs,omitempty"`
	DataUseSummary   string   `json:"dataUseSummary"`
	AssetDigest      string   `json:"assetDigest"`
}

type InputProfile struct {
	ProfileID              string   `json:"profileId"`
	ConfigurationSchemaRef string   `json:"configurationSchemaRef"`
	SetupTemplateRef       string   `json:"setupTemplateRef"`
	RequiredFields         []string `json:"requiredFields,omitempty"`
	AssetDigest            string   `json:"assetDigest"`
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

type OrchestrationProfile struct {
	ProfileID           string   `json:"profileId"`
	ReasoningProfile    string   `json:"reasoningProfile"`
	DefinitionOfDone    []string `json:"definitionOfDone"`
	SubagentRefs        []string `json:"subagentRefs,omitempty"`
	CheckpointPolicyRef string   `json:"checkpointPolicyRef"`
	StopRules           []string `json:"stopRules"`
	AssetDigest         string   `json:"assetDigest"`
}

type TriggerProfile struct {
	ProfileID                string   `json:"profileId"`
	TriggerKinds             []string `json:"triggerKinds"`
	DefaultDeliveryPolicyRef string   `json:"defaultDeliveryPolicyRef"`
	AssetDigest              string   `json:"assetDigest"`
}

type MemoryProfile struct {
	ProfileID            string   `json:"profileId"`
	ReadableKinds        []string `json:"readableKinds"`
	SuggestRememberKinds []string `json:"suggestRememberKinds"`
	ForbiddenKinds       []string `json:"forbiddenKinds"`
	AssetDigest          string   `json:"assetDigest"`
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
	CatalogProfiles       []CatalogProfile       `json:"catalogProfiles"`
	ActivationProfiles    []ActivationProfile    `json:"activationProfiles"`
	InputProfiles         []InputProfile         `json:"inputProfiles"`
	ContextProfiles       []ContextProfile       `json:"contextProfiles"`
	CapabilityProfiles    []CapabilityProfile    `json:"capabilityProfiles"`
	OrchestrationProfiles []OrchestrationProfile `json:"orchestrationProfiles"`
	TriggerProfiles       []TriggerProfile       `json:"triggerProfiles"`
	MemoryProfiles        []MemoryProfile        `json:"memoryProfiles"`
	PresentationProfiles  []PresentationProfile  `json:"presentationProfiles"`
	EvaluationProfiles    []EvaluationProfile    `json:"evaluationProfiles"`
}

func (catalog ProfileAssetCatalog) Validate() error {
	if err := validateAssetSet("catalog", catalog.CatalogProfiles, func(value CatalogProfile) string { return value.ProfileID }, catalogDigest); err != nil {
		return err
	}
	if err := validateAssetSet("activation", catalog.ActivationProfiles, func(value ActivationProfile) string { return value.ProfileID }, activationDigest); err != nil {
		return err
	}
	if err := validateAssetSet("input", catalog.InputProfiles, func(value InputProfile) string { return value.ProfileID }, inputDigest); err != nil {
		return err
	}
	for _, value := range catalog.ActivationProfiles {
		if value.Mode != ActivationReactive &&
			value.Mode != ActivationProactive &&
			value.Mode != ActivationHybrid {
			return fmt.Errorf("activation profile %q has invalid mode %q", value.ProfileID, value.Mode)
		}
		if err := validateAllowedSurfaceKinds(value.ProfileID, value.AllowedSurfaceKinds); err != nil {
			return err
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
	if err := validateAssetSet("orchestration", catalog.OrchestrationProfiles, func(value OrchestrationProfile) string { return value.ProfileID }, orchestrationDigest); err != nil {
		return err
	}
	if err := validateAssetSet("trigger", catalog.TriggerProfiles, func(value TriggerProfile) string { return value.ProfileID }, triggerDigest); err != nil {
		return err
	}
	if err := validateAssetSet("memory", catalog.MemoryProfiles, func(value MemoryProfile) string { return value.ProfileID }, memoryDigest); err != nil {
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
	catalogProfile, err := resolveAsset(manifest.CatalogProfileRef, catalog.CatalogProfiles, func(value CatalogProfile) string { return value.ProfileID }, catalogDigest)
	if err != nil {
		return Manifest{}, fmt.Errorf("catalog profile: %w", err)
	}
	activation, err := resolveAsset(manifest.ActivationProfileRef, catalog.ActivationProfiles, func(value ActivationProfile) string { return value.ProfileID }, activationDigest)
	if err != nil {
		return Manifest{}, fmt.Errorf("activation profile: %w", err)
	}
	inputProfile, err := resolveAsset(manifest.InputProfileRef, catalog.InputProfiles, func(value InputProfile) string { return value.ProfileID }, inputDigest)
	if err != nil {
		return Manifest{}, fmt.Errorf("input profile: %w", err)
	}
	contextProfile, err := resolveAsset(manifest.ContextProfileRef, catalog.ContextProfiles, func(value ContextProfile) string { return value.ProfileID }, contextDigest)
	if err != nil {
		return Manifest{}, fmt.Errorf("context profile: %w", err)
	}
	capability, err := resolveAsset(manifest.CapabilityProfileRef, catalog.CapabilityProfiles, func(value CapabilityProfile) string { return value.ProfileID }, capabilityDigest)
	if err != nil {
		return Manifest{}, fmt.Errorf("capability profile: %w", err)
	}
	orchestration, err := resolveAsset(manifest.OrchestrationProfileRef, catalog.OrchestrationProfiles, func(value OrchestrationProfile) string { return value.ProfileID }, orchestrationDigest)
	if err != nil {
		return Manifest{}, fmt.Errorf("orchestration profile: %w", err)
	}
	trigger, err := resolveAsset(manifest.TriggerProfileRef, catalog.TriggerProfiles, func(value TriggerProfile) string { return value.ProfileID }, triggerDigest)
	if err != nil {
		return Manifest{}, fmt.Errorf("trigger profile: %w", err)
	}
	memoryProfile, err := resolveAsset(manifest.MemoryProfileRef, catalog.MemoryProfiles, func(value MemoryProfile) string { return value.ProfileID }, memoryDigest)
	if err != nil {
		return Manifest{}, fmt.Errorf("memory profile: %w", err)
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
	manifest.ActivationProfile = activation
	manifest.SlotSchema = contextProfile.SlotSchema
	manifest.ToolPolicy = capability.ToolPolicy
	manifest.IconHint = presentation.IconToken
	manifest.CatalogProfile = catalogProfile
	manifest.InputProfile = inputProfile
	manifest.ContextProfile = contextProfile
	manifest.Orchestration = orchestration
	manifest.Trigger = trigger
	manifest.Memory = memoryProfile
	manifest.Presentation = presentation
	manifest.Evaluation = evaluation
	manifest.ResolvedAssetRefs = map[string]AssetProof{
		"catalog":       {ProfileID: catalogProfile.ProfileID, AssetDigest: catalogProfile.AssetDigest},
		"activation":    {ProfileID: activation.ProfileID, AssetDigest: activation.AssetDigest},
		"input":         {ProfileID: inputProfile.ProfileID, AssetDigest: inputProfile.AssetDigest},
		"context":       {ProfileID: contextProfile.ProfileID, AssetDigest: contextProfile.AssetDigest},
		"capability":    {ProfileID: capability.ProfileID, AssetDigest: capability.AssetDigest},
		"orchestration": {ProfileID: orchestration.ProfileID, AssetDigest: orchestration.AssetDigest},
		"trigger":       {ProfileID: trigger.ProfileID, AssetDigest: trigger.AssetDigest},
		"memory":        {ProfileID: memoryProfile.ProfileID, AssetDigest: memoryProfile.AssetDigest},
		"presentation":  {ProfileID: presentation.ProfileID, AssetDigest: presentation.AssetDigest},
		"evaluation":    {ProfileID: evaluation.ProfileID, AssetDigest: evaluation.AssetDigest},
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
		ProfileID           string   `json:"profileId"`
		Mode                string   `json:"mode"`
		AllowedSurfaceKinds []string `json:"allowedSurfaceKinds,omitempty"`
	}{value.ProfileID, value.Mode, value.AllowedSurfaceKinds})
}

func validateAllowedSurfaceKinds(profileID string, values []string) error {
	// Existing personal-only profiles omit the field. Shared eligibility must
	// always be explicit and therefore cannot be inferred from mode.
	if len(values) == 0 {
		return nil
	}
	if len(values) > 3 {
		return fmt.Errorf("activation profile %q has invalid surface kinds", profileID)
	}
	seen := map[string]struct{}{}
	for _, value := range values {
		if value != "personal" && value != "conversation" && value != "circle" {
			return fmt.Errorf("activation profile %q has invalid surface kind %q", profileID, value)
		}
		if _, duplicate := seen[value]; duplicate {
			return fmt.Errorf("activation profile %q has duplicate surface kind %q", profileID, value)
		}
		seen[value] = struct{}{}
	}
	if _, personal := seen["personal"]; !personal {
		return fmt.Errorf("activation profile %q must allow personal surface", profileID)
	}
	return nil
}

func catalogDigest(value CatalogProfile) (string, string, error) {
	return assetDigest(value.AssetDigest, struct {
		ProfileID        string   `json:"profileId"`
		IconToken        string   `json:"iconToken"`
		CoverMediaRef    string   `json:"coverMediaRef,omitempty"`
		TargetUsers      []string `json:"targetUsers"`
		ValueDescription string   `json:"valueDescription"`
		ExampleRefs      []string `json:"exampleRefs,omitempty"`
		DataUseSummary   string   `json:"dataUseSummary"`
	}{value.ProfileID, value.IconToken, value.CoverMediaRef, value.TargetUsers, value.ValueDescription, value.ExampleRefs, value.DataUseSummary})
}

func inputDigest(value InputProfile) (string, string, error) {
	return assetDigest(value.AssetDigest, struct {
		ProfileID              string   `json:"profileId"`
		ConfigurationSchemaRef string   `json:"configurationSchemaRef"`
		SetupTemplateRef       string   `json:"setupTemplateRef"`
		RequiredFields         []string `json:"requiredFields,omitempty"`
	}{value.ProfileID, value.ConfigurationSchemaRef, value.SetupTemplateRef, value.RequiredFields})
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

func orchestrationDigest(value OrchestrationProfile) (string, string, error) {
	return assetDigest(value.AssetDigest, struct {
		ProfileID           string   `json:"profileId"`
		ReasoningProfile    string   `json:"reasoningProfile"`
		DefinitionOfDone    []string `json:"definitionOfDone"`
		SubagentRefs        []string `json:"subagentRefs,omitempty"`
		CheckpointPolicyRef string   `json:"checkpointPolicyRef"`
		StopRules           []string `json:"stopRules"`
	}{value.ProfileID, value.ReasoningProfile, value.DefinitionOfDone, value.SubagentRefs, value.CheckpointPolicyRef, value.StopRules})
}

func triggerDigest(value TriggerProfile) (string, string, error) {
	return assetDigest(value.AssetDigest, struct {
		ProfileID                string   `json:"profileId"`
		TriggerKinds             []string `json:"triggerKinds"`
		DefaultDeliveryPolicyRef string   `json:"defaultDeliveryPolicyRef"`
	}{value.ProfileID, value.TriggerKinds, value.DefaultDeliveryPolicyRef})
}

func memoryDigest(value MemoryProfile) (string, string, error) {
	return assetDigest(value.AssetDigest, struct {
		ProfileID            string   `json:"profileId"`
		ReadableKinds        []string `json:"readableKinds"`
		SuggestRememberKinds []string `json:"suggestRememberKinds"`
		ForbiddenKinds       []string `json:"forbiddenKinds"`
	}{value.ProfileID, value.ReadableKinds, value.SuggestRememberKinds, value.ForbiddenKinds})
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
