package ports

import (
	"context"

	"quwoquan_service/services/integration-service/internal/domain/location/model"
)

// LocationProvider 是供应商无关的位置查询边界。
// 具体供应商协议只允许存在于 infrastructure adapter。
type LocationProvider interface {
	Nearby(context.Context, model.NearbyQuery) ([]model.POI, error)
	Search(context.Context, model.SearchQuery) ([]model.POI, error)
}
