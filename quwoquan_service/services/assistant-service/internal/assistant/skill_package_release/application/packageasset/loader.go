package skill

import (
	"context"
	"errors"
)

var ErrCatalogUnavailable = errors.New("active Skill package catalog is not configured")

type PackageReleaseIdentity struct {
	PackageID     string
	ReleaseDigest string
}

type packageReleaseContextKey struct{}

func WithPackageRelease(
	ctx context.Context,
	identity PackageReleaseIdentity,
) context.Context {
	return context.WithValue(ctx, packageReleaseContextKey{}, identity)
}

func PackageReleaseFromContext(
	ctx context.Context,
) (PackageReleaseIdentity, bool) {
	if ctx == nil {
		return PackageReleaseIdentity{}, false
	}
	identity, ok := ctx.Value(packageReleaseContextKey{}).(PackageReleaseIdentity)
	if !ok || identity.PackageID == "" || identity.ReleaseDigest == "" {
		return PackageReleaseIdentity{}, false
	}
	return identity, true
}

type Loader interface {
	Load(context.Context) ([]Manifest, error)
}
