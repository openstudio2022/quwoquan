package media

import (
	"context"

	mediaports "quwoquan_service/services/content-service/internal/domain/media/ports"
)

type DataPorts struct {
	UploadSessions MediaUploadSessionDataPort
	Assets         MediaAssetDataPort
	OriginalAccess mediaports.MediaOriginalAccessAppendSink
}

type MediaUploadSessionDataPort interface {
	mediaports.MediaUploadSessionStore
	MediaUploadSessionOwnerReader
}

type MediaAssetDataPort interface {
	mediaports.MediaAssetStore
	MediaAssetOwnerReader
	MediaAssetOriginalAccessReader
	MediaAssetPublicReader
}

// OriginalAccessPostVisibilityReader 是跨 Post 对象的窄读端口。实现必须
// 将已发布状态、审核、可见性和 viewer block 一起判定，不能用 owner 查询代替。
type OriginalAccessPostVisibilityReader interface {
	CanViewerAccessPublishedMedia(
		ctx context.Context,
		mediaAssetID string,
		viewerID string,
	) (bool, error)
}

func BindDataPorts(adapter interface {
	MediaUploadSessionDataPort
	MediaAssetDataPort
	mediaports.MediaOriginalAccessAppendSink
}) DataPorts {
	return DataPorts{
		UploadSessions: adapter,
		Assets:         adapter,
		OriginalAccess: adapter,
	}
}
