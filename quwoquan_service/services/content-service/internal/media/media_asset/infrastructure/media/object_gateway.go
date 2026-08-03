package media

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	runtimemedia "quwoquan_service/runtime/media"
)

type ObjectGatewayConfig struct {
	Bucket               string
	MediaDeliveryBaseURL string
	CDNSignKey           string
	DeliveryTTL          time.Duration
}

type ObjectGateway struct {
	config ObjectGatewayConfig
	client runtimemedia.PresignClient
	now    func() time.Time
}

type prefixDeleteClient interface {
	DeletePrefix(context.Context, string, string) error
	HasObjectsWithPrefix(context.Context, string, string) (bool, error)
}

func NewObjectGateway(config ObjectGatewayConfig, client runtimemedia.PresignClient) (*ObjectGateway, error) {
	config.Bucket = strings.TrimSpace(config.Bucket)
	config.MediaDeliveryBaseURL = runtimemedia.NormalizeMediaDeliveryOrigin(
		config.MediaDeliveryBaseURL,
	)
	config.CDNSignKey = strings.TrimSpace(config.CDNSignKey)
	if config.Bucket == "" || config.MediaDeliveryBaseURL == "" || config.CDNSignKey == "" || client == nil {
		return nil, errors.New("media object gateway requires bucket, media delivery base URL, CDN signing key and presign client")
	}
	if config.DeliveryTTL <= 0 {
		return nil, errors.New("media object gateway requires a positive delivery TTL")
	}
	return &ObjectGateway{config: config, client: client, now: time.Now}, nil
}

// SetClock injects a deterministic clock while preserving the configured
// object-store client and delivery policy.
func (g *ObjectGateway) SetClock(now func() time.Time) {
	if now == nil {
		g.now = time.Now
		return
	}
	g.now = now
}

// ReclaimMediaArtifacts removes public delivery artifacts before private
// candidates. Callers supply only keys proven to belong to deleted
// MediaAssets and private keys with no surviving reference; this gateway
// still validates every namespace so corrupt work cannot widen deletion.
func (g *ObjectGateway) ReclaimMediaArtifacts(
	ctx context.Context,
	publicSliceKeys []string,
	publicPrefixes []string,
	privateObjectKeys []string,
	privatePrefixes []string,
) error {
	if g == nil || g.client == nil || g.config.Bucket == "" {
		return errors.New("media artifact cleanup gateway is not configured")
	}
	for _, key := range uniqueArtifactKeys(publicSliceKeys) {
		if !isPublicMediaSliceKey(key) {
			return errors.New("closed-account media cleanup received invalid public slice key")
		}
		if err := g.client.DeleteObject(
			ctx,
			g.config.Bucket,
			strings.Trim(strings.TrimSpace(key), "/"),
		); err != nil {
			return fmt.Errorf("delete closed-account public media slice: %w", err)
		}
	}
	if err := g.deleteArtifactPrefixes(ctx, publicPrefixes, true); err != nil {
		return err
	}
	for _, key := range uniqueArtifactKeys(privateObjectKeys) {
		if !isClosedAccountPrivateObjectKey(key) {
			return errors.New("closed-account media cleanup received invalid private object key")
		}
		if err := g.client.DeleteObject(
			ctx,
			g.config.Bucket,
			strings.Trim(strings.TrimSpace(key), "/"),
		); err != nil {
			return fmt.Errorf("delete unreferenced closed-account media object: %w", err)
		}
	}
	if err := g.deleteArtifactPrefixes(ctx, privatePrefixes, false); err != nil {
		return err
	}
	return g.verifyArtifactKeysAbsent(
		ctx,
		uniqueArtifactKeys(append(
			append([]string(nil), publicSliceKeys...),
			privateObjectKeys...,
		)),
	)
}

func (g *ObjectGateway) deleteArtifactPrefixes(
	ctx context.Context,
	prefixes []string,
	public bool,
) error {
	normalized := uniqueArtifactKeys(prefixes)
	if len(normalized) == 0 {
		return nil
	}
	deleter, ok := g.client.(prefixDeleteClient)
	if !ok {
		return errors.New("media artifact cleanup requires prefix deletion capability")
	}
	for _, prefix := range normalized {
		valid := isClosedAccountPrivatePrefix(prefix)
		if public {
			valid = isClosedAccountPublicPrefix(prefix)
		}
		if !valid {
			return errors.New("closed-account media cleanup received invalid object prefix")
		}
		if err := deleter.DeletePrefix(
			ctx,
			g.config.Bucket,
			strings.Trim(strings.TrimSpace(prefix), "/"),
		); err != nil {
			return fmt.Errorf("delete closed-account media artifact prefix: %w", err)
		}
		remaining, err := deleter.HasObjectsWithPrefix(
			ctx,
			g.config.Bucket,
			strings.Trim(strings.TrimSpace(prefix), "/"),
		)
		if err != nil {
			return fmt.Errorf(
				"verify closed-account media artifact prefix deletion: %w",
				err,
			)
		}
		if remaining {
			return errors.New(
				"closed-account media artifact prefix still contains objects",
			)
		}
	}
	return nil
}

func (g *ObjectGateway) verifyArtifactKeysAbsent(
	ctx context.Context,
	keys []string,
) error {
	for _, key := range keys {
		info, err := g.client.StatObject(
			ctx,
			g.config.Bucket,
			strings.Trim(strings.TrimSpace(key), "/"),
		)
		if err != nil {
			return fmt.Errorf(
				"verify closed-account media artifact deletion: %w",
				err,
			)
		}
		if info == nil {
			return errors.New(
				"verify closed-account media artifact deletion returned no state",
			)
		}
		if info.Exists {
			return errors.New(
				"closed-account media artifact still exists after deletion",
			)
		}
	}
	return nil
}

func isClosedAccountPublicPrefix(prefix string) bool {
	raw := strings.TrimSpace(prefix)
	key := strings.Trim(raw, "/")
	if !isPublicMediaSliceKey(key) || !strings.Contains(key, "/s/asset/") {
		return false
	}
	return strings.HasSuffix(raw, "/") &&
		!strings.Contains(key, "..") &&
		!strings.ContainsAny(key, "?#\\")
}

func isClosedAccountPrivateObjectKey(key string) bool {
	key = strings.Trim(strings.TrimSpace(key), "/")
	return !strings.Contains(key, "..") &&
		!strings.ContainsAny(key, "?#\\") &&
		(strings.HasPrefix(key, "uploads/") ||
			strings.HasPrefix(key, "media/objects/sha256/") ||
			strings.HasPrefix(key, "media/processed/"))
}

func isClosedAccountPrivatePrefix(prefix string) bool {
	raw := strings.TrimSpace(prefix)
	prefix = strings.Trim(raw, "/")
	return !strings.Contains(prefix, "..") &&
		!strings.ContainsAny(prefix, "?#\\") &&
		strings.HasSuffix(raw, "/") &&
		(strings.HasPrefix(prefix, "media/processed/image/") ||
			strings.HasPrefix(prefix, "media/processed/video/"))
}

func uniqueArtifactKeys(values []string) []string {
	seen := make(map[string]struct{}, len(values))
	result := make([]string, 0, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, exists := seen[value]; exists {
			continue
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	return result
}

// PublishPublicSlice copies a private CAS object to its canonical public
// delivery slice. The source remains authoritative internal storage; this
// method deliberately does not turn the public path into a CAS identity.
func (g *ObjectGateway) PublishPublicSlice(
	ctx context.Context,
	sourceObjectKey string,
	publicSliceKey string,
) error {
	source := strings.Trim(strings.TrimSpace(sourceObjectKey), "/")
	target := strings.Trim(strings.TrimSpace(publicSliceKey), "/")
	if source == "" || target == "" {
		return errors.New("public slice materialization requires source and target keys")
	}
	if isPublicMediaSliceKey(source) {
		return errors.New("public slice source must be a private CAS object key")
	}
	if !isPublicMediaSliceKey(target) {
		return errors.New("public slice target is invalid")
	}
	if err := g.client.CopyObject(ctx, g.config.Bucket, source, target); err != nil {
		return fmt.Errorf("materialize public media slice: %w", err)
	}
	return nil
}

func (g *ObjectGateway) DeliveryURL(ctx context.Context, objectKey string) (string, error) {
	return g.DeliveryURLUntil(ctx, objectKey, g.now().UTC().Add(g.config.DeliveryTTL))
}

func (g *ObjectGateway) DeliveryURLUntil(_ context.Context, objectKey string, expiresAt time.Time) (string, error) {
	key := strings.TrimSpace(objectKey)
	if key == "" {
		return "", errors.New("media delivery object key is required")
	}
	if !expiresAt.After(g.now().UTC()) {
		return "", errors.New("media delivery grant is expired")
	}
	// Public slice keys must not be signed as CAS object keys; build from the
	// injected HTTPS CDN base so path stays environment-stable.
	if isPublicMediaSliceKey(key) {
		version, ok := runtimemedia.PublicSliceVersion(key)
		if !ok {
			return "", errors.New("media delivery public slice key requires one path version")
		}
		deliveryURI := runtimemedia.BuildPublicMediaURL(
			g.config.MediaDeliveryBaseURL,
			key,
			version,
		)
		if deliveryURI == "" {
			return "", errors.New("media delivery public slice key requires HTTPS CDN domain")
		}
		return deliveryURI, nil
	}
	signedURL := runtimemedia.SignCDNURLUntil(
		g.config.MediaDeliveryBaseURL,
		key,
		g.config.CDNSignKey,
		expiresAt,
	)
	if signedURL == "" {
		return "", errors.New("media delivery private object key is invalid")
	}
	return signedURL, nil
}

func isPublicMediaSliceKey(key string) bool {
	trimmed := strings.Trim(key, "/")
	return strings.HasPrefix(trimmed, "media/avatar/s/") ||
		strings.HasPrefix(trimmed, "media/image/s/") ||
		strings.HasPrefix(trimmed, "media/video/s/") ||
		strings.HasPrefix(trimmed, "media/background/s/") ||
		strings.HasPrefix(trimmed, "media/attachment/s/")
}
