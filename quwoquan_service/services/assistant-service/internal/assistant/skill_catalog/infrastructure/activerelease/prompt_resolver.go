package activerelease

import (
	"context"
	"fmt"
	"strings"

	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/skill"
	packageapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application"
	packagemodel "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/domain/model"
)

// PromptResolver resolves prompt bodies from the exact immutable package
// frozen by AssistantRun. It deliberately has no active-pointer fallback:
// execution without a frozen package identity must fail closed.
type PromptResolver struct {
	resolver  ReleaseResolver
	packageID string
}

func NewPromptResolver(
	resolver ReleaseResolver,
	packageID string,
) *PromptResolver {
	return &PromptResolver{
		resolver:  resolver,
		packageID: strings.TrimSpace(packageID),
	}
}

func (resolver *PromptResolver) ResolvePromptAssets(
	ctx context.Context,
	assetIDs []string,
) (string, error) {
	if resolver == nil || resolver.resolver == nil || resolver.packageID == "" {
		return "", fmt.Errorf("Skill package prompt resolver is not configured")
	}
	identity, found := skillpkg.PackageReleaseFromContext(ctx)
	if !found || identity.PackageID != resolver.packageID {
		return "", fmt.Errorf("AssistantRun has no frozen Skill package identity")
	}
	resolved, err := resolver.resolver.ResolveRelease(
		ctx,
		identity.PackageID,
		identity.ReleaseDigest,
	)
	if err != nil {
		return "", fmt.Errorf("resolve frozen Skill package prompts: %w", err)
	}
	return resolvePromptBodies(resolved, assetIDs)
}

func resolvePromptBodies(
	resolved packageapplication.ResolvedRelease,
	assetIDs []string,
) (string, error) {
	if len(assetIDs) == 0 {
		return "", nil
	}
	prompts := make(map[string]string)
	for _, asset := range resolved.Release.Assets {
		if asset.Kind != packagemodel.AssetPrompt {
			continue
		}
		raw, ok := resolved.Assets[asset.AssetID]
		if !ok {
			return "", fmt.Errorf("Skill prompt asset %q is unavailable", asset.AssetID)
		}
		content := strings.TrimSpace(string(raw))
		if content == "" {
			return "", fmt.Errorf("Skill prompt asset %q is empty", asset.AssetID)
		}
		prompts[asset.AssetID] = content
	}
	sections := make([]string, 0, len(assetIDs))
	seen := make(map[string]struct{}, len(assetIDs))
	for _, rawID := range assetIDs {
		assetID := strings.TrimSpace(rawID)
		if assetID == "" {
			return "", fmt.Errorf("Skill prompt asset id is required")
		}
		if _, duplicate := seen[assetID]; duplicate {
			return "", fmt.Errorf("Skill prompt asset %q is duplicated", assetID)
		}
		seen[assetID] = struct{}{}
		content, ok := prompts[assetID]
		if !ok {
			return "", fmt.Errorf("Skill prompt asset %q is not in the frozen package", assetID)
		}
		sections = append(sections, content)
	}
	return strings.Join(sections, "\n\n"), nil
}
