package skill

import (
	"context"
	"encoding/json"
	"os"
)

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

type StaticLoader struct {
	Manifests []Manifest
}

func (l StaticLoader) Load(ctx context.Context) ([]Manifest, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	if len(l.Manifests) == 0 {
		return []Manifest{DefaultManifest()}, nil
	}
	return append([]Manifest{}, l.Manifests...), nil
}

type JSONFileLoader struct {
	Path string
}

func (l JSONFileLoader) Load(ctx context.Context) ([]Manifest, error) {
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	if l.Path == "" {
		return []Manifest{DefaultManifest()}, nil
	}
	raw, err := os.ReadFile(l.Path)
	if err != nil {
		return nil, err
	}
	var manifests []Manifest
	if err := json.Unmarshal(raw, &manifests); err != nil {
		return nil, err
	}
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	return manifests, nil
}
