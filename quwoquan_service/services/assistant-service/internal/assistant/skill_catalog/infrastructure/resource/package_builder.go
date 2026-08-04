package resource

import (
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"path/filepath"
	"sort"
	"strings"
	"time"

	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
	packagemodel "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/domain/model"
)

type PackageBuildOptions struct {
	PackageID            string
	PackageVersion       string
	BuildID              string
	SourceRepository     string
	SourceRevision       string
	BuiltAt              time.Time
	RuntimeCompatibility packagemodel.RuntimeCompatibility
	CapabilityGrants     []packagemodel.CapabilityGrant
	SigningKeyID         string
	SigningPrivateKey    ed25519.PrivateKey
}

type PackageFile struct {
	RelativePath string
	Content      []byte
}

type BuiltPackage struct {
	Release packagemodel.Release
	Files   []PackageFile
}

func BuildPackage(
	bundle SourceBundle,
	options PackageBuildOptions,
) (BuiltPackage, error) {
	if len(bundle.Manifests) == 0 || len(bundle.ResolvedManifests) == 0 ||
		len(bundle.PromptAssets) == 0 ||
		len(bundle.InputSchemaAssets) == 0 ||
		!validBuildPathSegment(options.BuildID) ||
		len(options.SigningPrivateKey) != ed25519.PrivateKeySize {
		return BuiltPackage{}, fmt.Errorf("official Skill package build input is incomplete")
	}
	assets := make([]packagemodel.Asset, 0)
	files := make([]PackageFile, 0)
	assetIDs := map[string]struct{}{}
	appendAsset := func(
		assetID string,
		kind string,
		extension string,
		content []byte,
	) error {
		assetID = strings.TrimSpace(assetID)
		if assetID == "" || len(content) == 0 {
			return fmt.Errorf("Skill package %s asset identity/content is invalid", kind)
		}
		if _, duplicate := assetIDs[assetID]; duplicate {
			return fmt.Errorf("Skill package asset %q is duplicated", assetID)
		}
		assetIDs[assetID] = struct{}{}
		nameSum := sha256.Sum256([]byte(assetID))
		relative := filepath.ToSlash(filepath.Join(
			"releases",
			options.BuildID,
			"assets",
			kind,
			hex.EncodeToString(nameSum[:])+extension,
		))
		contentSum := sha256.Sum256(content)
		assets = append(assets, packagemodel.Asset{
			AssetID:     assetID,
			Kind:        kind,
			Locator:     "skill-package://official/" + relative,
			AssetDigest: "sha256:" + hex.EncodeToString(contentSum[:]),
		})
		files = append(files, PackageFile{
			RelativePath: relative,
			Content:      append([]byte(nil), content...),
		})
		return nil
	}
	appendJSON := func(assetID string, kind string, value any) error {
		content, err := json.MarshalIndent(value, "", "  ")
		if err != nil {
			return fmt.Errorf("encode Skill package asset %q: %w", assetID, err)
		}
		content = append(content, '\n')
		return appendAsset(assetID, kind, ".json", content)
	}
	for _, manifest := range bundle.Manifests {
		if err := appendJSON(
			"manifest:"+manifest.SkillID,
			packagemodel.AssetManifest,
			manifest,
		); err != nil {
			return BuiltPackage{}, err
		}
	}
	if err := appendProfileAssets(appendJSON, bundle.Profiles); err != nil {
		return BuiltPackage{}, err
	}
	inputSchemaIDs := make([]string, 0, len(bundle.InputSchemaAssets))
	for assetID := range bundle.InputSchemaAssets {
		inputSchemaIDs = append(inputSchemaIDs, assetID)
	}
	sort.Strings(inputSchemaIDs)
	for _, assetID := range inputSchemaIDs {
		if err := appendAsset(
			assetID,
			packagemodel.AssetInputSchema,
			".json",
			bundle.InputSchemaAssets[assetID],
		); err != nil {
			return BuiltPackage{}, err
		}
	}
	presentationTemplateIDs := make([]string, 0, len(bundle.PresentationTemplateAssets))
	for assetID := range bundle.PresentationTemplateAssets {
		presentationTemplateIDs = append(presentationTemplateIDs, assetID)
	}
	sort.Strings(presentationTemplateIDs)
	for _, assetID := range presentationTemplateIDs {
		if err := appendAsset(
			assetID,
			packagemodel.AssetPresentationTemplate,
			".json",
			bundle.PresentationTemplateAssets[assetID],
		); err != nil {
			return BuiltPackage{}, err
		}
	}
	for _, replay := range bundle.ReplayCorpus.Assets {
		if err := appendJSON(
			"replay:"+replay.AssetID,
			packagemodel.AssetReplay,
			skillpkg.ReplayCorpus{Assets: []skillpkg.ReplayCorpusAsset{replay}},
		); err != nil {
			return BuiltPackage{}, err
		}
	}
	promptIDs := make([]string, 0, len(bundle.PromptAssets))
	for assetID := range bundle.PromptAssets {
		promptIDs = append(promptIDs, assetID)
	}
	sort.Strings(promptIDs)
	for _, assetID := range promptIDs {
		if err := appendAsset(
			assetID,
			packagemodel.AssetPrompt,
			".md",
			bundle.PromptAssets[assetID],
		); err != nil {
			return BuiltPackage{}, err
		}
	}
	sort.Slice(files, func(left, right int) bool {
		return files[left].RelativePath < files[right].RelativePath
	})
	release := packagemodel.Release{
		PackageID:            strings.TrimSpace(options.PackageID),
		PackageVersion:       strings.TrimSpace(options.PackageVersion),
		ReleaseDigest:        "sha256:" + strings.Repeat("0", sha256.Size*2),
		Assets:               assets,
		RuntimeCompatibility: options.RuntimeCompatibility,
		Provenance: packagemodel.Provenance{
			SourceRepository: strings.TrimSpace(options.SourceRepository),
			SourceRevision:   strings.TrimSpace(options.SourceRevision),
			BuildID:          strings.TrimSpace(options.BuildID),
			BuiltAt:          options.BuiltAt.UTC(),
		},
		Signature: packagemodel.Signature{
			Algorithm: "ed25519",
			KeyID:     strings.TrimSpace(options.SigningKeyID),
			Value:     "pending",
		},
		CapabilityGrants: append(
			[]packagemodel.CapabilityGrant(nil),
			options.CapabilityGrants...,
		),
	}
	digest, err := packagemodel.Digest(release)
	if err != nil {
		return BuiltPackage{}, fmt.Errorf("build Skill package descriptor: %w", err)
	}
	release.ReleaseDigest = digest
	release.Signature.Value = base64.StdEncoding.EncodeToString(
		ed25519.Sign(options.SigningPrivateKey, []byte(digest)),
	)
	if _, err := packagemodel.Normalize(release); err != nil {
		return BuiltPackage{}, fmt.Errorf("validate built Skill package: %w", err)
	}
	return BuiltPackage{Release: release, Files: files}, nil
}

type appendJSONAsset func(string, string, any) error

func appendProfileAssets(
	appendJSON appendJSONAsset,
	profiles skillpkg.ProfileAssetCatalog,
) error {
	for _, value := range profiles.CatalogProfiles {
		if err := appendJSON("catalog:"+value.ProfileID, packagemodel.AssetCatalog, value); err != nil {
			return err
		}
	}
	for _, value := range profiles.ActivationProfiles {
		if err := appendJSON("activation:"+value.ProfileID, packagemodel.AssetActivation, value); err != nil {
			return err
		}
	}
	for _, value := range profiles.InputProfiles {
		if err := appendJSON("input:"+value.ProfileID, packagemodel.AssetInput, value); err != nil {
			return err
		}
	}
	for _, value := range profiles.ContextProfiles {
		if err := appendJSON("context:"+value.ProfileID, packagemodel.AssetContext, value); err != nil {
			return err
		}
	}
	for _, value := range profiles.CapabilityProfiles {
		if err := appendJSON("capability:"+value.ProfileID, packagemodel.AssetCapability, value); err != nil {
			return err
		}
	}
	for _, value := range profiles.OrchestrationProfiles {
		if err := appendJSON("orchestration:"+value.ProfileID, packagemodel.AssetOrchestration, value); err != nil {
			return err
		}
	}
	for _, value := range profiles.TriggerProfiles {
		if err := appendJSON("trigger:"+value.ProfileID, packagemodel.AssetTrigger, value); err != nil {
			return err
		}
	}
	for _, value := range profiles.MemoryProfiles {
		if err := appendJSON("memory:"+value.ProfileID, packagemodel.AssetMemory, value); err != nil {
			return err
		}
	}
	for _, value := range profiles.PresentationProfiles {
		if err := appendJSON("presentation:"+value.ProfileID, packagemodel.AssetPresentation, value); err != nil {
			return err
		}
	}
	for _, value := range profiles.EvaluationProfiles {
		if err := appendJSON("evaluation:"+value.ProfileID, packagemodel.AssetEvaluation, value); err != nil {
			return err
		}
	}
	return nil
}

func validBuildPathSegment(value string) bool {
	value = strings.TrimSpace(value)
	if value == "" || value == "." || value == ".." {
		return false
	}
	for _, current := range value {
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
