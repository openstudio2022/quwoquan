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

const defaultCDNDomain = "mock-cdn.example.com"

func BuildAssetURL(cdnDomain, objectKey string, version int64) string {
	normalizedDomain := strings.TrimSpace(cdnDomain)
	if normalizedDomain == "" {
		normalizedDomain = defaultCDNDomain
	}
	normalizedKey := strings.TrimPrefix(strings.TrimSpace(objectKey), "/")
	if version <= 0 {
		return fmt.Sprintf("https://%s/%s", normalizedDomain, normalizedKey)
	}
	return fmt.Sprintf("https://%s/%s?v=%d", normalizedDomain, normalizedKey, version)
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
	cdnDomain string,
) AssetRef {
	objectKey := BuildAvatarObjectKey("conversation", conversationID, version, sourceHash)
	return AssetRef{
		AssetID:   assetID,
		AssetKind: AssetKindAvatarGroup,
		OwnerType: "conversation",
		OwnerID:   conversationID,
		Version:   version,
		ObjectKey: objectKey,
		URL:       BuildAssetURL(cdnDomain, objectKey, version),
	}
}
