package runtimemedia

import (
	"context"
	"time"
)

// MediaCategory partitions upload policies and OSS bucket paths.
type MediaCategory string

const (
	CategoryChatVoice MediaCategory = "chat_voice"
	CategoryChatImage MediaCategory = "chat_image"
	CategoryChatVideo MediaCategory = "chat_video"
	CategoryChatFile  MediaCategory = "chat_file"
	CategoryPost      MediaCategory = "post"
	CategoryAvatar    MediaCategory = "avatar"
	CategoryCircle    MediaCategory = "circle"
)

// UploadSession represents an in-progress upload.
type UploadSession struct {
	SessionID   string        `json:"sessionId" bson:"_id"`
	Category    MediaCategory `json:"category" bson:"category"`
	OwnerID     string        `json:"ownerId" bson:"ownerId"`
	FileName    string        `json:"fileName" bson:"fileName"`
	ContentType string        `json:"contentType" bson:"contentType"`
	FileSize    int64         `json:"fileSize" bson:"fileSize"`
	PresignURL  string        `json:"presignUrl" bson:"-"`
	OSSKey      string        `json:"ossKey" bson:"ossKey"`
	Status      string        `json:"status" bson:"status"` // pending | completed | aborted
	CreatedAt   time.Time     `json:"createdAt" bson:"createdAt"`
	ExpiresAt   time.Time     `json:"expiresAt" bson:"expiresAt"`
}

// MediaAsset is a completed, CDN-ready media resource.
type MediaAsset struct {
	AssetID     string        `json:"assetId" bson:"_id"`
	SessionID   string        `json:"sessionId" bson:"sessionId"`
	Category    MediaCategory `json:"category" bson:"category"`
	OwnerID     string        `json:"ownerId" bson:"ownerId"`
	FileName    string        `json:"fileName" bson:"fileName"`
	ContentType string        `json:"contentType" bson:"contentType"`
	FileSize    int64         `json:"fileSize" bson:"fileSize"`
	OSSKey      string        `json:"ossKey" bson:"ossKey"`
	CDNURL      string        `json:"cdnUrl" bson:"cdnUrl"`
	DurationMs  int64         `json:"durationMs,omitempty" bson:"durationMs,omitempty"`
	Width       int           `json:"width,omitempty" bson:"width,omitempty"`
	Height      int           `json:"height,omitempty" bson:"height,omitempty"`
	Metadata    map[string]any `json:"metadata,omitempty" bson:"metadata,omitempty"`
	CreatedAt   time.Time     `json:"createdAt" bson:"createdAt"`
}

// InitUploadOpts carries the information needed to start an upload session.
type InitUploadOpts struct {
	Category    MediaCategory
	OwnerID     string
	FileName    string
	ContentType string
	FileSize    int64
}

// CompleteUploadOpts carries optional metadata set at completion time.
type CompleteUploadOpts struct {
	DurationMs int64
	Width      int
	Height     int
	Metadata   map[string]any
}

// MediaStore is the unified interface for media upload, storage, and retrieval.
type MediaStore interface {
	// InitUpload validates the upload against policy, creates a session, and
	// returns a presigned URL the client uses to upload directly to OSS.
	InitUpload(ctx context.Context, opts InitUploadOpts) (*UploadSession, error)

	// CompleteUpload marks the session as completed, persists the MediaAsset,
	// and returns the CDN URL.
	CompleteUpload(ctx context.Context, sessionID string, opts CompleteUploadOpts) (*MediaAsset, error)

	// AbortUpload marks the session as aborted and schedules cleanup.
	AbortUpload(ctx context.Context, sessionID string) error

	// GetAsset retrieves a MediaAsset by ID, returning a signed CDN URL.
	GetAsset(ctx context.Context, assetID string) (*MediaAsset, error)

	// SignURL generates a time-limited signed CDN URL for an existing asset.
	SignURL(ctx context.Context, ossKey string, ttl time.Duration) (string, error)
}
