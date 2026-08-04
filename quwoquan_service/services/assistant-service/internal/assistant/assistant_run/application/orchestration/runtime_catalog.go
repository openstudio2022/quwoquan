package orchestration

import (
	"context"

	catalogapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/application"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
)

func (l *AgentLoop) resolveSkillManifest(
	ctx context.Context,
	skillID string,
) (skillpkg.Manifest, bool, error) {
	if l == nil {
		return skillpkg.Manifest{}, false, nil
	}
	return catalogapplication.ResolveRuntimeManifest(ctx, l.Catalog, skillID)
}
