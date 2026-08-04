// Package promptassets compiles canonical source assets into a test-only
// resolver. Production execution resolves prompt bodies from the immutable
// SkillPackageRelease frozen by AssistantRun.
package promptassets

import (
	"context"
	"fmt"
	"strings"
	"testing"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
	resourcebuilder "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/infrastructure/resource"
)

type Resolver struct {
	prompts map[string]string
}

func MustResolver(t *testing.T) ports.PromptAssetResolver {
	t.Helper()
	bundle, err := resourcebuilder.NewSourceBuilder().Compile(t.Context())
	if err != nil {
		t.Fatalf("compile canonical Skill source assets: %v", err)
	}
	prompts := make(map[string]string, len(bundle.PromptAssets))
	for assetID, raw := range bundle.PromptAssets {
		content := strings.TrimSpace(string(raw))
		if content == "" {
			t.Fatalf("canonical prompt asset %q is empty", assetID)
		}
		prompts[assetID] = content
	}
	return Resolver{prompts: prompts}
}

func (resolver Resolver) ResolvePromptAssets(
	ctx context.Context,
	assetIDs []string,
) (string, error) {
	if err := ctx.Err(); err != nil {
		return "", err
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
		content, found := resolver.prompts[assetID]
		if !found {
			return "", fmt.Errorf("Skill prompt asset %q is not in the test package", assetID)
		}
		sections = append(sections, content)
	}
	return strings.Join(sections, "\n\n"), nil
}
