package application

import "context"

// MediaObjectDeletionFence serializes account-closure object reclamation with
// creation of new MediaAsset references. The workflow owns this required port;
// cmd composition supplies the Mongo-backed media adapter.
type MediaObjectDeletionFence interface {
	ClaimUnreferencedDeletion(
		ctx context.Context,
		objectKey string,
		workID string,
	) (bool, error)
	MarkWorkDeleted(ctx context.Context, workID string) error
}
