package ports

import (
	"context"
	"time"

	assetports "quwoquan_service/services/content-service/internal/media/media_asset/domain/ports"
	"quwoquan_service/services/content-service/internal/media/media_upload_session/domain/model"
)

type Event struct {
	ID               string
	Type             string
	AggregateType    string
	AggregateID      string
	AggregateVersion int64
	Payload          []byte
	OccurredAt       time.Time
}

type Receipt struct {
	Session               *model.Session
	AssetID               string
	AssetProcessingStatus string
	ObjectKey             string
	Replayed              bool
}

// CompleteCommit is the session-owned atomic boundary. The persistence adapter
// persists the completed session and invokes the MediaAsset-owned creation
// port in one transaction; Post never participates in this write path.
type CompleteCommit struct {
	Session          *model.Session
	ExpectedVersion  int64
	Asset            assetports.Creation
	IdempotencyKey   string
	CommandName      string
	CommandDigest    string
	ReceiptExpiresAt time.Time
	Events           []Event
}

type Commit struct {
	Session          *model.Session
	ExpectedVersion  int64
	IdempotencyKey   string
	CommandName      string
	CommandDigest    string
	ReceiptExpiresAt time.Time
	Events           []Event
}

type Store interface {
	Load(context.Context, string) (*model.Session, bool, error)
	FindForOwner(context.Context, string, string) (model.Snapshot, bool, error)
	FindReceipt(context.Context, string, string, string) (Receipt, bool, error)
	Commit(context.Context, Commit) (Receipt, error)
	Complete(context.Context, CompleteCommit) (Receipt, error)
}

// ObjectReferenceAuthorizer serializes MediaAsset creation against shared CAS
// object deletion. Implementations are composed in cmd from the post-owned
// mediaobjectfence adapter; this object must not import sibling infrastructure.
type ObjectReferenceAuthorizer interface {
	AllowReference(ctx context.Context, objectKey string) error
}
