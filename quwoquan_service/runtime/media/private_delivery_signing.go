package runtimemedia

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"net/url"
	"strings"
	"time"
)

// NormalizeMediaDeliveryOrigin validates the origin used for signed private
// object delivery. Role-specific public bases belong to public-slice routing
// and are deliberately rejected here.
func NormalizeMediaDeliveryOrigin(raw string) string {
	base := NormalizeMediaCDNBase(raw)
	if base == "" {
		return ""
	}
	parsed, err := url.Parse(base)
	if err != nil || (parsed.Path != "" && parsed.Path != "/") {
		return ""
	}
	return strings.TrimRight(base, "/")
}

// SignCDNURLUntil generates a deterministic signed private-object URL for an
// absolute expiration. Replayed grants retain their original expiry.
func SignCDNURLUntil(
	mediaDeliveryOrigin string,
	privateObjectKey string,
	signKey string,
	expiresAt time.Time,
) string {
	deliveryURL := buildPrivateMediaDeliveryURL(
		mediaDeliveryOrigin,
		privateObjectKey,
	)
	if deliveryURL == "" || strings.TrimSpace(signKey) == "" {
		return ""
	}
	parsed, err := url.Parse(deliveryURL)
	if err != nil {
		return ""
	}
	expires := expiresAt.UTC().Unix()
	signInput := fmt.Sprintf("%s-%d", parsed.EscapedPath(), expires)
	mac := hmac.New(sha256.New, []byte(signKey))
	_, _ = mac.Write([]byte(signInput))
	signature := hex.EncodeToString(mac.Sum(nil))
	return fmt.Sprintf("%s?sign=%s&t=%d", deliveryURL, signature, expires)
}

func buildPrivateMediaDeliveryURL(mediaDeliveryOrigin, rawKey string) string {
	origin := NormalizeMediaDeliveryOrigin(mediaDeliveryOrigin)
	key := normalizePrivateMediaObjectKey(rawKey)
	if origin == "" || key == "" {
		return ""
	}
	return origin + "/" + key
}

func normalizePrivateMediaObjectKey(raw string) string {
	key := strings.Trim(strings.TrimSpace(raw), "/")
	if key == "" ||
		strings.Contains(key, "..") ||
		strings.ContainsAny(key, "?#\\%") ||
		(!strings.HasPrefix(key, "media/objects/sha256/") &&
			!strings.HasPrefix(key, "media/processed/")) {
		return ""
	}
	for _, segment := range strings.Split(key, "/") {
		if !canonicalSliceSegment.MatchString(segment) {
			return ""
		}
	}
	return key
}
