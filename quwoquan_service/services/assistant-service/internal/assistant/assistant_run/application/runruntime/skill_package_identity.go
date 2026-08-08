package runruntime

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"strings"

	skillpkg "quwoquan_service/services/assistant-service/internal/assistant/skill_package_release/application/packageasset"
)

type SkillPackageIdentity struct {
	PackageID     string
	ReleaseDigest string
}

type SkillPackageIdentityResolver interface {
	ResolveActiveSkillPackage(context.Context) (string, string, error)
	ContainsSkillInFrozenPackage(context.Context, string) (bool, error)
}

type StaticSkillPackageIdentityResolver struct {
	PackageID     string
	ReleaseDigest string
}

func (resolver StaticSkillPackageIdentityResolver) ResolveActiveSkillPackage(
	ctx context.Context,
) (string, string, error) {
	if err := ctx.Err(); err != nil {
		return "", "", err
	}
	packageID := strings.TrimSpace(resolver.PackageID)
	digest := strings.TrimSpace(resolver.ReleaseDigest)
	if packageID == "" || !validSkillPackageDigest(digest) {
		return "", "", ErrSkillPackageUnavailable
	}
	return packageID, digest, nil
}

// ContainsSkillInFrozenPackage makes the static resolver an explicit synthetic
// package fixture: every non-empty Skill ID belongs to its one declared release.
// Production composition uses CatalogSource, which resolves real manifests.
func (resolver StaticSkillPackageIdentityResolver) ContainsSkillInFrozenPackage(
	ctx context.Context,
	skillID string,
) (bool, error) {
	if err := ctx.Err(); err != nil {
		return false, err
	}
	identity, frozen := skillpkg.PackageReleaseFromContext(ctx)
	if !frozen ||
		identity.PackageID != strings.TrimSpace(resolver.PackageID) ||
		identity.ReleaseDigest != strings.TrimSpace(resolver.ReleaseDigest) {
		return false, ErrSkillPackageUnavailable
	}
	return strings.TrimSpace(skillID) != "", nil
}

func validSkillPackageDigest(value string) bool {
	if len(value) != len("sha256:")+sha256.Size*2 ||
		!strings.HasPrefix(value, "sha256:") {
		return false
	}
	raw := strings.TrimPrefix(value, "sha256:")
	if raw != strings.ToLower(raw) {
		return false
	}
	_, err := hex.DecodeString(raw)
	return err == nil
}
