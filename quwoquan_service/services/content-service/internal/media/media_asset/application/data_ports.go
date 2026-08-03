package media

import mediaports "quwoquan_service/services/content-service/internal/media/media_asset/domain/ports"

type DataPorts struct {
	Assets MediaAssetDataPort
}

type MediaAssetDataPort interface {
	mediaports.MediaAssetStore
	MediaAssetOwnerReader
	MediaAssetPublicReader
}

func BindDataPorts(adapter MediaAssetDataPort) DataPorts {
	return DataPorts{Assets: adapter}
}
