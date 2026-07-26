package application

import (
	"context"

	rtsearch "quwoquan_service/runtime/search"
)

// XiaoquSearchReader 是 SearchXiaoquResults 的具名查询端口。
//
// Assistant 只负责把 canonical search-service 结果投影为回答引用，不在本域复制
// 召回、排序或合成候选数据。
type XiaoquSearchReader interface {
	Retrieve(
		ctx context.Context,
		query string,
		objectTypes []string,
		limit int,
	) (rtsearch.RetrieveResponse, error)
}

func WithXiaoquSearchReader(reader XiaoquSearchReader) AssistantServiceOption {
	return func(service *AssistantService) {
		service.xiaoquSearch = reader
	}
}
