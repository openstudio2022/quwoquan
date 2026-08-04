// Package catalogprojection turns one digest-verified Skill manifest into the
// public catalog view. It is shared by the build-time verifier and the active
// release runtime so listing eligibility and semantic metadata cannot drift.
package catalogprojection

import (
	"encoding/json"
	"fmt"
	"sort"
	"strings"

	presentation "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/presentation"
	catalogapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/application"
	catalogmodel "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/domain/model"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
)

type TemplateLoader func(skillID string, templateID string) ([]byte, bool, error)

type Input struct {
	PackageID                 string
	ReleaseDigest             string
	Manifest                  skillpkg.Manifest
	ConfigurationSchemaDigest string
	ConfigurationSchema       json.RawMessage
	LoadTemplate              TemplateLoader
}

func Project(input Input) (catalogmodel.Item, bool, error) {
	manifest := input.Manifest
	profile := manifest.CatalogProfile
	if profile.Visibility == skillpkg.CatalogVisibilityHidden {
		return catalogmodel.Item{}, false, nil
	}
	if profile.Visibility != skillpkg.CatalogVisibilityListed {
		return catalogmodel.Item{}, false, fmt.Errorf(
			"Skill %q catalog visibility %q is invalid",
			manifest.SkillID,
			profile.Visibility,
		)
	}
	if strings.TrimSpace(profile.CoverMediaRef) != "" {
		return catalogmodel.Item{}, false, fmt.Errorf(
			"listed Skill %q cover media has no immutable media proof",
			manifest.SkillID,
		)
	}
	if strings.TrimSpace(input.ConfigurationSchemaDigest) == "" ||
		len(input.ConfigurationSchema) == 0 || input.LoadTemplate == nil {
		return catalogmodel.Item{}, false, fmt.Errorf(
			"listed Skill %q catalog dependencies are unavailable",
			manifest.SkillID,
		)
	}

	allConsentScopes := catalogapplication.AllContextConsentScopes(
		manifest.ContextProfile,
	)
	requiredConsentScopes := catalogapplication.RequiredContextConsentScopes(
		manifest.ContextProfile,
	)
	if err := exactSemanticIDs(
		manifest.SkillID,
		"consent scopes",
		allConsentScopes,
		profile.ConsentScopes,
	); err != nil {
		return catalogmodel.Item{}, false, err
	}
	if err := exactSemanticIDs(
		manifest.SkillID,
		"surface kinds",
		canonicalStrings(manifest.ActivationProfile.AllowedSurfaceKinds),
		profile.SurfaceKinds,
	); err != nil {
		return catalogmodel.Item{}, false, err
	}

	allowedTemplates := make(map[string]struct{}, len(manifest.Presentation.TemplateRefs))
	for _, raw := range manifest.Presentation.TemplateRefs {
		value := strings.TrimSpace(raw)
		if value != "" {
			allowedTemplates[value] = struct{}{}
		}
	}
	examples := make([]catalogmodel.ResolvedExample, 0, len(profile.Examples))
	for _, example := range profile.Examples {
		if strings.TrimSpace(example.MediaRef) != "" {
			return catalogmodel.Item{}, false, fmt.Errorf(
				"listed Skill %q example %q media has no immutable media proof",
				manifest.SkillID,
				example.ExampleID,
			)
		}
		templateID := strings.TrimSpace(example.TemplateRef)
		if _, allowed := allowedTemplates[templateID]; !allowed {
			return catalogmodel.Item{}, false, fmt.Errorf(
				"listed Skill %q example %q references template %q outside its PresentationProfile",
				manifest.SkillID,
				example.ExampleID,
				templateID,
			)
		}
		raw, found, err := input.LoadTemplate(manifest.SkillID, templateID)
		if err != nil {
			return catalogmodel.Item{}, false, err
		}
		if !found {
			return catalogmodel.Item{}, false, fmt.Errorf(
				"listed Skill %q example %q template %q is unavailable",
				manifest.SkillID,
				example.ExampleID,
				templateID,
			)
		}
		template, err := presentation.DecodeTemplate(raw)
		if err != nil {
			return catalogmodel.Item{}, false, fmt.Errorf(
				"decode listed Skill %q example %q template: %w",
				manifest.SkillID,
				example.ExampleID,
				err,
			)
		}
		if template.SkillID != manifest.SkillID &&
			template.SkillID != presentation.PlatformTemplateSkillID {
			return catalogmodel.Item{}, false, fmt.Errorf(
				"listed Skill %q example %q template owner mismatch",
				manifest.SkillID,
				example.ExampleID,
			)
		}
		examples = append(examples, catalogmodel.ResolvedExample{
			ExampleID:                  strings.TrimSpace(example.ExampleID),
			Title:                      strings.TrimSpace(example.Title),
			Summary:                    strings.TrimSpace(example.Summary),
			IconToken:                  strings.TrimSpace(example.IconToken),
			MediaRef:                   strings.TrimSpace(example.MediaRef),
			PresentationTemplateRef:    presentation.TemplateRef(template),
			PresentationTemplateDigest: template.AssetDigest,
		})
	}

	description := strings.TrimSpace(profile.ValueDescription)
	if description == "" {
		description = strings.TrimSpace(manifest.Description)
	}
	return catalogmodel.Item{
		PackageID:                   strings.TrimSpace(input.PackageID),
		ReleaseDigest:               strings.TrimSpace(input.ReleaseDigest),
		SkillID:                     strings.TrimSpace(manifest.SkillID),
		DomainID:                    strings.TrimSpace(manifest.DomainID),
		DisplayName:                 strings.TrimSpace(manifest.DisplayName),
		Description:                 description,
		CatalogGroup:                semanticLabel(profile.CatalogGroup),
		RequiresConsent:             len(requiredConsentScopes) > 0,
		RequiredConsentScopes:       requiredConsentScopes,
		ConsentScopeLabels:          semanticLabels(profile.ConsentScopes),
		IconHint:                    strings.TrimSpace(profile.IconToken),
		CoverMediaRef:               strings.TrimSpace(profile.CoverMediaRef),
		TargetAudiences:             semanticLabels(profile.TargetAudiences),
		DataUseSummary:              strings.TrimSpace(profile.DataUseSummary),
		Examples:                    examples,
		ActivationMode:              strings.TrimSpace(manifest.ActivationProfile.Mode),
		SurfaceKinds:                semanticLabels(profile.SurfaceKinds),
		ConfigurationSchemaDigest:   strings.TrimSpace(input.ConfigurationSchemaDigest),
		ConfigurationSchema:         append(json.RawMessage(nil), input.ConfigurationSchema...),
		SetupTemplateRef:            strings.TrimSpace(manifest.InputProfile.SetupTemplateRef),
		ConfigurationRequiredFields: canonicalStrings(manifest.InputProfile.RequiredFields),
	}, true, nil
}

func exactSemanticIDs(
	skillID string,
	kind string,
	expected []string,
	labels []skillpkg.CatalogSemanticLabel,
) error {
	actual := make([]string, 0, len(labels))
	for _, label := range labels {
		actual = append(actual, strings.TrimSpace(label.ID))
	}
	actual = canonicalStrings(actual)
	expected = canonicalStrings(expected)
	if len(actual) != len(expected) {
		return fmt.Errorf(
			"listed Skill %q %s metadata does not match capability policy",
			skillID,
			kind,
		)
	}
	for index := range expected {
		if actual[index] != expected[index] {
			return fmt.Errorf(
				"listed Skill %q %s metadata does not match capability policy",
				skillID,
				kind,
			)
		}
	}
	return nil
}

func semanticLabels(values []skillpkg.CatalogSemanticLabel) []catalogmodel.SemanticLabel {
	result := make([]catalogmodel.SemanticLabel, 0, len(values))
	for _, value := range values {
		result = append(result, semanticLabel(value))
	}
	return result
}

func semanticLabel(value skillpkg.CatalogSemanticLabel) catalogmodel.SemanticLabel {
	return catalogmodel.SemanticLabel{
		ID:          strings.TrimSpace(value.ID),
		DisplayText: strings.TrimSpace(value.DisplayText),
		Description: strings.TrimSpace(value.Description),
	}
}

func canonicalStrings(values []string) []string {
	result := make([]string, 0, len(values))
	seen := make(map[string]struct{}, len(values))
	for _, raw := range values {
		value := strings.TrimSpace(raw)
		if value == "" {
			continue
		}
		if _, duplicate := seen[value]; duplicate {
			continue
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	sort.Strings(result)
	return result
}
