package application

import (
	"context"
	"sort"
	"strings"

	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
)

// AllContextConsentScopes returns every consent scope declared by the frozen
// ContextProfile. Catalog UI uses this complete set to explain optional and
// required data access without inventing labels from a Skill ID.
func AllContextConsentScopes(profile skillpkg.ContextProfile) []string {
	return contextConsentScopes(profile, false)
}

// RequiredContextConsentScopes returns only scopes attached to requirements
// that the immutable package marks required. Optional context is resolved
// opportunistically and must never block Skill start or proactive delivery.
func RequiredContextConsentScopes(profile skillpkg.ContextProfile) []string {
	return contextConsentScopes(profile, true)
}

func contextConsentScopes(
	profile skillpkg.ContextProfile,
	requiredOnly bool,
) []string {
	set := make(map[string]struct{})
	for _, requirement := range profile.Requirements {
		if requiredOnly && !requirement.Required {
			continue
		}
		for _, raw := range requirement.ConsentScopes {
			if scope := strings.TrimSpace(raw); scope != "" {
				set[scope] = struct{}{}
			}
		}
	}
	result := make([]string, 0, len(set))
	for scope := range set {
		result = append(result, scope)
	}
	sort.Strings(result)
	return result
}

// ResolveRuntimeManifest resolves a manifest from the frozen active package
// loader. Catalog lookup is owned by SkillCatalog; execution owners must not
// reimplement source selection or fall back to a second catalog.
func ResolveRuntimeManifest(
	ctx context.Context,
	loader skillpkg.Loader,
	skillID string,
) (skillpkg.Manifest, bool, error) {
	skillID = strings.TrimSpace(skillID)
	if skillID == "" || loader == nil {
		return skillpkg.Manifest{}, false, nil
	}
	catalog, err := loader.Load(ctx)
	if err != nil {
		return skillpkg.Manifest{}, false, err
	}
	for _, manifest := range catalog {
		if strings.TrimSpace(manifest.SkillID) == skillID {
			return manifest, true, nil
		}
	}
	return skillpkg.Manifest{}, false, nil
}
