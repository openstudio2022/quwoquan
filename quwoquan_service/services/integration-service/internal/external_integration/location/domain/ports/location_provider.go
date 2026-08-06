package ports

import (
	"context"

	"quwoquan_service/services/integration-service/internal/external_integration/location/domain/model"
)

// NearbyLocationProvider 是供应商无关的附近位置查询边界。
type NearbyLocationProvider interface {
	Nearby(context.Context, model.NearbyQuery) ([]model.POI, error)
}

// POISearchProvider 是用户显式关键词与粗粒度中心的 POI 查询边界。
type POISearchProvider interface {
	Search(context.Context, model.SearchRequestFact) ([]model.POI, error)
}

// RouteReadProvider 只接收/返回 canonical route 类型。
type RouteReadProvider interface {
	ReadRoute(context.Context, model.RouteQuery) (model.Route, error)
}

// LocationProvider 保留现有附近与搜索 Provider 的组合端口；新装配必须分别选择
// POI 与 Route Adapter，禁止一个 Provider 失败后切换到另一个 Provider。
type LocationProvider interface {
	NearbyLocationProvider
	POISearchProvider
}
