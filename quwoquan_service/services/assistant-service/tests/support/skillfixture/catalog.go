package skillfixture

import (
	"context"
	"encoding/json"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/orchestration"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/infrastructure/resource"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
)

func Load() ([]skillpkg.Manifest, error) {
	catalog, err := resource.NewSourceBuilder().Load(context.Background())
	if err != nil {
		return nil, err
	}
	return orchestration.ValidateAssistantDomainSkillCatalog(catalog)
}

type Loader struct{}

func (Loader) Load(context.Context) ([]skillpkg.Manifest, error) {
	return Load()
}

// StaticLoader is an object-level test double. Runtime code deliberately has
// no static or file-backed Skill catalog implementation.
type StaticLoader struct {
	Manifests []skillpkg.Manifest
}

func (loader StaticLoader) Load(ctx context.Context) ([]skillpkg.Manifest, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	return append([]skillpkg.Manifest(nil), loader.Manifests...), nil
}

func (Loader) ResolvePresentationTemplate(
	ctx context.Context,
	templateID string,
	skillID string,
) (json.RawMessage, bool, error) {
	bundle, err := resource.NewSourceBuilder().Compile(ctx)
	if err != nil {
		return nil, false, err
	}
	for _, owner := range []string{skillID, "quwoquan.official"} {
		assetID := "presentation_template:" + owner + ":" + templateID
		if raw, found := bundle.PresentationTemplateAssets[assetID]; found {
			return append(json.RawMessage(nil), raw...), true, nil
		}
	}
	return nil, false, nil
}
