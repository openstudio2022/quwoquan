package ports

import (
	"context"
	"time"

	mediamodel "quwoquan_service/services/content-service/internal/media/media_asset/domain/model"
)

// Creation is the MediaAsset-owned immutable state produced when a verified
// MediaUploadSession is completed. Callers may persist it, but must not derive
// MediaAsset defaults independently.
type Creation struct {
	ID               string
	Version          int64
	OwnerID          string
	SourceSessionID  string
	ObjectKey        string
	SHA256           string
	MediaType        string
	MimeType         string
	FileSize         int64
	CaptureMetadata  mediamodel.CaptureMetadata
	AccessPolicy     string
	ProcessingStatus string
	CoverStrategy    string
	CreatedAt        time.Time
	UpdatedAt        time.Time
}

type CreatedEvent struct {
	ID               string
	Type             string
	AggregateID      string
	AggregateVersion int64
	Payload          []byte
	OccurredAt       time.Time
}

// CreateCommit is appended inside the caller's durable unit of work. This lets
// MediaUploadSession and MediaAsset commit atomically while MediaAsset retains
// ownership of its document, receipt, outbox, and object-reference rules.
type CreateCommit struct {
	Asset            Creation
	IdempotencyKey   string
	CommandName      string
	CommandDigest    string
	ReceiptExpiresAt time.Time
	Event            CreatedEvent
}

type CreationAppender interface {
	AppendCreated(context.Context, CreateCommit) error
}
