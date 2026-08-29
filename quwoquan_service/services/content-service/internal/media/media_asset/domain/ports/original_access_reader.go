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
	// SourceReleaseID 是 data release importer 投影写入的归属 release；
	// UGC 上传资产为空。research principal 的 grant 准入以它判定 active
	// research release membership（DEC-031）。
	SourceReleaseID string
}

type OriginalAccessReader interface {
	FindOriginalAccessAsset(context.Context, string) (OriginalAccessSlice, bool, error)
}
