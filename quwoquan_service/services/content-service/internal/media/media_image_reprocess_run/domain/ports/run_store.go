package ports

import (
	"context"
	"time"

	reprocessmodel "quwoquan_service/services/content-service/internal/media/media_image_reprocess_run/domain/model"
)

type Commit struct {
	Aggregate        *reprocessmodel.Run
	ExpectedVersion  int64
	IdempotencyKey   string
	CommandName      string
	CommandDigest    string
	ReceiptExpiresAt time.Time
}

type CommitResult struct {
	Aggregate *reprocessmodel.Run
	Replayed  bool
}

// RunStore is the object-specific durable port for control-plane runs. It is
// intentionally not a generic workflow store.
type RunStore interface {
	LoadMediaImageReprocessRun(context.Context, string) (*reprocessmodel.Run, bool, error)
	FindMediaImageReprocessRunReceipt(
		context.Context,
		string,
		string,
		string,
	) (CommitResult, bool, error)
	CommitMediaImageReprocessRun(context.Context, Commit) (CommitResult, error)
	ListRunnableMediaImageReprocessRuns(
		context.Context,
		int,
	) ([]*reprocessmodel.Run, error)
	TryAcquireMediaImageReprocessRunLease(
		context.Context,
		string,
		string,
		time.Time,
		time.Duration,
	) (bool, error)
	RenewMediaImageReprocessRunLease(
		context.Context,
		string,
		string,
		time.Time,
		time.Duration,
	) (bool, error)
}
