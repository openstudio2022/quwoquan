package runtimemedia

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"time"
)

// CDNConfig holds CDN signing parameters.
type CDNConfig struct {
	Domain  string
	SignKey string
	TTL     time.Duration
}

// NewCDNSigner creates a CDNSigner with the given config.
func NewCDNSigner(cfg CDNConfig) *CDNSigner {
	return &CDNSigner{cfg: cfg}
}

// CDNSigner generates time-limited signed CDN URLs.
type CDNSigner struct {
	cfg CDNConfig
}

// Sign returns a signed URL for the given OSS key, valid for cfg.TTL.
func (s *CDNSigner) Sign(ossKey string) string {
	return s.SignWithTTL(ossKey, s.cfg.TTL)
}

// SignWithTTL returns a signed URL with a custom TTL.
func (s *CDNSigner) SignWithTTL(ossKey string, ttl time.Duration) string {
	return generateSignedURL(s.cfg.Domain, ossKey, s.cfg.SignKey, ttl)
}

func generateSignedURL(domain, ossKey, signKey string, ttl time.Duration) string {
	expires := time.Now().Add(ttl).Unix()
	path := "/" + ossKey
	payload := fmt.Sprintf("%s-%d", path, expires)

	mac := hmac.New(sha256.New, []byte(signKey))
	mac.Write([]byte(payload))
	signature := hex.EncodeToString(mac.Sum(nil))

	return fmt.Sprintf("https://%s%s?sign=%s&t=%d", domain, path, signature, expires)
}
