package activerelease

import (
	"context"
	"encoding/json"
	"fmt"
	"sort"
	"strings"

	"github.com/santhosh-tekuri/jsonschema/v6"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/application/catalogprojection"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/domain/model"
	packageapplication "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
	packagemodel "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/domain/model"
)

const OfficialPackageID = "assistant.session.skills"

type ReleaseResolver interface {
	ResolveActive(context.Context, string) (packageapplication.ResolvedRelease, error)
	ResolveRelease(context.Context, string, string) (packageapplication.ResolvedRelease, error)
}

type CatalogValidator func([]skillpkg.Manifest) ([]skillpkg.Manifest, error)

// CatalogSource is the production Skill manifest boundary. It resolves the
// active pointer on every call and decodes only digest-verified immutable
// assets returned by SkillPackageRelease. It never discovers files or invents
// built-in catalog entries.
type CatalogSource struct {
	resolver  ReleaseResolver
	packageID string
	validate  CatalogValidator
}

// ValidateSharedSkillIDs verifies a Placement disabled list against the
// current active package and its immutable ActivationProfile. Unknown and
// personal-only Skills are rejected instead of becoming inert policy data.
func (source *CatalogSource) ValidateSharedSkillIDs(
	ctx context.Context,
	surfaceKind string,
	skillIDs []string,
) error {
	surfaceKind = strings.TrimSpace(surfaceKind)
	if surfaceKind != "conversation" && surfaceKind != "circle" {
		return model.ErrSkillNotShared
	}
	snapshot, err := source.ResolveSnapshot(ctx)
	if err != nil {
		return err
	}
	eligible := make(map[string]struct{})
	for _, manifest := range snapshot.Manifests {
		for _, allowed := range manifest.ActivationProfile.AllowedSurfaceKinds {
			if allowed == surfaceKind {
				eligible[manifest.SkillID] = struct{}{}
				break
			}
		}
	}
	for _, skillID := range skillIDs {
		if _, found := eligible[strings.TrimSpace(skillID)]; !found {
			return fmt.Errorf("%w: %s", model.ErrSkillNotShared, skillID)
		}
	}
	return nil
}

func NewCatalogSource(
	resolver ReleaseResolver,
	packageID string,
	validate CatalogValidator,
) *CatalogSource {
	return &CatalogSource{
		resolver:  resolver,
		packageID: strings.TrimSpace(packageID),
		validate:  validate,
	}
}

func (source *CatalogSource) Load(
	ctx context.Context,
) ([]skillpkg.Manifest, error) {
	snapshot, err := source.resolveContextSnapshot(ctx)
	if err != nil {
		return nil, err
	}
	return append([]skillpkg.Manifest(nil), snapshot.Manifests...), nil
}

func (source *CatalogSource) resolveContextSnapshot(ctx context.Context) (Snapshot, error) {
	identity, frozen := skillpkg.PackageReleaseFromContext(ctx)
	if frozen {
		return source.ResolveReleaseSnapshot(
			ctx,
			identity.PackageID,
			identity.ReleaseDigest,
		)
	}
	return source.ResolveSnapshot(ctx)
}

func (source *CatalogSource) ResolveActiveSkillPackage(
	ctx context.Context,
) (string, string, error) {
	snapshot, err := source.ResolveSnapshot(ctx)
	if err != nil {
		return "", "", err
	}
	return snapshot.PackageID, snapshot.ReleaseDigest, nil
}

// ContainsSkillInFrozenPackage resolves membership only from the immutable
// package identity carried by ctx. It deliberately rejects an active-pointer
// lookup so a Run start cannot mix authorization from one release with the
// identity persisted from another release.
func (source *CatalogSource) ContainsSkillInFrozenPackage(
	ctx context.Context,
	skillID string,
) (bool, error) {
	if _, frozen := skillpkg.PackageReleaseFromContext(ctx); !frozen {
		return false, fmt.Errorf("frozen Skill package context is required")
	}
	snapshot, err := source.resolveContextSnapshot(ctx)
	if err != nil {
		return false, err
	}
	skillID = strings.TrimSpace(skillID)
	if skillID == "" {
		return false, nil
	}
	for _, manifest := range snapshot.Manifests {
		if strings.TrimSpace(manifest.SkillID) == skillID {
			return true, nil
		}
	}
	return false, nil
}

func (source *CatalogSource) ListCatalogItems(
	ctx context.Context,
) ([]model.Item, error) {
	snapshot, err := source.resolveContextSnapshot(ctx)
	if err != nil {
		return nil, err
	}
	items := make([]model.Item, 0, len(snapshot.Manifests))
	for _, manifest := range snapshot.Manifests {
		if manifest.CatalogProfile.Visibility == skillpkg.CatalogVisibilityHidden {
			continue
		}
		schemaRef := strings.TrimSpace(manifest.InputProfile.ConfigurationSchemaRef)
		schema, found := snapshot.InputSchemas[schemaRef]
		if !found || strings.TrimSpace(schema.AssetDigest) == "" {
			return nil, fmt.Errorf(
				"active Skill %q input schema %q is unavailable",
				manifest.SkillID,
				schemaRef,
			)
		}
		configurationSchema, err := json.Marshal(schema.Document)
		if err != nil {
			return nil, fmt.Errorf(
				"encode active Skill %q input schema %q: %w",
				manifest.SkillID,
				schemaRef,
				err,
			)
		}
		item, listed, err := catalogprojection.Project(catalogprojection.Input{
			PackageID:                 snapshot.PackageID,
			ReleaseDigest:             snapshot.ReleaseDigest,
			Manifest:                  manifest,
			ConfigurationSchemaDigest: schema.AssetDigest,
			ConfigurationSchema:       configurationSchema,
			LoadTemplate: func(skillID string, templateID string) ([]byte, bool, error) {
				for _, owner := range []string{skillID, "quwoquan.official"} {
					key := owner + "\x00" + templateID
					asset, found := snapshot.PresentationTemplates[key]
					if found {
						return append([]byte(nil), asset.Document...), true, nil
					}
				}
				return nil, false, nil
			},
		})
		if err != nil {
			return nil, err
		}
		if listed {
			items = append(items, item)
		}
	}
	return items, nil
}

type Snapshot struct {
	PackageID             string
	ReleaseDigest         string
	Manifests             []skillpkg.Manifest
	InputSchemas          map[string]InputSchema
	PresentationTemplates map[string]PresentationTemplateAsset
}

type InputSchema struct {
	AssetID     string
	AssetDigest string
	Document    any
}

type PresentationTemplateAsset struct {
	AssetID     string
	AssetDigest string
	TemplateID  string
	SkillID     string
	Document    json.RawMessage
}

// ResolvePresentationTemplate resolves only the digest-verified template asset
// from the active or Run-frozen Skill package selected by the request context.
func (source *CatalogSource) ResolvePresentationTemplate(
	ctx context.Context,
	templateID string,
	skillID string,
) (json.RawMessage, bool, error) {
	var snapshot Snapshot
	identity, frozen := skillpkg.PackageReleaseFromContext(ctx)
	var err error
	if frozen {
		snapshot, err = source.ResolveReleaseSnapshot(ctx, identity.PackageID, identity.ReleaseDigest)
	} else {
		snapshot, err = source.ResolveSnapshot(ctx)
	}
	if err != nil {
		return nil, false, err
	}
	key := strings.TrimSpace(skillID) + "\x00" + strings.TrimSpace(templateID)
	asset, found := snapshot.PresentationTemplates[key]
	if !found {
		key = "quwoquan.official\x00" + strings.TrimSpace(templateID)
		asset, found = snapshot.PresentationTemplates[key]
	}
	if !found {
		return nil, false, nil
	}
	return append(json.RawMessage(nil), asset.Document...), true, nil
}

// ValidateConfiguration binds a setting to the exact input schema carried by
// the active immutable package. It never resolves source files or accepts a
// caller-provided schema.
func (source *CatalogSource) ValidateConfiguration(
	ctx context.Context,
	skillID string,
	schemaDigest string,
	configuration json.RawMessage,
) error {
	snapshot, err := source.ResolveSnapshot(ctx)
	if err != nil {
		return err
	}
	skillID = strings.TrimSpace(skillID)
	var schemaRef string
	for _, manifest := range snapshot.Manifests {
		if manifest.SkillID == skillID {
			schemaRef = strings.TrimSpace(manifest.InputProfile.ConfigurationSchemaRef)
			break
		}
	}
	if schemaRef == "" {
		return model.ErrSkillNotFound
	}
	schema, found := snapshot.InputSchemas[schemaRef]
	if !found {
		return fmt.Errorf("active Skill input schema %q is unavailable", schemaRef)
	}
	if strings.TrimSpace(schemaDigest) != schema.AssetDigest {
		return model.ErrConfigurationSchemaDigestMismatch
	}
	var value any
	decoder := json.NewDecoder(strings.NewReader(string(configuration)))
	decoder.UseNumber()
	if err := decoder.Decode(&value); err != nil {
		return fmt.Errorf("%w: %v", model.ErrConfigurationInvalid, err)
	}
	if _, ok := value.(map[string]any); !ok {
		return fmt.Errorf("%w: configuration root must be an object", model.ErrConfigurationInvalid)
	}
	compiler := jsonschema.NewCompiler()
	location := "urn:quwoquan:skill-input-schema:" + strings.TrimPrefix(schema.AssetDigest, "sha256:")
	if err := compiler.AddResource(location, schema.Document); err != nil {
		return fmt.Errorf("compile active Skill input schema %q: %w", schemaRef, err)
	}
	compiled, err := compiler.Compile(location)
	if err != nil {
		return fmt.Errorf("compile active Skill input schema %q: %w", schemaRef, err)
	}
	if err := compiled.Validate(value); err != nil {
		return fmt.Errorf("%w: %v", model.ErrConfigurationInvalid, err)
	}
	return nil
}

func (source *CatalogSource) ResolveSnapshot(
	ctx context.Context,
) (Snapshot, error) {
	if source == nil || source.resolver == nil || source.validate == nil ||
		source.packageID == "" {
		return Snapshot{}, fmt.Errorf("active Skill package catalog is not configured")
	}
	if err := ctx.Err(); err != nil {
		return Snapshot{}, err
	}
	resolved, err := source.resolver.ResolveActive(ctx, source.packageID)
	if err != nil {
		return Snapshot{}, fmt.Errorf("resolve active Skill package %q: %w", source.packageID, err)
	}
	if resolved.Release.PackageID != source.packageID ||
		strings.TrimSpace(resolved.Release.ReleaseDigest) == "" {
		return Snapshot{}, fmt.Errorf("active Skill package identity mismatch")
	}
	return source.resolveSnapshot(resolved)
}

func (source *CatalogSource) ResolveReleaseSnapshot(
	ctx context.Context,
	packageID string,
	releaseDigest string,
) (Snapshot, error) {
	if source == nil || source.resolver == nil || source.validate == nil ||
		strings.TrimSpace(packageID) == "" ||
		strings.TrimSpace(releaseDigest) == "" ||
		strings.TrimSpace(packageID) != source.packageID {
		return Snapshot{}, fmt.Errorf("frozen Skill package identity is invalid")
	}
	if err := ctx.Err(); err != nil {
		return Snapshot{}, err
	}
	resolved, err := source.resolver.ResolveRelease(
		ctx,
		strings.TrimSpace(packageID),
		strings.TrimSpace(releaseDigest),
	)
	if err != nil {
		return Snapshot{}, fmt.Errorf(
			"resolve frozen Skill package %q@%q: %w",
			packageID,
			releaseDigest,
			err,
		)
	}
	if resolved.Release.PackageID != strings.TrimSpace(packageID) ||
		resolved.Release.ReleaseDigest != strings.TrimSpace(releaseDigest) {
		return Snapshot{}, fmt.Errorf("frozen Skill package identity mismatch")
	}
	return source.resolveSnapshot(resolved)
}

func (source *CatalogSource) resolveSnapshot(
	resolved packageapplication.ResolvedRelease,
) (Snapshot, error) {
	manifests, inputSchemas, presentationTemplates, err := decodeCatalog(resolved)
	if err != nil {
		return Snapshot{}, err
	}
	manifests, err = source.validate(manifests)
	if err != nil {
		return Snapshot{}, fmt.Errorf("validate active Skill package catalog: %w", err)
	}
	return Snapshot{
		PackageID:             resolved.Release.PackageID,
		ReleaseDigest:         resolved.Release.ReleaseDigest,
		Manifests:             append([]skillpkg.Manifest(nil), manifests...),
		InputSchemas:          inputSchemas,
		PresentationTemplates: presentationTemplates,
	}, nil
}

func decodeCatalog(
	resolved packageapplication.ResolvedRelease,
) ([]skillpkg.Manifest, map[string]InputSchema, map[string]PresentationTemplateAsset, error) {
	profiles := skillpkg.ProfileAssetCatalog{}
	manifests := []skillpkg.Manifest{}
	replays := skillpkg.ReplayCorpus{}
	promptAssetIDs := map[string]struct{}{}
	inputSchemas := map[string]InputSchema{}
	presentationTemplates := map[string]PresentationTemplateAsset{}
	for _, asset := range resolved.Release.Assets {
		raw, found := resolved.Assets[asset.AssetID]
		if !found {
			return nil, nil, nil, fmt.Errorf("active Skill package asset %q is unavailable", asset.AssetID)
		}
		if err := decodeAsset(
			asset,
			raw,
			&profiles,
			&manifests,
			&replays,
			promptAssetIDs,
			inputSchemas,
			presentationTemplates,
		); err != nil {
			return nil, nil, nil, err
		}
	}
	if err := profiles.Validate(); err != nil {
		return nil, nil, nil, fmt.Errorf("validate active Skill package profiles: %w", err)
	}
	for _, profile := range profiles.InputProfiles {
		if _, found := inputSchemas[strings.TrimSpace(profile.ConfigurationSchemaRef)]; !found {
			return nil, nil, nil, fmt.Errorf(
				"active input profile %q references missing schema %q",
				profile.ProfileID,
				profile.ConfigurationSchemaRef,
			)
		}
	}
	for index, manifest := range manifests {
		for _, promptAssetID := range manifest.PromptAssets {
			if _, found := promptAssetIDs[strings.TrimSpace(promptAssetID)]; !found {
				return nil, nil, nil, fmt.Errorf(
					"active Skill manifest %q references missing prompt asset %q",
					manifest.SkillID,
					promptAssetID,
				)
			}
		}
		manifest, err := profiles.ResolveManifest(manifest)
		if err != nil {
			return nil, nil, nil, fmt.Errorf("resolve active Skill manifest %q: %w", manifest.SkillID, err)
		}
		replay, proof, err := replays.ResolveAsset(manifest.ReplayAssetRef, manifest.SkillID)
		if err != nil {
			return nil, nil, nil, fmt.Errorf("resolve active Skill replay %q: %w", manifest.SkillID, err)
		}
		manifest.ResolvedAssetRefs["replay"] = proof
		if err := replay.Validate(manifest); err != nil {
			return nil, nil, nil, fmt.Errorf("validate active Skill replay %q: %w", manifest.SkillID, err)
		}
		if _, err := manifest.ResolvedReleaseDigest(); err != nil {
			return nil, nil, nil, fmt.Errorf("resolve active Skill digest %q: %w", manifest.SkillID, err)
		}
		manifests[index] = manifest
	}
	sort.Slice(manifests, func(left, right int) bool {
		return manifests[left].SkillID < manifests[right].SkillID
	})
	return manifests, inputSchemas, presentationTemplates, nil
}

func decodeAsset(
	asset packagemodel.Asset,
	raw []byte,
	profiles *skillpkg.ProfileAssetCatalog,
	manifests *[]skillpkg.Manifest,
	replays *skillpkg.ReplayCorpus,
	promptAssetIDs map[string]struct{},
	inputSchemas map[string]InputSchema,
	presentationTemplates map[string]PresentationTemplateAsset,
) error {
	decode := func(target any) error {
		decoder := json.NewDecoder(strings.NewReader(string(raw)))
		decoder.DisallowUnknownFields()
		if err := decoder.Decode(target); err != nil {
			return fmt.Errorf("decode active Skill asset %q (%s): %w", asset.AssetID, asset.Kind, err)
		}
		return nil
	}
	switch asset.Kind {
	case packagemodel.AssetManifest:
		var value skillpkg.Manifest
		if err := decode(&value); err != nil {
			return err
		}
		*manifests = append(*manifests, value)
	case packagemodel.AssetCatalog:
		var value skillpkg.CatalogProfile
		if err := decode(&value); err != nil {
			return err
		}
		profiles.CatalogProfiles = append(profiles.CatalogProfiles, value)
	case packagemodel.AssetActivation:
		var value skillpkg.ActivationProfile
		if err := decode(&value); err != nil {
			return err
		}
		profiles.ActivationProfiles = append(profiles.ActivationProfiles, value)
	case packagemodel.AssetInput:
		var value skillpkg.InputProfile
		if err := decode(&value); err != nil {
			return err
		}
		profiles.InputProfiles = append(profiles.InputProfiles, value)
	case packagemodel.AssetInputSchema:
		var value any
		if err := decode(&value); err != nil {
			return err
		}
		object, ok := value.(map[string]any)
		if !ok || strings.TrimSpace(fmt.Sprint(object["$schema"])) == "" {
			return fmt.Errorf("active Skill input schema %q must be a canonical JSON Schema object", asset.AssetID)
		}
		inputSchemas[asset.AssetID] = InputSchema{
			AssetID:     asset.AssetID,
			AssetDigest: asset.AssetDigest,
			Document:    value,
		}
	case packagemodel.AssetContext:
		var value skillpkg.ContextProfile
		if err := decode(&value); err != nil {
			return err
		}
		profiles.ContextProfiles = append(profiles.ContextProfiles, value)
	case packagemodel.AssetCapability:
		var value skillpkg.CapabilityProfile
		if err := decode(&value); err != nil {
			return err
		}
		profiles.CapabilityProfiles = append(profiles.CapabilityProfiles, value)
	case packagemodel.AssetOrchestration:
		var value skillpkg.OrchestrationProfile
		if err := decode(&value); err != nil {
			return err
		}
		profiles.OrchestrationProfiles = append(profiles.OrchestrationProfiles, value)
	case packagemodel.AssetTrigger:
		var value skillpkg.TriggerProfile
		if err := decode(&value); err != nil {
			return err
		}
		profiles.TriggerProfiles = append(profiles.TriggerProfiles, value)
	case packagemodel.AssetMemory:
		var value skillpkg.MemoryProfile
		if err := decode(&value); err != nil {
			return err
		}
		profiles.MemoryProfiles = append(profiles.MemoryProfiles, value)
	case packagemodel.AssetPresentation:
		var value skillpkg.PresentationProfile
		if err := decode(&value); err != nil {
			return err
		}
		profiles.PresentationProfiles = append(profiles.PresentationProfiles, value)
	case packagemodel.AssetPresentationTemplate:
		var identity struct {
			TemplateID string `json:"templateId"`
			SkillID    string `json:"skillId"`
		}
		if err := json.Unmarshal(raw, &identity); err != nil {
			return fmt.Errorf("decode active Skill presentation template %q: %w", asset.AssetID, err)
		}
		identity.TemplateID = strings.TrimSpace(identity.TemplateID)
		identity.SkillID = strings.TrimSpace(identity.SkillID)
		if identity.TemplateID == "" || identity.SkillID == "" {
			return fmt.Errorf("active Skill presentation template %q has invalid identity", asset.AssetID)
		}
		key := identity.SkillID + "\x00" + identity.TemplateID
		if _, duplicate := presentationTemplates[key]; duplicate {
			return fmt.Errorf("active Skill presentation template %q is duplicated", key)
		}
		presentationTemplates[key] = PresentationTemplateAsset{
			AssetID: asset.AssetID, AssetDigest: asset.AssetDigest,
			TemplateID: identity.TemplateID, SkillID: identity.SkillID,
			Document: append(json.RawMessage(nil), raw...),
		}
	case packagemodel.AssetEvaluation:
		var value skillpkg.EvaluationProfile
		if err := decode(&value); err != nil {
			return err
		}
		profiles.EvaluationProfiles = append(profiles.EvaluationProfiles, value)
	case packagemodel.AssetReplay:
		value, err := skillpkg.DecodeReplayCorpus(raw)
		if err != nil {
			return fmt.Errorf("decode active Skill replay asset %q: %w", asset.AssetID, err)
		}
		replays.Assets = append(replays.Assets, value.Assets...)
	case packagemodel.AssetPrompt:
		if strings.TrimSpace(asset.AssetID) == "" || strings.TrimSpace(string(raw)) == "" {
			return fmt.Errorf("active Skill prompt asset %q is empty", asset.AssetID)
		}
		promptAssetIDs[strings.TrimSpace(asset.AssetID)] = struct{}{}
	default:
		return fmt.Errorf("active Skill package asset %q has unsupported kind %q", asset.AssetID, asset.Kind)
	}
	return nil
}
