package runtimemedia

import "time"

// ObjectStorageConfig is the provider-neutral environment composition consumed by
// the canonical content-service MediaUploadSession/MediaAsset implementation.
// It contains no upload aggregate or persistence behavior.
type ObjectStorageConfig struct {
	Endpoint             string
	Bucket               string
	Region               string
	AccessKeyID          string
	AccessKeySecret      string
	MediaDeliveryBaseURL string
	MediaUploadBaseURL   string
	CDNSignKey           string
	PresignTTL           time.Duration
	CDNTTL               time.Duration
}

// ObjectInfo is the object-storage readback used by the canonical content
// media gateways to verify uploaded bytes and immutable metadata.
type ObjectInfo struct {
	Exists      bool
	Sha256      string
	ContentType string
	Size        int64
	Metadata    map[string]string
}
