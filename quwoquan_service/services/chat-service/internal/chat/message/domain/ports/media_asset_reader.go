package ports

import "context"

// MediaAssetDeliverySlice is the typed cross-context projection used by
// Message commands and reads. It deliberately excludes object keys and digests.
type MediaAssetDeliverySlice struct {
	AssetID          string
	OwnerPersonaID   string
	ProcessingStatus string
	MediaType        string
	ContentType      string
	FileSize         int64
	DeliveryURL      string
}

type MediaAssetDeliveryReader interface {
	ReadOwnedReadyAsset(
		context.Context,
		string,
		string,
	) (MediaAssetDeliverySlice, bool, error)
}
