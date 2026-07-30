package objectstorage

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"mime"
	"net/url"
	"path/filepath"
	"strings"
	"time"

	runtimemedia "quwoquan_service/runtime/media"
	sessionapp "quwoquan_service/services/content-service/internal/media/media_upload_session/application"
)

type Config struct {
	Bucket        string
	UploadBaseURL string
}

// Gateway is the MediaUploadSession object-storage adapter. It owns temporary
// upload grants and CAS promotion; MediaAsset consumers receive only the
// promoted object identity through the completed-session transaction.
type Gateway struct {
	config Config
	client runtimemedia.PresignClient
	now    func() time.Time
}

func NewGateway(config Config, client runtimemedia.PresignClient) (*Gateway, error) {
	config.Bucket = strings.TrimSpace(config.Bucket)
	config.UploadBaseURL = strings.TrimRight(strings.TrimSpace(config.UploadBaseURL), "/")
	if config.Bucket == "" || !isTrustedUploadURL(config.UploadBaseURL, config.UploadBaseURL) || client == nil {
		return nil, errors.New(
			"media upload session object gateway requires bucket, HTTPS upload base URL and presign client",
		)
	}
	return &Gateway{config: config, client: client, now: time.Now}, nil
}

func (g *Gateway) SetClock(now func() time.Time) {
	if now == nil {
		g.now = time.Now
		return
	}
	g.now = now
}

func (g *Gateway) PrepareUpload(ctx context.Context, params sessionapp.PrepareUploadParams) (sessionapp.UploadGrant, error) {
	if err := validatePrepare(params, g.now().UTC()); err != nil {
		return sessionapp.UploadGrant{}, err
	}
	key := temporaryObjectKey(params.OwnerID, params.SessionID, params.MimeType)
	url, err := g.UploadURL(ctx, key, params.MimeType, params.ExpectedSHA256, params.ExpiresAt)
	if err != nil {
		return sessionapp.UploadGrant{}, err
	}
	return sessionapp.UploadGrant{ObjectKey: key, UploadURL: url, ExpiresAt: params.ExpiresAt.UTC()}, nil
}

func (g *Gateway) UploadURL(ctx context.Context, objectKey, mimeType, expectedSHA256 string, expiresAt time.Time) (string, error) {
	ttl := expiresAt.UTC().Sub(g.now().UTC())
	if strings.TrimSpace(objectKey) == "" || strings.TrimSpace(mimeType) == "" || ttl <= 0 {
		return "", errors.New("media upload grant is expired or incomplete")
	}
	uploadURL, err := g.client.PresignPutObject(ctx, g.config.Bucket, objectKey, runtimemedia.PutObjectConstraints{
		ContentType: mimeType, SHA256: expectedSHA256,
	}, ttl)
	if err != nil {
		return "", err
	}
	if !isTrustedUploadURL(uploadURL, g.config.UploadBaseURL) {
		return "", errors.New("presigned media upload URL is outside the configured upload authority")
	}
	return uploadURL, nil
}

func isTrustedUploadURL(rawCandidate, rawBase string) bool {
	candidate, candidateErr := url.Parse(strings.TrimSpace(rawCandidate))
	base, baseErr := url.Parse(strings.TrimSpace(rawBase))
	if candidateErr != nil || baseErr != nil ||
		base.Scheme != "https" || base.Host == "" || base.User != nil ||
		base.RawQuery != "" || base.Fragment != "" ||
		candidate.Scheme != base.Scheme ||
		!strings.EqualFold(candidate.Hostname(), base.Hostname()) ||
		candidate.Port() != base.Port() ||
		candidate.User != nil || candidate.Fragment != "" {
		return false
	}
	basePath := strings.TrimRight(base.Path, "/")
	return basePath == "" ||
		candidate.Path == basePath ||
		strings.HasPrefix(candidate.Path, basePath+"/")
}

func (g *Gateway) CompleteUpload(ctx context.Context, params sessionapp.CompleteUploadParams) (sessionapp.CompletedObject, error) {
	if err := validateComplete(params); err != nil {
		return sessionapp.CompletedObject{}, err
	}
	finalKey := contentAddressedObjectKey(params.ExpectedSHA256, params.MimeType)
	info, err := g.client.StatObject(ctx, g.config.Bucket, params.ObjectKey)
	if err != nil {
		return sessionapp.CompletedObject{}, fmt.Errorf("stat uploaded media object: %w", err)
	}
	if info == nil || !info.Exists {
		if finalKey == params.ObjectKey {
			return sessionapp.CompletedObject{}, errors.New("uploaded media object does not exist")
		}
		info, err = g.client.StatObject(ctx, g.config.Bucket, finalKey)
		if err != nil {
			return sessionapp.CompletedObject{}, fmt.Errorf("stat promoted media object: %w", err)
		}
		if info == nil || !info.Exists {
			return sessionapp.CompletedObject{}, errors.New("uploaded media object does not exist")
		}
		if _, err := validateCompletedObject(info, params); err != nil {
			return sessionapp.CompletedObject{}, err
		}
		return g.completedObject(finalKey, params.ExpectedSHA256), nil
	}
	actualDigest, err := validateCompletedObject(info, params)
	if err != nil {
		return sessionapp.CompletedObject{}, err
	}
	if finalKey != params.ObjectKey {
		if err := g.client.PromoteObject(
			ctx,
			g.config.Bucket,
			params.ObjectKey,
			finalKey,
			map[string]string{
				"sha256":       actualDigest,
				"content-type": strings.TrimSpace(params.MimeType),
			},
		); err != nil {
			return sessionapp.CompletedObject{}, fmt.Errorf("promote uploaded media object: %w", err)
		}
	}
	return g.completedObject(finalKey, actualDigest), nil
}

func validateCompletedObject(
	info *runtimemedia.ObjectInfo,
	params sessionapp.CompleteUploadParams,
) (string, error) {
	actualDigest := normalizeDigest(info.Sha256)
	if actualDigest == "" || actualDigest != normalizeDigest(params.ExpectedSHA256) {
		return "", errors.New("uploaded media object checksum does not match the upload session")
	}
	if info.Size != params.FileSize ||
		strings.TrimSpace(info.ContentType) != strings.TrimSpace(params.MimeType) {
		return "", errors.New("uploaded media object metadata does not match the upload session")
	}
	return actualDigest, nil
}

func (g *Gateway) completedObject(
	objectKey string,
	digest string,
) sessionapp.CompletedObject {
	return sessionapp.CompletedObject{
		ObjectKey: objectKey,
		SHA256:    normalizeDigest(digest),
	}
}

func (g *Gateway) DeleteTemporaryUpload(ctx context.Context, objectKey string) error {
	key := strings.Trim(strings.TrimSpace(objectKey), "/")
	if !strings.HasPrefix(key, "uploads/") {
		return errors.New("temporary media cleanup requires an uploads/ object key")
	}
	if err := g.client.DeleteObject(ctx, g.config.Bucket, key); err != nil {
		return fmt.Errorf("delete temporary media upload: %w", err)
	}
	return nil
}

func validatePrepare(params sessionapp.PrepareUploadParams, now time.Time) error {
	if strings.TrimSpace(params.SessionID) == "" || strings.TrimSpace(params.OwnerID) == "" ||
		params.FileSize <= 0 || !params.ExpiresAt.After(now) || !validDigest(params.ExpectedSHA256) {
		return errors.New("media upload session identity, owner, file size, checksum and future expiration are required")
	}
	return validateType(params.MediaType, params.MimeType)
}

func validateComplete(params sessionapp.CompleteUploadParams) error {
	if strings.TrimSpace(params.ObjectKey) == "" || params.FileSize <= 0 || !validDigest(params.ExpectedSHA256) {
		return errors.New("media completion requires object key, file size and checksum")
	}
	return validateType(params.MediaType, params.MimeType)
}

func validateType(mediaType, mimeType string) error {
	mediaType = strings.ToLower(strings.TrimSpace(mediaType))
	mimeType = strings.ToLower(strings.TrimSpace(strings.Split(mimeType, ";")[0]))
	if mediaType == "file" && strings.Contains(mimeType, "/") {
		return nil
	}
	if (mediaType == "image" || mediaType == "video" || mediaType == "audio") && strings.HasPrefix(mimeType, mediaType+"/") {
		return nil
	}
	return errors.New("media type and content type are inconsistent")
}

func validDigest(value string) bool {
	value = strings.TrimPrefix(normalizeDigest(value), "sha256:")
	if len(value) != sha256.Size*2 {
		return false
	}
	_, err := hex.DecodeString(value)
	return err == nil
}

func normalizeDigest(value string) string {
	raw := strings.TrimPrefix(strings.ToLower(strings.TrimSpace(value)), "sha256:")
	if raw == "" {
		return ""
	}
	return "sha256:" + raw
}

func temporaryObjectKey(ownerID, sessionID, mimeType string) string {
	ownerDigest := sha256.Sum256([]byte(strings.TrimSpace(ownerID)))
	return fmt.Sprintf("uploads/%s/%s%s", hex.EncodeToString(ownerDigest[:8]), strings.TrimSpace(sessionID), extension(mimeType))
}

func contentAddressedObjectKey(digest, mimeType string) string {
	raw := strings.TrimPrefix(normalizeDigest(digest), "sha256:")
	return fmt.Sprintf("media/objects/sha256/%s/%s/%s%s", raw[:2], raw[2:4], raw, extension(mimeType))
}

func extension(mimeType string) string {
	extensions, _ := mime.ExtensionsByType(strings.TrimSpace(strings.Split(mimeType, ";")[0]))
	if len(extensions) > 0 {
		return strings.ToLower(extensions[0])
	}
	return filepath.Ext(mimeType)
}

var _ sessionapp.ObjectStore = (*Gateway)(nil)
