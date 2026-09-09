package ports

import "context"

// OriginalAccessSlice is the minimum MediaAsset projection required by the
// MediaOriginalAccessFact decision service. Object-storage keys never cross an
// HTTP boundary; this is an internal typed port between canonical objects.
type OriginalAccessSlice struct {
	AssetID          string
	OwnerID          string
	ObjectKey        string
	MediaType        string
	MimeType         string
	FileSize         int64
	ProcessingStatus string
	AccessPolicy     string
}

type OriginalAccessReader interface {
	FindOriginalAccessAsset(context.Context, string) (OriginalAccessSlice, bool, error)
}
