package media

import mediaports "quwoquan_service/services/content-service/internal/domain/media/ports"

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
	MediaAssetPublicReader
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
