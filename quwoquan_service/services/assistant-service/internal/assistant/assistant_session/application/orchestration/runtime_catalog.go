package orchestration

import (
	"context"
	"strings"

	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_session/application/skill"
)

func (l *AgentLoop) resolveSkillManifest(
	ctx context.Context,
	skillID string,
) (skillpkg.Manifest, bool, error) {
	loader := l.Catalog
	if loader == nil {
		loader = emptySkillCatalogLoader{}
	}
	return resolveSkillManifest(ctx, loader, skillID)
}

func (service *AssistantService) resolveSkillManifest(
	ctx context.Context,
	skillID string,
) (skillpkg.Manifest, bool, error) {
	loader := service.skillCatalog
	if loader == nil {
		loader = emptySkillCatalogLoader{}
	}
	return resolveSkillManifest(ctx, loader, skillID)
}

type emptySkillCatalogLoader struct{}

func (emptySkillCatalogLoader) Load(context.Context) ([]skillpkg.Manifest, error) {
	return nil, nil
}

func resolveSkillManifest(
	ctx context.Context,
	loader skillpkg.Loader,
	skillID string,
) (skillpkg.Manifest, bool, error) {
	skillID = strings.TrimSpace(skillID)
	if skillID == "" {
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
