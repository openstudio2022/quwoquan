package runtimemedia

import (
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"log/slog"
	"time"

	rterr "quwoquan_service/runtime/errors"
	runtimegovernance "quwoquan_service/runtime/governance"
	runtimeobservability "quwoquan_service/runtime/observability"
)

// OSSConfig holds the configuration for the OSS adapter.
type OSSConfig struct {
	Endpoint        string
	Bucket          string
	Region          string
	AccessKeyID     string
	AccessKeySecret string
	CDNDomain       string
	CDNSignKey      string
	PresignTTL      time.Duration
	CDNTTL          time.Duration
}

// SessionStore persists upload sessions (typically backed by MongoDB).
type SessionStore interface {
	Create(ctx context.Context, session *UploadSession) error
	FindByID(ctx context.Context, sessionID string) (*UploadSession, error)
	UpdateStatus(ctx context.Context, sessionID string, status string) error
}

// AssetStore persists completed media assets (typically backed by MongoDB).
type AssetStore interface {
	Create(ctx context.Context, asset *MediaAsset) error
	FindByID(ctx context.Context, assetID string) (*MediaAsset, error)
}

// OSSMediaStore implements MediaStore with OSS presigned URL uploads and CDN delivery.
type OSSMediaStore struct {
	config       OSSConfig
	sessions     SessionStore
	assets       AssetStore
	presigner    PresignClient
	logger       *runtimeobservability.IOAccessLogger
	circuitBreak *runtimegovernance.CircuitBreaker
}

// NewOSSMediaStore creates a production-ready MediaStore.
// If presigner is nil, falls back to StubPresignClient (dev-only).
func NewOSSMediaStore(
	config OSSConfig,
	sessions SessionStore,
	assets AssetStore,
	logger *runtimeobservability.IOAccessLogger,
	presigner PresignClient,
) *OSSMediaStore {
	if presigner == nil {
		presigner = StubPresignClient{}
	}
	return &OSSMediaStore{
		config:       config,
		sessions:     sessions,
		assets:       assets,
		presigner:    presigner,
		logger:       logger,
		circuitBreak: runtimegovernance.NewCircuitBreaker(5, 30*time.Second, slog.Default()),
	}
}

func (s *OSSMediaStore) InitUpload(ctx context.Context, opts InitUploadOpts) (*UploadSession, error) {
	if err := ValidateUpload(opts); err != nil {
		return nil, err
	}

	now := time.Now()
	sessionID := fmt.Sprintf("us_%d", now.UnixNano())
	ossKey := buildOSSKey(opts.Category, opts.OwnerID, sessionID, opts.FileName)

	presignURL, err := s.generatePresignURL(ctx, ossKey, opts.ContentType)
	if err != nil {
		return nil, err
	}

	session := &UploadSession{
		SessionID:   sessionID,
		Category:    opts.Category,
		OwnerID:     opts.OwnerID,
		FileName:    opts.FileName,
		ContentType: opts.ContentType,
		FileSize:    opts.FileSize,
		PresignURL:  presignURL,
		OSSKey:      ossKey,
		Status:      "pending",
		CreatedAt:   now,
		ExpiresAt:   now.Add(s.config.PresignTTL),
	}

	if err := s.sessions.Create(ctx, session); err != nil {
		return nil, err
	}

	s.logAccess("media.upload.init", "success", opts.OwnerID, 0, "")
	return session, nil
}

func (s *OSSMediaStore) CompleteUpload(ctx context.Context, sessionID string, opts CompleteUploadOpts) (*MediaAsset, error) {
	session, err := s.sessions.FindByID(ctx, sessionID)
	if err != nil {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "session_not_found"),
			"上传会话不存在", fmt.Sprintf("session %s not found", sessionID),
		)
	}

	if session.Status != "pending" {
		return nil, rterr.NewInvalidArgument(
			rterr.ModuleContent,
			"上传会话状态无效",
			fmt.Sprintf("session %s status is %s, expected pending", sessionID, session.Status),
		)
	}

	exists, _ := s.presigner.HeadObject(ctx, s.config.Bucket, session.OSSKey)
	if !exists {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "object_not_uploaded"),
			"文件尚未上传完成", fmt.Sprintf("object %s not found in bucket", session.OSSKey),
		)
	}

	cdnURL := s.buildCDNURL(session.OSSKey)

	asset := &MediaAsset{
		AssetID:     fmt.Sprintf("ma_%d", time.Now().UnixNano()),
		SessionID:   sessionID,
		Category:    session.Category,
		OwnerID:     session.OwnerID,
		FileName:    session.FileName,
		ContentType: session.ContentType,
		FileSize:    session.FileSize,
		OSSKey:      session.OSSKey,
		CDNURL:      cdnURL,
		DurationMs:  opts.DurationMs,
		Width:       opts.Width,
		Height:      opts.Height,
		Metadata:    opts.Metadata,
		CreatedAt:   time.Now(),
	}

	if err := s.assets.Create(ctx, asset); err != nil {
		return nil, err
	}

	if err := s.sessions.UpdateStatus(ctx, sessionID, "completed"); err != nil {
		return nil, err
	}

	s.logAccess("media.upload.complete", "success", session.OwnerID, 0, "")
	return asset, nil
}

func (s *OSSMediaStore) AbortUpload(ctx context.Context, sessionID string) error {
	session, err := s.sessions.FindByID(ctx, sessionID)
	if err != nil {
		return nil
	}
	if session.Status != "pending" {
		return nil
	}

	if err := s.sessions.UpdateStatus(ctx, sessionID, "aborted"); err != nil {
		return err
	}

	s.logAccess("media.upload.abort", "success", session.OwnerID, 0, "")
	return nil
}

func (s *OSSMediaStore) GetAsset(ctx context.Context, assetID string) (*MediaAsset, error) {
	asset, err := s.assets.FindByID(ctx, assetID)
	if err != nil {
		return nil, rterr.NewAppError(
			rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "asset_not_found"),
			"媒体资源不存在", fmt.Sprintf("asset %s not found", assetID),
		)
	}

	signed, err := s.SignURL(ctx, asset.OSSKey, s.config.CDNTTL)
	if err == nil {
		asset.CDNURL = signed
	}

	return asset, nil
}

func (s *OSSMediaStore) SignURL(_ context.Context, ossKey string, ttl time.Duration) (string, error) {
	return SignCDNURL(s.config.CDNDomain, ossKey, s.config.CDNSignKey, ttl), nil
}

func (s *OSSMediaStore) generatePresignURL(ctx context.Context, ossKey, contentType string) (string, error) {
	if !s.circuitBreak.Allow() {
		return "", rterr.NewUnavailable(rterr.ModuleContent, "OSS 服务暂时不可用", "circuit breaker open for OSS")
	}

	url, err := s.presigner.PresignPutObject(ctx, s.config.Bucket, ossKey, contentType, s.config.PresignTTL)
	if err != nil {
		s.circuitBreak.RecordFailure()
		return "", rterr.NewUnavailable(rterr.ModuleContent, "生成上传链接失败", fmt.Sprintf("presign failed: %v", err))
	}

	s.circuitBreak.RecordSuccess()
	return url, nil
}

func (s *OSSMediaStore) buildCDNURL(ossKey string) string {
	return fmt.Sprintf("https://%s/%s", s.config.CDNDomain, ossKey)
}

func (s *OSSMediaStore) logAccess(endpoint, status, userID string, durationMs int64, errCode string) {
	if s.logger == nil {
		return
	}
	_ = s.logger.Write(runtimeobservability.IOAccessLog{
		SchemaVersion: "1.0",
		Service:       "media",
		Timestamp:     time.Now().Format(time.RFC3339Nano),
		Origin:        "service.http",
		Direction:     "outbound",
		Endpoint:      endpoint,
		Status:        status,
		DurationMs:    durationMs,
		ErrorCode:     errCode,
		UserID:        userID,
	})
}

func buildOSSKey(category MediaCategory, ownerID, sessionID, fileName string) string {
	date := time.Now().Format("2006/01/02")
	return fmt.Sprintf("media/%s/%s/%s/%s_%s", category, date, ownerID, sessionID, fileName)
}

// SignCDNURL generates a signed CDN URL with HMAC-SHA256.
func SignCDNURL(cdnDomain, ossKey, signKey string, ttl time.Duration) string {
	expires := time.Now().Add(ttl).Unix()
	path := fmt.Sprintf("/%s", ossKey)
	signStr := fmt.Sprintf("%s-%d", path, expires)

	mac := hmac.New(sha256.New, []byte(signKey))
	mac.Write([]byte(signStr))
	sig := hex.EncodeToString(mac.Sum(nil))

	return fmt.Sprintf("https://%s%s?sign=%s&t=%d", cdnDomain, path, sig, expires)
}
