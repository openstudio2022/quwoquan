package orchestration

import (
	"context"

	catalogapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/application"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
)

func (service *AssistantService) resolveSkillManifest(
	ctx context.Context,
	skillID string,
) (skillpkg.Manifest, bool, error) {
	return catalogapplication.ResolveRuntimeManifest(
		ctx,
		service.skillCatalog,
		skillID,
	)
}
