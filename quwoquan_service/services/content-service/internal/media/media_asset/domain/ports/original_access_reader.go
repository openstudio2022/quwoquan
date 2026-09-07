package ports

import (
	"context"
	"strings"
)

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
	// SourceReleaseIDs 是 data release importer 以 $addToSet 累加的归属集合；
	// 同一 CAS 资产可以同时属于 previous active 与 candidate release。
	// UGC 上传资产为空。research principal 只按集合成员判定 active release
	// membership，单值诊断字段不得参与授权。
	SourceReleaseIDs []string
}

func (slice OriginalAccessSlice) BelongsToRelease(releaseID string) bool {
	releaseID = strings.TrimSpace(releaseID)
	if releaseID == "" {
		return false
	}
	for _, candidate := range slice.SourceReleaseIDs {
		if strings.TrimSpace(candidate) == releaseID {
			return true
		}
	}
	return false
}

type OriginalAccessReader interface {
	FindOriginalAccessAsset(context.Context, string) (OriginalAccessSlice, bool, error)
}
