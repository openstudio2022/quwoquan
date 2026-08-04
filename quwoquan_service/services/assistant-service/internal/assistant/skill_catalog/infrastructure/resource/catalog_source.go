// Package resource contains the build-time official Skill source compiler.
// Production request paths must use infrastructure/activerelease instead.
package resource

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strings"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/application/catalogprojection"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_catalog/domain/model"
	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
)

const (
	manifestFileName             = "manifest.json"
	profileAssetsDirName         = "profiles"
	inputSchemasDirName          = "input_schemas"
	replayCorpusFileName         = "replay_corpus.json"
	presentationTemplatesDirName = "presentation_templates"
)

var profileAssetFileNames = []string{
	"catalog_activation_input.json",
	"context_capability_orchestration.json",
	"presentation_evaluation.json",
}

// SourceBuilder compiles source-controlled assets into a candidate package.
// It is deliberately not wired into the assistant API binary.
type SourceBuilder struct {
	Root string
}

type SourceBundle struct {
	Root                       string
	Manifests                  []skillpkg.Manifest
	ResolvedManifests          []skillpkg.Manifest
	Profiles                   skillpkg.ProfileAssetCatalog
	ReplayCorpus               skillpkg.ReplayCorpus
	PromptAssets               map[string][]byte
	InputSchemaAssets          map[string][]byte
	PresentationTemplateAssets map[string][]byte
}

func NewSourceBuilder() *SourceBuilder { return &SourceBuilder{} }

func NewSourceBuilderAt(root string) *SourceBuilder {
	return &SourceBuilder{Root: strings.TrimSpace(root)}
}

func (builder *SourceBuilder) Compile(ctx context.Context) (SourceBundle, error) {
	root, err := skillSourceRoot(builder.Root)
	if err != nil {
		return SourceBundle{}, err
	}
	profiles, err := loadProfiles(root)
	if err != nil {
		return SourceBundle{}, err
	}
	replays, err := loadReplayCorpus(root)
	if err != nil {
		return SourceBundle{}, err
	}
	entries, err := os.ReadDir(root)
	if err != nil {
		return SourceBundle{}, fmt.Errorf("read Skill source root: %w", err)
	}
	manifests := []skillpkg.Manifest{}
	resolvedManifests := []skillpkg.Manifest{}
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		if entry.Name() == profileAssetsDirName || entry.Name() == inputSchemasDirName ||
			entry.Name() == presentationTemplatesDirName {
			continue
		}
		if err := ctx.Err(); err != nil {
			return SourceBundle{}, err
		}
		path := filepath.Join(root, entry.Name(), manifestFileName)
		raw, err := os.ReadFile(path)
		if err != nil {
			return SourceBundle{}, fmt.Errorf("read Skill source manifest %s: %w", path, err)
		}
		var manifest skillpkg.Manifest
		decoder := json.NewDecoder(strings.NewReader(string(raw)))
		decoder.DisallowUnknownFields()
		if err := decoder.Decode(&manifest); err != nil {
			return SourceBundle{}, fmt.Errorf("decode Skill source manifest %s: %w", path, err)
		}
		manifests = append(manifests, manifest)
		resolved, err := profiles.ResolveManifest(manifest)
		if err != nil {
			return SourceBundle{}, fmt.Errorf("resolve Skill source manifest %s: %w", path, err)
		}
		replay, proof, err := replays.ResolveAsset(resolved.ReplayAssetRef, resolved.SkillID)
		if err != nil {
			return SourceBundle{}, fmt.Errorf("resolve Skill source replay %q: %w", resolved.SkillID, err)
		}
		resolved.ResolvedAssetRefs["replay"] = proof
		if err := replay.Validate(resolved); err != nil {
			return SourceBundle{}, fmt.Errorf("validate Skill source replay %q: %w", resolved.SkillID, err)
		}
		if _, err := resolved.ResolvedReleaseDigest(); err != nil {
			return SourceBundle{}, fmt.Errorf("resolve Skill source digest %q: %w", resolved.SkillID, err)
		}
		resolvedManifests = append(resolvedManifests, resolved)
	}
	if err := profiles.ValidateManifestReferences(manifests); err != nil {
		return SourceBundle{}, fmt.Errorf("validate Skill profile references: %w", err)
	}
	sort.Slice(manifests, func(left, right int) bool {
		return manifests[left].SkillID < manifests[right].SkillID
	})
	sort.Slice(resolvedManifests, func(left, right int) bool {
		return resolvedManifests[left].SkillID < resolvedManifests[right].SkillID
	})
	prompts, err := loadPromptAssets(root, manifests)
	if err != nil {
		return SourceBundle{}, err
	}
	inputSchemas, err := loadInputSchemaAssets(root, profiles)
	if err != nil {
		return SourceBundle{}, err
	}
	presentationTemplates, err := loadPresentationTemplateAssets(root)
	if err != nil {
		return SourceBundle{}, err
	}
	return SourceBundle{
		Root:                       root,
		Manifests:                  manifests,
		ResolvedManifests:          resolvedManifests,
		Profiles:                   profiles,
		ReplayCorpus:               replays,
		PromptAssets:               prompts,
		InputSchemaAssets:          inputSchemas,
		PresentationTemplateAssets: presentationTemplates,
	}, nil
}

func loadPresentationTemplateAssets(root string) (map[string][]byte, error) {
	directory := filepath.Join(root, presentationTemplatesDirName)
	entries, err := os.ReadDir(directory)
	if err != nil {
		return nil, fmt.Errorf("read Skill presentation templates %s: %w", directory, err)
	}
	assets := make(map[string][]byte, len(entries))
	for _, entry := range entries {
		if entry.IsDir() || filepath.Ext(entry.Name()) != ".json" {
			continue
		}
		path := filepath.Join(directory, entry.Name())
		raw, err := os.ReadFile(path)
		if err != nil {
			return nil, fmt.Errorf("read Skill presentation template %s: %w", path, err)
		}
		var identity struct {
			TemplateID string `json:"templateId"`
			SkillID    string `json:"skillId"`
		}
		if err := json.Unmarshal(raw, &identity); err != nil ||
			strings.TrimSpace(identity.TemplateID) == "" || strings.TrimSpace(identity.SkillID) == "" {
			return nil, fmt.Errorf("Skill presentation template %s has invalid identity", path)
		}
		assetID := "presentation_template:" + strings.TrimSpace(identity.SkillID) + ":" +
			strings.TrimSpace(identity.TemplateID)
		if _, duplicate := assets[assetID]; duplicate {
			return nil, fmt.Errorf("Skill presentation template %q is duplicated", assetID)
		}
		assets[assetID] = append([]byte(nil), raw...)
	}
	if len(assets) == 0 {
		return nil, fmt.Errorf("Skill presentation template assets are empty")
	}
	return assets, nil
}

func loadInputSchemaAssets(
	root string,
	profiles skillpkg.ProfileAssetCatalog,
) (map[string][]byte, error) {
	assets := make(map[string][]byte)
	for _, profile := range profiles.InputProfiles {
		assetID := strings.TrimSpace(profile.ConfigurationSchemaRef)
		if !validSourceAssetID(assetID) {
			return nil, fmt.Errorf(
				"input profile %q has invalid configuration schema ref %q",
				profile.ProfileID,
				profile.ConfigurationSchemaRef,
			)
		}
		if _, found := assets[assetID]; found {
			continue
		}
		path := filepath.Join(root, inputSchemasDirName, assetID+".json")
		raw, err := os.ReadFile(path)
		if err != nil {
			return nil, fmt.Errorf("read Skill input schema %s: %w", path, err)
		}
		var document any
		decoder := json.NewDecoder(strings.NewReader(string(raw)))
		decoder.UseNumber()
		if err := decoder.Decode(&document); err != nil {
			return nil, fmt.Errorf("decode Skill input schema %s: %w", path, err)
		}
		object, ok := document.(map[string]any)
		if !ok || strings.TrimSpace(fmt.Sprint(object["$schema"])) == "" {
			return nil, fmt.Errorf("Skill input schema %q is not a canonical JSON Schema object", assetID)
		}
		assets[assetID] = append([]byte(nil), raw...)
	}
	if len(assets) == 0 {
		return nil, fmt.Errorf("Skill input schema assets are empty")
	}
	return assets, nil
}

func (builder *SourceBuilder) Load(ctx context.Context) ([]skillpkg.Manifest, error) {
	bundle, err := builder.Compile(ctx)
	if err != nil {
		return nil, err
	}
	return append([]skillpkg.Manifest(nil), bundle.ResolvedManifests...), nil
}

func (builder *SourceBuilder) ListCatalogItems(ctx context.Context) ([]model.Item, error) {
	bundle, err := builder.Compile(ctx)
	if err != nil {
		return nil, err
	}
	items := make([]model.Item, 0, len(bundle.ResolvedManifests))
	for _, manifest := range bundle.ResolvedManifests {
		if manifest.CatalogProfile.Visibility == skillpkg.CatalogVisibilityHidden {
			continue
		}
		schemaRef := strings.TrimSpace(manifest.InputProfile.ConfigurationSchemaRef)
		schema, found := bundle.InputSchemaAssets[schemaRef]
		if !found {
			return nil, fmt.Errorf(
				"Skill %q input schema %q is unavailable",
				manifest.SkillID,
				schemaRef,
			)
		}
		schemaSum := sha256.Sum256(schema)
		item, listed, err := catalogprojection.Project(catalogprojection.Input{
			Manifest:                  manifest,
			ConfigurationSchemaDigest: "sha256:" + hex.EncodeToString(schemaSum[:]),
			ConfigurationSchema:       append(json.RawMessage(nil), schema...),
			LoadTemplate: func(skillID string, templateID string) ([]byte, bool, error) {
				for _, owner := range []string{skillID, "quwoquan.official"} {
					assetID := "presentation_template:" + owner + ":" + templateID
					raw, found := bundle.PresentationTemplateAssets[assetID]
					if found {
						return append([]byte(nil), raw...), true, nil
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

func loadProfiles(root string) (skillpkg.ProfileAssetCatalog, error) {
	var profiles skillpkg.ProfileAssetCatalog
	for _, fileName := range profileAssetFileNames {
		path := filepath.Join(root, profileAssetsDirName, fileName)
		raw, err := os.ReadFile(path)
		if err != nil {
			return skillpkg.ProfileAssetCatalog{}, fmt.Errorf("read Skill source profiles %s: %w", path, err)
		}
		var fragment skillpkg.ProfileAssetCatalog
		decoder := json.NewDecoder(strings.NewReader(string(raw)))
		decoder.DisallowUnknownFields()
		if err := decoder.Decode(&fragment); err != nil {
			return skillpkg.ProfileAssetCatalog{}, fmt.Errorf("decode Skill source profiles %s: %w", path, err)
		}
		profiles.CatalogProfiles = append(profiles.CatalogProfiles, fragment.CatalogProfiles...)
		profiles.ActivationProfiles = append(profiles.ActivationProfiles, fragment.ActivationProfiles...)
		profiles.InputProfiles = append(profiles.InputProfiles, fragment.InputProfiles...)
		profiles.ContextProfiles = append(profiles.ContextProfiles, fragment.ContextProfiles...)
		profiles.CapabilityProfiles = append(profiles.CapabilityProfiles, fragment.CapabilityProfiles...)
		profiles.OrchestrationProfiles = append(profiles.OrchestrationProfiles, fragment.OrchestrationProfiles...)
		profiles.TriggerProfiles = append(profiles.TriggerProfiles, fragment.TriggerProfiles...)
		profiles.MemoryProfiles = append(profiles.MemoryProfiles, fragment.MemoryProfiles...)
		profiles.PresentationProfiles = append(profiles.PresentationProfiles, fragment.PresentationProfiles...)
		profiles.EvaluationProfiles = append(profiles.EvaluationProfiles, fragment.EvaluationProfiles...)
	}
	if err := profiles.Validate(); err != nil {
		return skillpkg.ProfileAssetCatalog{}, fmt.Errorf("validate Skill source profile fragments: %w", err)
	}
	return profiles, nil
}

func loadReplayCorpus(root string) (skillpkg.ReplayCorpus, error) {
	path := filepath.Join(root, replayCorpusFileName)
	raw, err := os.ReadFile(path)
	if err != nil {
		return skillpkg.ReplayCorpus{}, fmt.Errorf("read Skill source replay %s: %w", path, err)
	}
	corpus, err := skillpkg.DecodeReplayCorpus(raw)
	if err != nil {
		return skillpkg.ReplayCorpus{}, fmt.Errorf("decode Skill source replay %s: %w", path, err)
	}
	return corpus, nil
}

func loadPromptAssets(
	root string,
	manifests []skillpkg.Manifest,
) (map[string][]byte, error) {
	declared := map[string]struct{}{}
	for _, manifest := range manifests {
		for _, rawID := range manifest.PromptAssets {
			assetID := strings.TrimSpace(rawID)
			if !validSourceAssetID(assetID) {
				return nil, fmt.Errorf("Skill %q has invalid prompt asset %q", manifest.SkillID, rawID)
			}
			declared[assetID] = struct{}{}
		}
	}
	assets := make(map[string][]byte, len(declared))
	for assetID := range declared {
		path := filepath.Join(root, assetID+".md")
		raw, err := os.ReadFile(path)
		if err != nil {
			return nil, fmt.Errorf("read Skill prompt asset %s: %w", path, err)
		}
		if strings.TrimSpace(string(raw)) == "" {
			return nil, fmt.Errorf("Skill prompt asset %q is empty", assetID)
		}
		assets[assetID] = append([]byte(nil), raw...)
	}
	return assets, nil
}

func validSourceAssetID(assetID string) bool {
	if assetID == "" {
		return false
	}
	for _, current := range assetID {
		if (current >= 'a' && current <= 'z') ||
			(current >= 'A' && current <= 'Z') ||
			(current >= '0' && current <= '9') ||
			current == '.' || current == '_' || current == '-' {
			continue
		}
		return false
	}
	return true
}

func skillSourceRoot(explicit string) (string, error) {
	if explicit = strings.TrimSpace(explicit); explicit != "" {
		if info, err := os.Stat(explicit); err == nil && info.IsDir() {
			return explicit, nil
		}
		return "", fmt.Errorf("explicit Skill source root is not a directory: %s", explicit)
	}
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		return "", fmt.Errorf("resolve canonical assistant Skill source root")
	}
	canonical := filepath.Clean(filepath.Join(
		filepath.Dir(file), "..", "..", "..", "..", "..",
		"resources", "skill_packages", "official",
	))
	if info, err := os.Stat(canonical); err == nil && info.IsDir() {
		return canonical, nil
	}
	return "", fmt.Errorf(
		"canonical assistant Skill source root is not a directory: %s",
		canonical,
	)
}
