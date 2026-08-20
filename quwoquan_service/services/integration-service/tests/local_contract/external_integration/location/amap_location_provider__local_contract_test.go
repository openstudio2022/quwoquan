package local_contract

import (
	"context"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"

	locationgenerated "quwoquan_service/services/integration-service/generated/external_integration/location"
	"quwoquan_service/services/integration-service/internal/external_integration/location/domain/model"
	"quwoquan_service/services/integration-service/internal/external_integration/location/infrastructure/provider"
	"quwoquan_service/services/integration-service/internal/external_integration/location/infrastructure/providerbinding"
)

func TestAMapNearbyMapsRegeoPOIsToCanonicalModel(t *testing.T) {
	var method, path string
	var query url.Values
	upstream := httptest.NewTLSServer(http.HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			method, path, query = r.Method, r.URL.Path, r.URL.Query()
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"status":"1","regeocode":{"pois":[` +
				`{"id":"B0FF01","name":"Cafe","address":"No.1 Road",` +
				`"distance":"120","location":"104.130000,30.120000","adcode":"510107"},` +
				`{"id":"B0FF02","name":"Bar","address":"No.2 Road",` +
				`"distance":"250","location":"104.140000,30.130000","adcode":"510107"}` +
				`]}}`))
		},
	))
	t.Cleanup(upstream.Close)

	client := provider.NewAMapClient(upstream.URL+"/", "test-key", upstream.Client())
	items, err := client.Nearby(context.Background(), model.NearbyQuery{
		Lat:          30.12,
		Lng:          104.13,
		RadiusMeters: 500,
		Limit:        1,
	})
	if err != nil {
		t.Fatalf("Nearby() error = %v", err)
	}
	if method != http.MethodGet || path != "/v3/geocode/regeo" {
		t.Fatalf("unexpected AMap request: %s %s", method, path)
	}
	// 高德 regeo 的 location 是 lng,lat，百度 reverse_geocoding 是 lat,lng。
	// 两个厂商适配器结构几乎相同，只有钉住线序才能挡住互相拷贝时的经纬度对调。
	if got := query.Get("location"); got != "104.130000,30.120000" {
		t.Fatalf("location wire order = %q, want lng,lat", got)
	}
	if query.Get("key") != "test-key" ||
		query.Get("extensions") != "all" ||
		query.Get("radius") != "500" {
		t.Fatalf("vendor query = %v", query)
	}
	// Limit 是领域侧硬上限：厂商多返回的条目必须在 adapter 内截断，
	// 否则调用方拿到的条数与它声明的分页容量不一致。
	if len(items) != 1 {
		t.Fatalf("Nearby() len = %d, want 1", len(items))
	}
	want := model.POI{
		ID:             "B0FF01",
		Name:           "Cafe",
		Address:        "No.1 Road",
		Latitude:       30.12,
		Longitude:      104.13,
		DistanceMeters: 120,
		AdCode:         "510107",
	}
	if items[0] != want {
		t.Fatalf("canonical POI = %+v, want %+v", items[0], want)
	}
}

func TestAMapSearchMapsPlaceTextPOIsToCanonicalModel(t *testing.T) {
	var method, path string
	var query url.Values
	upstream := httptest.NewTLSServer(http.HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			method, path, query = r.Method, r.URL.Path, r.URL.Query()
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"status":"1","pois":[` +
				`{"id":"B0FF03","name":"Library","address":"No.3 Road",` +
				`"adcode":"510107","citycode":"028","location":"104.130000,30.120000"},` +
				`{"id":"B0FF04","name":"Broken","address":"No.4 Road",` +
				`"adcode":"510107","citycode":"028","location":"104.150000"}` +
				`]}}`))
		},
	))
	t.Cleanup(upstream.Close)

	client := provider.NewAMapClient(upstream.URL, "test-key", upstream.Client())
	items, err := client.Search(context.Background(), model.SearchRequestFact{
		Query:    "library",
		CityCode: "028",
		Lat:      30.12,
		Lng:      104.13,
		Limit:    5,
	})
	if err != nil {
		t.Fatalf("Search() error = %v", err)
	}
	if method != http.MethodGet || path != "/v3/place/text" {
		t.Fatalf("unexpected AMap request: %s %s", method, path)
	}
	if query.Get("keywords") != "library" ||
		query.Get("offset") != "5" ||
		query.Get("city") != "028" ||
		query.Get("location") != "104.130000,30.120000" {
		t.Fatalf("vendor query = %v", query)
	}
	if len(items) != 2 {
		t.Fatalf("Search() len = %d, want 2", len(items))
	}
	want := model.POI{
		ID:        "B0FF03",
		Name:      "Library",
		Address:   "No.3 Road",
		Latitude:  30.12,
		Longitude: 104.13,
		CityCode:  "028",
		AdCode:    "510107",
	}
	if items[0] != want {
		t.Fatalf("canonical POI = %+v, want %+v", items[0], want)
	}
	// 坐标串不成对时归零而不是继承上一条：坐标是「缺席」，把它塌陷成邻居的
	// 坐标会让端侧把一个 POI 画到另一个 POI 的位置上。
	if items[1].Latitude != 0 || items[1].Longitude != 0 {
		t.Fatalf("malformed coordinate = (%v,%v), want zero", items[1].Latitude, items[1].Longitude)
	}
}

func TestAMapSearchOmitsUnsetCityAndCenter(t *testing.T) {
	var query url.Values
	upstream := httptest.NewTLSServer(http.HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			query = r.URL.Query()
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"status":"1","pois":[]}`))
		},
	))
	t.Cleanup(upstream.Close)

	client := provider.NewAMapClient(upstream.URL, "test-key", upstream.Client())
	items, err := client.Search(context.Background(), model.SearchRequestFact{
		Query: "library",
		Limit: 5,
	})
	if err != nil {
		t.Fatalf("Search() error = %v", err)
	}
	// 空结果是「在场为空」，必须是长度为 0 的切片而不是 nil，
	// 否则上层无法区分「附近没有 POI」与「厂商没答」。
	if items == nil || len(items) != 0 {
		t.Fatalf("empty result = %#v, want empty slice", items)
	}
	if query.Has("city") || query.Has("location") {
		t.Fatalf("unset city/center leaked into vendor query: %v", query)
	}
}

func TestAMapFailsClosedWithoutVendorKey(t *testing.T) {
	reached := 0
	upstream := httptest.NewTLSServer(http.HandlerFunc(
		func(w http.ResponseWriter, _ *http.Request) {
			reached++
			_, _ = w.Write([]byte(`{"status":"1"}`))
		},
	))
	t.Cleanup(upstream.Close)

	client := provider.NewAMapClient(upstream.URL, "   ", upstream.Client())
	_, err := client.Nearby(context.Background(), model.NearbyQuery{Limit: 1})
	assertAppErrorCode(t, err, locationgenerated.ErrLocationProviderUnavailable.Error())
	_, err = client.Search(context.Background(), model.SearchRequestFact{Query: "cafe", Limit: 1})
	assertAppErrorCode(t, err, locationgenerated.ErrLocationProviderUnavailable.Error())
	// 缺凭据必须在出网前失败：否则厂商会记一次匿名调用并计费/风控。
	if reached != 0 {
		t.Fatalf("vendor requests without key = %d, want 0", reached)
	}
}

func TestAMapVendorFailureMapsToStructuredRecoveryWithoutLeak(t *testing.T) {
	tests := []struct {
		name   string
		status int
		body   string
	}{
		{
			name:   "http status",
			status: http.StatusBadGateway,
			body:   `vendor diagnostic must not escape`,
		},
		{
			name:   "invalid payload",
			status: http.StatusOK,
			body:   `{`,
		},
		{
			name:   "vendor business failure",
			status: http.StatusOK,
			body:   `{"status":"0","info":"vendor diagnostic must not escape"}`,
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			upstream := httptest.NewTLSServer(http.HandlerFunc(
				func(w http.ResponseWriter, _ *http.Request) {
					w.WriteHeader(test.status)
					_, _ = w.Write([]byte(test.body))
				},
			))
			t.Cleanup(upstream.Close)

			client := provider.NewAMapClient(upstream.URL, "test-key", upstream.Client())
			_, nearbyErr := client.Nearby(
				context.Background(),
				model.NearbyQuery{Limit: 1},
			)
			_, searchErr := client.Search(
				context.Background(),
				model.SearchRequestFact{Query: "cafe", Limit: 1},
			)
			for _, err := range []error{nearbyErr, searchErr} {
				assertAppErrorCode(
					t,
					err,
					locationgenerated.ErrLocationProviderUnavailable.Error(),
				)
				// 厂商诊断文本可能含配额、账号或内部主机名，只允许进内部日志。
				if strings.Contains(err.Error(), "vendor diagnostic") {
					t.Fatalf("vendor diagnostic leaked through adapter: %v", err)
				}
			}
		})
	}
}

func TestAMapTransportFailureMapsToStructuredRecovery(t *testing.T) {
	upstream := httptest.NewTLSServer(http.HandlerFunc(
		func(http.ResponseWriter, *http.Request) {},
	))
	httpClient := upstream.Client()
	baseURL := upstream.URL
	upstream.Close()

	client := provider.NewAMapClient(baseURL, "test-key", httpClient)
	_, err := client.Nearby(context.Background(), model.NearbyQuery{Limit: 1})
	assertAppErrorCode(t, err, locationgenerated.ErrLocationProviderUnavailable.Error())
	// 传输层错误带着 dial 目标与端口，泄漏即暴露内网拓扑。
	if strings.Contains(err.Error(), baseURL) {
		t.Fatalf("transport endpoint leaked through adapter: %v", err)
	}
}

func TestNewLocationProviderBuildsAMapAdapterOnlyWithItsOwnSecret(t *testing.T) {
	binding := providerbinding.ResolvedLocationBinding{
		AdapterID: provider.LocationAdapterAMapID,
		Endpoints: map[string]string{"base": "https://restapi.amap.example.test"},
		Secrets:   map[string]string{"INTEGRATION_LOCATION_BAIDU_AK": "test-ak"},
	}
	// 材料键按厂商隔离：拿百度的 AK 装配高德必须失败，
	// 否则一次 Binding 写错会让请求带着另一家的凭据出网。
	if _, err := provider.NewLocationProvider(binding, &http.Client{}); err == nil {
		t.Fatal("AMap adapter without its own secret must fail closed")
	}

	binding.Secrets = map[string]string{"INTEGRATION_LOCATION_AMAP_KEY": "test-key"}
	resolved, err := provider.NewLocationProvider(binding, &http.Client{})
	if err != nil {
		t.Fatalf("NewLocationProvider() error = %v", err)
	}
	if _, ok := resolved.(*provider.AMapClient); !ok {
		t.Fatalf("provider type = %T, want *provider.AMapClient", resolved)
	}
}
