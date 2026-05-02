package runtimemedia

import (
	"fmt"
	"strings"
)

// AssetKind identifies the logical media asset type exposed to services/apps.
type AssetKind string

const (
	AssetKindAvatarUser  AssetKind = "avatar_user"
	AssetKindAvatarGroup AssetKind = "avatar_group"
)

// AssetRef is the stable media reference shared across services and clients.
type AssetRef struct {
	AssetID   string    `json:"assetId"`
	AssetKind AssetKind `json:"assetKind"`
	OwnerType string    `json:"ownerType"`
	OwnerID   string    `json:"ownerId"`
	Version   int64     `json:"version"`
	ObjectKey string    `json:"objectKey"`
	URL       string    `json:"url"`
}

// NormalizeMediaCDNBase 将配置中的 CDN 入口规范为带 scheme 的 base URL（不含尾部 /）。
// 新配置必须显式携带 scheme，避免 App 收到不可访问的裸域名。
func NormalizeMediaCDNBase(raw string) string {
	s := strings.TrimSpace(raw)
	if s == "" {
		return ""
	}
	return strings.TrimRight(s, "/")
}

// BuildPublicMediaURL 基于「带 scheme 的 CDN base」与 objectKey 拼接可访问 URL。
func BuildPublicMediaURL(cdnBaseURL, objectKey string, version int64) string {
	base := NormalizeMediaCDNBase(cdnBaseURL)
	key := strings.TrimPrefix(strings.TrimSpace(objectKey), "/")
	if base == "" || key == "" {
		return ""
	}
	if !strings.Contains(base, "://") {
		return ""
	}
	u := fmt.Sprintf("%s/%s", strings.TrimRight(base, "/"), key)
	if version > 0 {
		u = fmt.Sprintf("%s?v=%d", u, version)
	}
	return u
}

// BuildAssetURL 已废弃：请使用 BuildPublicMediaURL；cdnDomain 若为裸域名将按 NormalizeMediaCDNBase 规则补全。
func BuildAssetURL(cdnDomain, objectKey string, version int64) string {
	raw := strings.TrimSpace(cdnDomain)
	if raw == "" {
		return ""
	}
	if !strings.Contains(raw, "://") {
		raw = "https://" + raw
	}
	return BuildPublicMediaURL(raw, objectKey, version)
}

func BuildAvatarObjectKey(ownerType, ownerID string, version int64, sourceHash string) string {
	cleanOwnerType := strings.TrimSpace(ownerType)
	if cleanOwnerType == "" {
		cleanOwnerType = "unknown"
	}
	cleanOwnerID := strings.TrimSpace(ownerID)
	if cleanOwnerID == "" {
		cleanOwnerID = "unknown"
	}
	cleanHash := strings.TrimSpace(sourceHash)
	if cleanHash == "" {
		cleanHash = "default"
	}
	if len(cleanHash) > 16 {
		cleanHash = cleanHash[:16]
	}
	return fmt.Sprintf(
		"media/avatar/%s/%s/v%d/%s.png",
		cleanOwnerType,
		cleanOwnerID,
		version,
		cleanHash,
	)
}

func BuildAvatarGroupAssetRef(
	conversationID string,
	assetID string,
	version int64,
	sourceHash string,
	cdnBaseURL string,
) AssetRef {
	objectKey := BuildAvatarObjectKey("conversation", conversationID, version, sourceHash)
	return AssetRef{
		AssetID:   assetID,
		AssetKind: AssetKindAvatarGroup,
		OwnerType: "conversation",
		OwnerID:   conversationID,
		Version:   version,
		ObjectKey: objectKey,
		URL:       BuildPublicMediaURL(cdnBaseURL, objectKey, version),
	}
}
