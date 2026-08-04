package skill

import (
	"fmt"
	"strings"
)

const (
	CatalogVisibilityListed = "listed"
	CatalogVisibilityHidden = "hidden"
)

// CatalogSemanticLabel is package-owned presentation metadata. Stable IDs are
// used for policy and analytics; display text is immutable release content so
// App surfaces do not grow vertical-specific switch statements.
type CatalogSemanticLabel struct {
	ID          string `json:"id"`
	DisplayText string `json:"displayText"`
	Description string `json:"description,omitempty"`
}

// CatalogExample is a safe, immutable Skill outcome preview. TemplateRef is a
// template ID declared by the same resolved PresentationProfile. Runtime code
// resolves it to the digest-qualified template reference before exposing it.
type CatalogExample struct {
	ExampleID   string `json:"exampleId"`
	Title       string `json:"title"`
	Summary     string `json:"summary"`
	IconToken   string `json:"iconToken,omitempty"`
	MediaRef    string `json:"mediaRef,omitempty"`
	TemplateRef string `json:"templateRef"`
}

type CatalogProfile struct {
	ProfileID        string                 `json:"profileId"`
	Visibility       string                 `json:"visibility"`
	IconToken        string                 `json:"iconToken"`
	CoverMediaRef    string                 `json:"coverMediaRef,omitempty"`
	CatalogGroup     CatalogSemanticLabel   `json:"catalogGroup,omitempty"`
	TargetAudiences  []CatalogSemanticLabel `json:"targetAudiences,omitempty"`
	SurfaceKinds     []CatalogSemanticLabel `json:"surfaceKinds,omitempty"`
	ConsentScopes    []CatalogSemanticLabel `json:"consentScopes,omitempty"`
	ValueDescription string                 `json:"valueDescription"`
	Examples         []CatalogExample       `json:"examples,omitempty"`
	DataUseSummary   string                 `json:"dataUseSummary"`
	AssetDigest      string                 `json:"assetDigest"`
}

func catalogDigest(value CatalogProfile) (string, string, error) {
	return assetDigest(value.AssetDigest, struct {
		ProfileID        string                 `json:"profileId"`
		Visibility       string                 `json:"visibility"`
		IconToken        string                 `json:"iconToken"`
		CoverMediaRef    string                 `json:"coverMediaRef,omitempty"`
		CatalogGroup     CatalogSemanticLabel   `json:"catalogGroup,omitempty"`
		TargetAudiences  []CatalogSemanticLabel `json:"targetAudiences,omitempty"`
		SurfaceKinds     []CatalogSemanticLabel `json:"surfaceKinds,omitempty"`
		ConsentScopes    []CatalogSemanticLabel `json:"consentScopes,omitempty"`
		ValueDescription string                 `json:"valueDescription"`
		Examples         []CatalogExample       `json:"examples,omitempty"`
		DataUseSummary   string                 `json:"dataUseSummary"`
	}{
		value.ProfileID,
		value.Visibility,
		value.IconToken,
		value.CoverMediaRef,
		value.CatalogGroup,
		value.TargetAudiences,
		value.SurfaceKinds,
		value.ConsentScopes,
		value.ValueDescription,
		value.Examples,
		value.DataUseSummary,
	})
}

func validateCatalogProfile(value CatalogProfile) error {
	profileID := strings.TrimSpace(value.ProfileID)
	visibility := strings.TrimSpace(value.Visibility)
	if visibility != CatalogVisibilityListed && visibility != CatalogVisibilityHidden {
		return fmt.Errorf("catalog profile %q has invalid visibility %q", profileID, visibility)
	}
	if strings.TrimSpace(value.IconToken) == "" ||
		strings.TrimSpace(value.ValueDescription) == "" ||
		strings.TrimSpace(value.DataUseSummary) == "" {
		return fmt.Errorf("catalog profile %q has incomplete display metadata", profileID)
	}
	// Catalog media must eventually carry a canonical MediaAssetRef together
	// with immutable dimensions, alt text, provenance and rights proof. Until
	// that package asset exists, accepting an unverified string would create a
	// phantom cover that can fail or leak at render time.
	if strings.TrimSpace(value.CoverMediaRef) != "" {
		return fmt.Errorf(
			"catalog profile %q cover media has no immutable media proof",
			profileID,
		)
	}
	if visibility == CatalogVisibilityHidden {
		if strings.TrimSpace(value.CatalogGroup.ID) != "" ||
			len(value.TargetAudiences) != 0 || len(value.SurfaceKinds) != 0 ||
			len(value.ConsentScopes) != 0 || len(value.Examples) != 0 {
			return fmt.Errorf("hidden catalog profile %q exposes listing metadata", profileID)
		}
		return nil
	}
	if err := validateCatalogSemanticLabel(profileID, "catalogGroup", value.CatalogGroup); err != nil {
		return err
	}
	if err := validateCatalogSemanticLabels(profileID, "targetAudiences", value.TargetAudiences, true); err != nil {
		return err
	}
	if err := validateCatalogSemanticLabels(profileID, "surfaceKinds", value.SurfaceKinds, true); err != nil {
		return err
	}
	if err := validateCatalogSemanticLabels(profileID, "consentScopes", value.ConsentScopes, false); err != nil {
		return err
	}
	if len(value.Examples) == 0 {
		return fmt.Errorf("listed catalog profile %q has no resolved examples", profileID)
	}
	seenExamples := make(map[string]struct{}, len(value.Examples))
	for _, example := range value.Examples {
		exampleID := strings.TrimSpace(example.ExampleID)
		if exampleID == "" || strings.TrimSpace(example.Title) == "" ||
			strings.TrimSpace(example.Summary) == "" || strings.TrimSpace(example.TemplateRef) == "" {
			return fmt.Errorf("catalog profile %q has invalid example %q", profileID, exampleID)
		}
		if strings.TrimSpace(example.MediaRef) != "" {
			return fmt.Errorf(
				"catalog profile %q example %q media has no immutable media proof",
				profileID,
				exampleID,
			)
		}
		if _, duplicate := seenExamples[exampleID]; duplicate {
			return fmt.Errorf("catalog profile %q has duplicate example %q", profileID, exampleID)
		}
		seenExamples[exampleID] = struct{}{}
	}
	return nil
}

func validateCatalogSemanticLabels(
	profileID string,
	field string,
	values []CatalogSemanticLabel,
	required bool,
) error {
	if required && len(values) == 0 {
		return fmt.Errorf("catalog profile %q has no %s", profileID, field)
	}
	seen := make(map[string]struct{}, len(values))
	for _, value := range values {
		if err := validateCatalogSemanticLabel(profileID, field, value); err != nil {
			return err
		}
		id := strings.TrimSpace(value.ID)
		if _, duplicate := seen[id]; duplicate {
			return fmt.Errorf("catalog profile %q has duplicate %s id %q", profileID, field, id)
		}
		seen[id] = struct{}{}
	}
	return nil
}

func validateCatalogSemanticLabel(
	profileID string,
	field string,
	value CatalogSemanticLabel,
) error {
	if strings.TrimSpace(value.ID) == "" || strings.TrimSpace(value.DisplayText) == "" {
		return fmt.Errorf("catalog profile %q has invalid %s semantic label", profileID, field)
	}
	return nil
}
