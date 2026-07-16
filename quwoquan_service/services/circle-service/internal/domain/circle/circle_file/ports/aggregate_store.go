package ports

import (
	"context"
	"encoding/json"
	"time"

	filemodel "quwoquan_service/services/circle-service/internal/domain/circle/circle_file/model"
)

type CommitRequest struct {
	Change           filemodel.ChangeSet
	ReceiptKey       string
	CommandDigest    string
	ReceiptExpiresAt time.Time
	StorageQuota     int64
}

type CommitReceipt struct {
	FileID   string
	Version  int64
	Status   filemodel.CircleFileStatus
	Replayed bool
}

type AggregateStore interface {
	Load(context.Context, string) (filemodel.CircleFile, bool, error)
	Commit(context.Context, CommitRequest) (CommitReceipt, error)
}

type MembershipPolicySlice struct {
	PersonaID string
	Role      string
	State     string
}

type CircleStoragePolicySlice struct {
	CircleID   string
	State      string
	QuotaBytes int64
}

type MediaAssetOwnerSlice struct {
	AssetID          string
	OwnerPersonaID   string
	ProcessingStatus string
	ContentType      string
	FileSize         int64
}

type PolicyReader interface {
	ReadCircleStoragePolicy(context.Context, string) (CircleStoragePolicySlice, bool, error)
	ReadCircleMembership(context.Context, string, string) (MembershipPolicySlice, bool, error)
	ReadGroupMembership(context.Context, string, string) (MembershipPolicySlice, bool, error)
	ReadParentFolder(context.Context, string, string) (filemodel.CircleFile, bool, error)
	ParentChainContains(context.Context, string, string, string) (bool, error)
}

type MediaAssetOwnerReader interface {
	ReadOwnedReadyAsset(context.Context, string, string) (MediaAssetOwnerSlice, bool, error)
}

type ListQuery struct {
	CircleID       string
	GroupID        string
	ParentFolderID string
	Cursor         string
	Limit          int
}

type PageSlice struct {
	Items  []filemodel.CircleFile
	Cursor string
}

type Reader interface {
	ReadFile(context.Context, string, string) (filemodel.CircleFile, bool, error)
	ListFiles(context.Context, ListQuery) (PageSlice, error)
}

type OutboxEvent struct {
	EventID          string
	EventType        string
	AggregateID      string
	AggregateVersion int64
	Payload          json.RawMessage
	OccurredAt       time.Time
	Checkpoint       string
}

type OutboxReader interface {
	ReadAfter(context.Context, string, int) ([]OutboxEvent, error)
}

type ProjectionCheckpointStore interface {
	LoadCheckpoint(context.Context, string) (string, error)
	SaveCheckpoint(context.Context, string, string) error
}

type OutboxPublisher interface {
	Publish(context.Context, OutboxEvent) error
}
