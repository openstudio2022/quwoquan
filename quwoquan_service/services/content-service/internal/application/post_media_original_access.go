package application

import (
	"context"
	"fmt"
	"strconv"
	"strings"
	"time"

	rterr "quwoquan_service/runtime/errors"
	"quwoquan_service/runtime/repository"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
)

type RequestOriginalImageAccessInput struct {
	MediaID   string
	Purpose   string
	ViewerID  string
	SessionID string
}

type OriginalImageAccessResponse struct {
	MediaID     string         `json:"mediaId"`
	Status      string         `json:"status"`
	OriginalURL string         `json:"originalUrl,omitempty"`
	Format      string         `json:"format,omitempty"`
	SizeBytes   int64          `json:"sizeBytes,omitempty"`
	Width       int64          `json:"width,omitempty"`
	Height      int64          `json:"height,omitempty"`
	ExpiresAt   *time.Time     `json:"expiresAt,omitempty"`
	TtlSeconds  int            `json:"ttlSeconds,omitempty"`
	Watermark   map[string]any `json:"watermark,omitempty"`
	AuditID     string         `json:"auditId,omitempty"`
}

func (s *PostService) UpdateMediaAssetAccessPolicy(mediaID string, patch map[string]any) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	asset, ok := s.mediaAssets[strings.TrimSpace(mediaID)]
	if !ok {
		return false
	}
	if asset.AccessPolicy == nil {
		asset.AccessPolicy = map[string]any{}
	}
	for key, value := range patch {
		asset.AccessPolicy[key] = value
	}
	asset.UpdatedAt = time.Now().UTC()
	s.mediaAssets[asset.ID] = asset
	return true
}

func (s *PostService) RequestOriginalImageAccess(ctx context.Context, in RequestOriginalImageAccessInput) (*OriginalImageAccessResponse, error) {
	mediaID := strings.TrimSpace(in.MediaID)
	if mediaID == "" {
		return nil, rterr.NewAppError(rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "media_not_found"), "媒体资源不存在或已过期", "missing mediaId")
	}
	purpose := strings.ToLower(strings.TrimSpace(in.Purpose))
	if purpose == "" {
		purpose = "view"
	}
	if purpose != "view" && purpose != "save" {
		return nil, rterr.NewInvalidArgument(rterr.ModuleContent, "purpose 仅支持 view/save", "unsupported purpose: "+purpose)
	}
	s.mu.Lock()
	asset, ok := s.mediaAssets[mediaID]
	s.mu.Unlock()
	if !ok {
		return nil, rterr.NewAppError(rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "media_not_found"), "媒体资源不存在或已过期", "media not found")
	}
	if strings.ToLower(strings.TrimSpace(asset.Type)) != "image" && strings.ToLower(strings.TrimSpace(asset.Type)) != "video" {
		return nil, rterr.NewInvalidArgument(rterr.ModuleContent, "原图/原视频申请仅支持图片或视频类型资产", "unsupported asset type")
	}
	if !originalAccessPolicyAllows(asset, purpose) {
		return nil, rterr.NewAppError(rterr.NewCode(rterr.ModuleContent, rterr.KindUser, "original_access_denied"), "当前内容不支持查看或保存原图", "denied by policy")
	}
	now := time.Now().UTC()
	ttl := 300
	if raw, ok := asset.AccessPolicy["originalTtlSeconds"]; ok {
		if parsed := positiveIntFromAny(raw); parsed > 0 {
			ttl = parsed
		}
	}
	expiresAt := now.Add(time.Duration(ttl) * time.Second)
	base := strings.TrimSpace(asset.OriginUrl)
	if base == "" {
		base = strings.TrimSpace(asset.CdnUrl)
	}
	if base == "" {
		base = mediaURL(s.mediaCDNBase, mediaObjectKey(asset.AssetScope, asset.OwnerId, "archived", mediaID, asset.Type))
	}
	sep := "?"
	if strings.Contains(base, "?") {
		sep = "&"
	}
	signed := fmt.Sprintf("%s%sx-original=%s&x-purpose=%s&x-exp=%d&x-sig=%x", base, sep, mediaID, purpose, expiresAt.Unix(), len(base)+len(mediaID)+len(purpose))
	auditID := fmt.Sprintf("audit_orig_%d", now.UnixNano())
	if s.publisher != nil {
		_ = s.publisher.Publish(ctx, repository.DomainEvent{Type: "MediaOriginalAccessGranted", AggregateType: "MediaAsset", AggregateID: mediaID, Payload: map[string]any{"mediaId": mediaID, "purpose": purpose, "viewerId": in.ViewerID, "sessionId": in.SessionID, "auditId": auditID, "expiresAt": expiresAt.Format(time.RFC3339)}, OccurredAt: now.Format(time.RFC3339)})
	}
	return &OriginalImageAccessResponse{MediaID: mediaID, Status: "granted", OriginalURL: signed, Format: asset.MimeType, SizeBytes: asset.FileSizeBytes, Width: asset.Width, Height: asset.Height, ExpiresAt: &expiresAt, TtlSeconds: ttl, AuditID: auditID}, nil
}

func originalAccessPolicyAllows(asset postmodel.MediaAsset, purpose string) bool {
	if asset.AccessPolicy == nil {
		return true
	}
	if purpose == "save" {
		if v, ok := asset.AccessPolicy["allowOriginalSave"].(bool); ok {
			return v
		}
	}
	if purpose == "view" {
		if v, ok := asset.AccessPolicy["allowOriginalView"].(bool); ok {
			return v
		}
	}
	if v, ok := asset.AccessPolicy["originalAllowed"].(bool); ok {
		return v
	}
	return true
}

func positiveIntFromAny(v any) int {
	switch tv := v.(type) {
	case int:
		if tv > 0 {
			return tv
		}
	case int64:
		if tv > 0 {
			return int(tv)
		}
	case float64:
		if tv > 0 {
			return int(tv)
		}
	case string:
		if parsed, err := strconv.Atoi(strings.TrimSpace(tv)); err == nil && parsed > 0 {
			return parsed
		}
	}
	return 0
}
