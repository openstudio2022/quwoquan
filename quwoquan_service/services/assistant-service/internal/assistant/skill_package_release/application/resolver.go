package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"strings"
	"sync"

	"quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/domain/ports"
)

type ActivationReader interface {
	GetActivation(context.Context, string) (model.Activation, bool, error)
}

type SignatureVerifier interface {
	Verify(context.Context, model.Release) error
}

type RuntimeIdentity struct {
	APIVersion string
	Version    string
}

type ResolvedRelease struct {
	Release model.Release
	Assets  map[string][]byte
}

func (resolved ResolvedRelease) RequireCapabilities(
	requested []model.CapabilityGrant,
) error {
	granted := make(map[string]struct{}, len(resolved.Release.CapabilityGrants))
	for _, grant := range resolved.Release.CapabilityGrants {
		granted[grant.CapabilityID+"\x00"+grant.Scope] = struct{}{}
	}
	for _, request := range requested {
		key := strings.TrimSpace(request.CapabilityID) +
			"\x00" +
			strings.TrimSpace(request.Scope)
		if _, allowed := granted[key]; !allowed {
			return model.ErrCapabilityDenied
		}
	}
	return nil
}

type Resolver struct {
	releases    ports.ReleaseReader
	assets      ports.AssetReader
	activations ActivationReader
	signatures  SignatureVerifier
	runtime     RuntimeIdentity

	mu    sync.Mutex
	cache map[string]ResolvedRelease
}

func NewResolver(
	releases ports.ReleaseReader,
	assets ports.AssetReader,
	activations ActivationReader,
	signatures SignatureVerifier,
	runtime RuntimeIdentity,
) *Resolver {
	if releases == nil || assets == nil || activations == nil || signatures == nil ||
		strings.TrimSpace(runtime.APIVersion) == "" ||
		strings.TrimSpace(runtime.Version) == "" {
		panic("assistant skill package resolver dependencies are required")
	}
	return &Resolver{
		releases:    releases,
		assets:      assets,
		activations: activations,
		signatures:  signatures,
		runtime: RuntimeIdentity{
			APIVersion: strings.TrimSpace(runtime.APIVersion),
			Version:    strings.TrimSpace(runtime.Version),
		},
		cache: map[string]ResolvedRelease{},
	}
}

// ResolveActive deliberately reads the active pointer on every call. Only the
// fully verified immutable release is cached, keyed by its digest.
func (resolver *Resolver) ResolveActive(
	ctx context.Context,
	packageID string,
) (ResolvedRelease, error) {
	packageID = strings.TrimSpace(packageID)
	if packageID == "" || resolver == nil || resolver.activations == nil {
		return ResolvedRelease{}, model.ErrInvalidRelease
	}
	activation, found, err := resolver.activations.GetActivation(ctx, packageID)
	if err != nil {
		return ResolvedRelease{}, err
	}
	if !found || strings.TrimSpace(activation.ActiveReleaseDigest) == "" {
		return ResolvedRelease{}, model.ErrActivationAbsent
	}
	return resolver.ResolveRelease(ctx, packageID, activation.ActiveReleaseDigest)
}

func (resolver *Resolver) ResolveRelease(
	ctx context.Context,
	packageID string,
	releaseDigest string,
) (ResolvedRelease, error) {
	packageID = strings.TrimSpace(packageID)
	releaseDigest = strings.TrimSpace(releaseDigest)
	if packageID == "" || releaseDigest == "" || resolver == nil {
		return ResolvedRelease{}, model.ErrInvalidRelease
	}
	cacheKey := packageID + "\x00" + releaseDigest
	resolver.mu.Lock()
	defer resolver.mu.Unlock()
	if cached, found := resolver.cache[cacheKey]; found {
		return cloneResolved(cached), nil
	}

	release, found, err := resolver.releases.GetRelease(ctx, packageID, releaseDigest)
	if err != nil {
		return ResolvedRelease{}, err
	}
	if !found {
		return ResolvedRelease{}, model.ErrReleaseNotFound
	}
	normalized, err := model.Normalize(release)
	if err != nil {
		return ResolvedRelease{}, err
	}
	actualReleaseDigest, err := model.Digest(normalized)
	if err != nil {
		return ResolvedRelease{}, err
	}
	if normalized.PackageID != packageID ||
		normalized.ReleaseDigest != releaseDigest ||
		actualReleaseDigest != releaseDigest {
		return ResolvedRelease{}, model.ErrDigestMismatch
	}
	if !model.RuntimeCompatible(
		normalized.RuntimeCompatibility,
		resolver.runtime.APIVersion,
		resolver.runtime.Version,
	) {
		return ResolvedRelease{}, model.ErrRuntimeMismatch
	}
	if err := resolver.signatures.Verify(ctx, normalized); err != nil {
		return ResolvedRelease{}, fmt.Errorf("%w: %v", model.ErrSignatureInvalid, err)
	}
	resolved := ResolvedRelease{
		Release: normalized,
		Assets:  make(map[string][]byte, len(normalized.Assets)),
	}
	for _, asset := range normalized.Assets {
		content, readErr := resolver.assets.ReadAsset(ctx, asset.Locator)
		if readErr != nil {
			return ResolvedRelease{}, readErr
		}
		sum := sha256.Sum256(content)
		actual := "sha256:" + hex.EncodeToString(sum[:])
		if actual != asset.AssetDigest {
			return ResolvedRelease{}, fmt.Errorf(
				"%w: asset %s declared %s actual %s",
				model.ErrAssetMismatch,
				asset.AssetID,
				asset.AssetDigest,
				actual,
			)
		}
		resolved.Assets[asset.AssetID] = append([]byte(nil), content...)
	}
	resolver.cache[cacheKey] = cloneResolved(resolved)
	return cloneResolved(resolved), nil
}

func cloneResolved(value ResolvedRelease) ResolvedRelease {
	cloned := ResolvedRelease{
		Release: value.Release,
		Assets:  make(map[string][]byte, len(value.Assets)),
	}
	cloned.Release.Assets = append([]model.Asset(nil), value.Release.Assets...)
	cloned.Release.CapabilityGrants = append(
		[]model.CapabilityGrant(nil),
		value.Release.CapabilityGrants...,
	)
	for assetID, content := range value.Assets {
		cloned.Assets[assetID] = append([]byte(nil), content...)
	}
	return cloned
}
