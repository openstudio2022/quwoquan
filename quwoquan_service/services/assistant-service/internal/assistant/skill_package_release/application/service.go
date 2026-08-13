package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/domain/ports"
)

const (
	EventActivated  = "SkillPackageReleaseActivated"
	EventRolledBack = "SkillPackageReleaseRolledBack"
)

type ActivateInput struct {
	PackageID        string
	ReleaseDigest    string
	ExpectedRevision int
	ActivatedBy      string
	// EvaluationReceipt 是激活的必备输入：必须证明轨迹回放评测在 exact
	// package digest 与 exact replay corpus asset digest 上通过。
	EvaluationReceipt model.EvaluationReceipt
}

type RollbackInput struct {
	PackageID        string
	ExpectedRevision int
	ActivatedBy      string
}

type ActivationResult struct {
	Activation model.Activation
	Replayed   bool
}

type StageResult struct {
	Release  model.Release
	Replayed bool
}

type Service struct {
	releases    ports.ReleaseStore
	activations ports.ActivationStore
	assets      ports.AssetReader
	signatures  SignatureVerifier
	resolver    *Resolver
	runtime     RuntimeIdentity
	now         func() time.Time
}

func NewService(
	releases ports.ReleaseStore,
	activations ports.ActivationStore,
	assets ports.AssetReader,
	signatures SignatureVerifier,
	runtime RuntimeIdentity,
	now func() time.Time,
) *Service {
	if releases == nil || activations == nil || assets == nil || signatures == nil {
		panic("assistant skill package service dependencies are required")
	}
	if now == nil {
		now = time.Now
	}
	return &Service{
		releases:    releases,
		activations: activations,
		assets:      assets,
		signatures:  signatures,
		resolver: NewResolver(
			releases,
			assets,
			activations,
			signatures,
			runtime,
		),
		runtime: runtime,
		now:     now,
	}
}

func (service *Service) Stage(
	ctx context.Context,
	commandID string,
	input model.Release,
) (StageResult, error) {
	commandID = strings.TrimSpace(commandID)
	if service == nil || commandID == "" {
		return StageResult{}, model.ErrInvalidRelease
	}
	release, err := model.Stage(input, service.now())
	if err != nil {
		return StageResult{}, err
	}
	if !model.RuntimeCompatible(
		release.RuntimeCompatibility,
		service.runtime.APIVersion,
		service.runtime.Version,
	) {
		return StageResult{}, model.ErrRuntimeMismatch
	}
	if err := service.signatures.Verify(ctx, release); err != nil {
		return StageResult{}, model.ErrSignatureInvalid
	}
	if err := verifyAssets(ctx, service.assets, release); err != nil {
		return StageResult{}, err
	}
	stored, replayed, err := service.releases.Stage(
		ctx,
		commandID,
		release.ReleaseDigest,
		release,
	)
	if err != nil {
		return StageResult{}, err
	}
	return StageResult{Release: stored, Replayed: replayed}, nil
}

func (service *Service) ResolveActive(
	ctx context.Context,
	packageID string,
) (ResolvedRelease, error) {
	if service == nil || service.resolver == nil {
		return ResolvedRelease{}, model.ErrActivationAbsent
	}
	return service.resolver.ResolveActive(ctx, packageID)
}

func (service *Service) ResolveRelease(
	ctx context.Context,
	packageID string,
	releaseDigest string,
) (ResolvedRelease, error) {
	if service == nil || service.resolver == nil {
		return ResolvedRelease{}, model.ErrReleaseNotFound
	}
	return service.resolver.ResolveRelease(ctx, packageID, releaseDigest)
}

func (service *Service) Activate(
	ctx context.Context,
	commandID string,
	input ActivateInput,
) (ActivationResult, error) {
	commandID = strings.TrimSpace(commandID)
	input.PackageID = strings.TrimSpace(input.PackageID)
	input.ReleaseDigest = strings.TrimSpace(input.ReleaseDigest)
	input.ActivatedBy = strings.TrimSpace(input.ActivatedBy)
	if service == nil || commandID == "" || input.PackageID == "" ||
		input.ReleaseDigest == "" || input.ExpectedRevision < 0 ||
		input.ActivatedBy == "" {
		return ActivationResult{}, model.ErrInvalidRelease
	}
	digest, err := commandDigest(input)
	if err != nil {
		return ActivationResult{}, err
	}
	if stored, replayed, readErr := service.activations.GetCommandResult(
		ctx,
		commandID,
		digest,
		input.PackageID,
	); readErr != nil || replayed {
		return ActivationResult{Activation: stored, Replayed: replayed}, readErr
	}
	resolved, err := service.resolver.ResolveRelease(
		ctx,
		input.PackageID,
		input.ReleaseDigest,
	)
	if err != nil {
		return ActivationResult{}, err
	}
	// 评测 receipt 必须与待激活 release 的 exact package/corpus digest 一致，
	// 否则 fail-closed：不允许拿旧版本或其他语料的评测结论激活新 release。
	if err := model.ValidateEvaluationReceipt(
		input.EvaluationReceipt,
		resolved.Release,
	); err != nil {
		return ActivationResult{}, err
	}
	current, found, err := service.activations.GetActivation(ctx, input.PackageID)
	if err != nil {
		return ActivationResult{}, err
	}
	if (!found && input.ExpectedRevision != 0) ||
		(found && current.Revision != input.ExpectedRevision) {
		return ActivationResult{}, model.ErrRevisionConflict
	}
	next := model.Activation{
		PackageID:           input.PackageID,
		ActiveReleaseDigest: input.ReleaseDigest,
		Revision:            input.ExpectedRevision + 1,
		ActivatedAt:         service.now().UTC(),
		ActivatedBy:         input.ActivatedBy,
	}
	if found {
		next.PreviousReleaseDigest = current.ActiveReleaseDigest
	}
	stored, replayed, err := service.activations.CommitActivation(
		ctx,
		commandID,
		digest,
		input.ExpectedRevision,
		next,
		EventActivated,
	)
	if err != nil {
		return ActivationResult{}, err
	}
	return ActivationResult{Activation: stored, Replayed: replayed}, nil
}

func (service *Service) Rollback(
	ctx context.Context,
	commandID string,
	input RollbackInput,
) (ActivationResult, error) {
	commandID = strings.TrimSpace(commandID)
	input.PackageID = strings.TrimSpace(input.PackageID)
	input.ActivatedBy = strings.TrimSpace(input.ActivatedBy)
	if service == nil || commandID == "" || input.PackageID == "" ||
		input.ExpectedRevision < 1 || input.ActivatedBy == "" {
		return ActivationResult{}, model.ErrInvalidRelease
	}
	digest, err := commandDigest(input)
	if err != nil {
		return ActivationResult{}, err
	}
	if stored, replayed, readErr := service.activations.GetCommandResult(
		ctx,
		commandID,
		digest,
		input.PackageID,
	); readErr != nil || replayed {
		return ActivationResult{Activation: stored, Replayed: replayed}, readErr
	}
	current, found, err := service.activations.GetActivation(ctx, input.PackageID)
	if err != nil {
		return ActivationResult{}, err
	}
	if !found {
		return ActivationResult{}, model.ErrActivationAbsent
	}
	if current.Revision != input.ExpectedRevision {
		return ActivationResult{}, model.ErrRevisionConflict
	}
	target := strings.TrimSpace(current.PreviousReleaseDigest)
	if target == "" {
		return ActivationResult{}, model.ErrReleaseNotFound
	}
	if _, err := service.resolver.ResolveRelease(ctx, input.PackageID, target); err != nil {
		return ActivationResult{}, err
	}
	next := model.Activation{
		PackageID:             input.PackageID,
		ActiveReleaseDigest:   target,
		PreviousReleaseDigest: current.ActiveReleaseDigest,
		Revision:              input.ExpectedRevision + 1,
		ActivatedAt:           service.now().UTC(),
		ActivatedBy:           input.ActivatedBy,
	}
	stored, replayed, err := service.activations.CommitActivation(
		ctx,
		commandID,
		digest,
		input.ExpectedRevision,
		next,
		EventRolledBack,
	)
	if err != nil {
		return ActivationResult{}, err
	}
	return ActivationResult{Activation: stored, Replayed: replayed}, nil
}

func verifyAssets(
	ctx context.Context,
	reader ports.AssetReader,
	release model.Release,
) error {
	for _, asset := range release.Assets {
		content, err := reader.ReadAsset(ctx, asset.Locator)
		if err != nil {
			return fmt.Errorf("%w: %v", model.ErrAssetUnavailable, err)
		}
		sum := sha256.Sum256(content)
		if "sha256:"+hex.EncodeToString(sum[:]) != asset.AssetDigest {
			return model.ErrAssetMismatch
		}
	}
	return nil
}

func commandDigest(input any) (string, error) {
	encoded, err := json.Marshal(input)
	if err != nil {
		return "", model.ErrInvalidRelease
	}
	sum := sha256.Sum256(encoded)
	return "sha256:" + hex.EncodeToString(sum[:]), nil
}
