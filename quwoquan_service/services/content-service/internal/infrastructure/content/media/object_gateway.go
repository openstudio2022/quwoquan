package media

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"mime"
	"path/filepath"
	"strings"
	"time"

	runtimemedia "quwoquan_service/runtime/media"
	mediaapp "quwoquan_service/services/content-service/internal/application/media"
)

type ObjectGatewayConfig struct {
	Bucket      string
	CDNDomain   string
	CDNSignKey  string
	DeliveryTTL time.Duration
}

type ObjectGateway struct {
	config ObjectGatewayConfig
	client runtimemedia.PresignClient
	now    func() time.Time
}

func NewObjectGateway(config ObjectGatewayConfig, client runtimemedia.PresignClient) (*ObjectGateway, error) {
	config.Bucket = strings.TrimSpace(config.Bucket)
	config.CDNDomain = strings.TrimSpace(strings.TrimPrefix(strings.TrimPrefix(config.CDNDomain, "https://"), "http://"))
	config.CDNSignKey = strings.TrimSpace(config.CDNSignKey)
	if config.Bucket == "" || config.CDNDomain == "" || config.CDNSignKey == "" || client == nil {
		return nil, errors.New("media object gateway requires bucket, CDN domain, CDN signing key and presign client")
	}
	if config.DeliveryTTL <= 0 {
		return nil, errors.New("media object gateway requires a positive delivery TTL")
	}
	return &ObjectGateway{config: config, client: client, now: time.Now}, nil
}

func (g *ObjectGateway) PrepareUpload(ctx context.Context, params mediaapp.PrepareUploadParams) (mediaapp.UploadGrant, error) {
	if err := g.validatePrepareUpload(params); err != nil {
		return mediaapp.UploadGrant{}, err
	}
	objectKey := temporaryObjectKey(params.OwnerID, params.SessionID, params.ContentType)
	uploadURL, err := g.UploadURL(ctx, objectKey, params.ContentType, params.ExpectedSHA256, params.ExpiresAt)
	if err != nil {
		return mediaapp.UploadGrant{}, err
	}
	return mediaapp.UploadGrant{ObjectKey: objectKey, UploadURL: uploadURL, ExpiresAt: params.ExpiresAt.UTC()}, nil
}

func (g *ObjectGateway) UploadURL(ctx context.Context, objectKey string, contentType string, expectedSHA256 string, expiresAt time.Time) (string, error) {
	ttl := time.Until(expiresAt.UTC())
	if g.now != nil {
		ttl = expiresAt.UTC().Sub(g.now().UTC())
	}
	if strings.TrimSpace(objectKey) == "" || strings.TrimSpace(contentType) == "" || ttl <= 0 {
		return "", errors.New("media upload grant is expired or incomplete")
	}
	return g.client.PresignPutObject(ctx, g.config.Bucket, objectKey, runtimemedia.PutObjectConstraints{
		ContentType: contentType,
		SHA256:      expectedSHA256,
	}, ttl)
}

func (g *ObjectGateway) CompleteUpload(ctx context.Context, params mediaapp.CompleteUploadParams) (mediaapp.CompletedUploadObject, error) {
	if err := validateCompleteUpload(params); err != nil {
		return mediaapp.CompletedUploadObject{}, err
	}
	info, err := g.client.StatObject(ctx, g.config.Bucket, params.ObjectKey)
	if err != nil {
		return mediaapp.CompletedUploadObject{}, fmt.Errorf("stat uploaded media object: %w", err)
	}
	if info == nil || !info.Exists {
		return mediaapp.CompletedUploadObject{}, errors.New("uploaded media object does not exist")
	}
	actualDigest := normalizeDigest(info.Sha256)
	if actualDigest == "" {
		return mediaapp.CompletedUploadObject{}, errors.New("uploaded media object has no SHA-256 checksum")
	}
	if actualDigest != normalizeDigest(params.ExpectedSHA256) {
		return mediaapp.CompletedUploadObject{}, errors.New("uploaded media object SHA-256 does not match the upload session")
	}
	if info.Size != params.FileSize {
		return mediaapp.CompletedUploadObject{}, fmt.Errorf("uploaded media object size %d does not match declared size %d", info.Size, params.FileSize)
	}
	if strings.TrimSpace(info.ContentType) != strings.TrimSpace(params.ContentType) {
		return mediaapp.CompletedUploadObject{}, errors.New("uploaded media object content type does not match the upload session")
	}
	finalObjectKey := contentAddressedObjectKey(actualDigest, params.ContentType)
	if finalObjectKey != params.ObjectKey {
		if err := g.client.PromoteObject(ctx, g.config.Bucket, params.ObjectKey, finalObjectKey, map[string]string{
			"sha256": actualDigest,
		}); err != nil {
			return mediaapp.CompletedUploadObject{}, fmt.Errorf("promote uploaded media object: %w", err)
		}
	}
	deliveryURL, err := g.DeliveryURL(ctx, finalObjectKey)
	if err != nil {
		return mediaapp.CompletedUploadObject{}, err
	}
	return mediaapp.CompletedUploadObject{ObjectKey: finalObjectKey, SHA256: actualDigest, DeliveryURL: deliveryURL}, nil
}

func (g *ObjectGateway) DeliveryURL(ctx context.Context, objectKey string) (string, error) {
	return g.DeliveryURLUntil(ctx, objectKey, g.now().UTC().Add(g.config.DeliveryTTL))
}

func (g *ObjectGateway) DeliveryURLUntil(_ context.Context, objectKey string, expiresAt time.Time) (string, error) {
	if strings.TrimSpace(objectKey) == "" {
		return "", errors.New("media delivery object key is required")
	}
	if !expiresAt.After(g.now().UTC()) {
		return "", errors.New("media delivery grant is expired")
	}
	return runtimemedia.SignCDNURLUntil(g.config.CDNDomain, objectKey, g.config.CDNSignKey, expiresAt), nil
}

func (g *ObjectGateway) validatePrepareUpload(params mediaapp.PrepareUploadParams) error {
	if strings.TrimSpace(params.SessionID) == "" || strings.TrimSpace(params.OwnerID) == "" || params.FileSize <= 0 || !params.ExpiresAt.After(g.now().UTC()) {
		return errors.New("media upload session identity, owner, positive file size and future expiration are required")
	}
	if !validMediaAndContentType(params.MediaType, params.ContentType) {
		return errors.New("media type and content type are inconsistent")
	}
	if !validDigest(params.ExpectedSHA256) {
		return errors.New("expectedSha256 must be a SHA-256 hex digest")
	}
	return nil
}

func validateCompleteUpload(params mediaapp.CompleteUploadParams) error {
	if strings.TrimSpace(params.ObjectKey) == "" || params.FileSize <= 0 || !validDigest(params.ExpectedSHA256) {
		return errors.New("media completion requires object key, positive file size and SHA-256")
	}
	if !validMediaAndContentType(params.MediaType, params.ContentType) {
		return errors.New("media type and content type are inconsistent")
	}
	return nil
}

func validMediaAndContentType(mediaType string, contentType string) bool {
	mediaType = strings.ToLower(strings.TrimSpace(mediaType))
	contentType = strings.ToLower(strings.TrimSpace(strings.Split(contentType, ";")[0]))
	switch mediaType {
	case "image", "video", "audio":
		return strings.HasPrefix(contentType, mediaType+"/")
	case "file":
		return contentType != "" && strings.Contains(contentType, "/")
	default:
		return false
	}
}

func validDigest(value string) bool {
	raw := strings.TrimPrefix(normalizeDigest(value), "sha256:")
	if len(raw) != sha256.Size*2 {
		return false
	}
	_, err := hex.DecodeString(raw)
	return err == nil
}

func normalizeDigest(value string) string {
	raw := strings.TrimPrefix(strings.ToLower(strings.TrimSpace(value)), "sha256:")
	if raw == "" {
		return ""
	}
	return "sha256:" + raw
}

func temporaryObjectKey(ownerID string, sessionID string, contentType string) string {
	ownerDigest := sha256.Sum256([]byte(strings.TrimSpace(ownerID)))
	return fmt.Sprintf("uploads/%s/%s%s", hex.EncodeToString(ownerDigest[:8]), strings.TrimSpace(sessionID), contentTypeExtension(contentType))
}

func contentAddressedObjectKey(digest string, contentType string) string {
	raw := strings.TrimPrefix(normalizeDigest(digest), "sha256:")
	return fmt.Sprintf("media/objects/sha256/%s/%s/%s%s", raw[:2], raw[2:4], raw, contentTypeExtension(contentType))
}

func contentTypeExtension(contentType string) string {
	extensions, _ := mime.ExtensionsByType(strings.TrimSpace(strings.Split(contentType, ";")[0]))
	if len(extensions) > 0 {
		return strings.ToLower(extensions[0])
	}
	if extension := filepath.Ext(contentType); extension != "" {
		return strings.ToLower(extension)
	}
	return ".bin"
}
