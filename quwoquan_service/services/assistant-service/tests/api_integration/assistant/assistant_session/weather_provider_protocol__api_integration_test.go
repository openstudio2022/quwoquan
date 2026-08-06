// spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-002
// readiness_case: weather-provider-protocol-api
package api_integration

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/weather"
)

func TestWeatherSelectedAdapterUsesBoundHTTPSProtocolAndNormalizesEvidence(
	t *testing.T,
) {
	calls := 0
	upstream := httptest.NewTLSServer(http.HandlerFunc(func(
		w http.ResponseWriter,
		request *http.Request,
	) {
		calls++
		w.Header().Set("Content-Type", "application/json")
		switch request.URL.Path {
		case "/v1/search":
			if request.URL.Query().Get("name") != "成都" {
				t.Fatalf("unexpected geocoding query: %s", request.URL.RawQuery)
			}
			_, _ = w.Write([]byte(
				`{"results":[{"name":"成都","latitude":30.67,"longitude":104.06,"admin1":"四川","timezone":"Asia/Shanghai"}]}`,
			))
		case "/v1/forecast":
			if request.URL.Query().Get("latitude") != "30.67" ||
				request.URL.Query().Get("longitude") != "104.06" {
				t.Fatalf("unexpected forecast query: %s", request.URL.RawQuery)
			}
			_, _ = w.Write([]byte(
				`{"current":{"time":"2026-08-06T12:00","temperature_2m":31.2,"apparent_temperature":34.1,"relative_humidity_2m":66,"precipitation":0.2,"weather_code":2,"wind_speed_10m":8.3},"daily":{"time":["2026-08-06"],"weather_code":[2],"temperature_2m_max":[34],"temperature_2m_min":[25],"precipitation_probability_max":[40]}}`,
			))
		default:
			http.NotFound(w, request)
		}
	}))
	t.Cleanup(upstream.Close)

	client, err := weather.New(
		weather.Config{
			GeocodingURL: upstream.URL + "/v1/search",
			ForecastURL:  upstream.URL + "/v1/forecast",
		},
		&http.Client{
			Timeout:   time.Second,
			Transport: upstream.Client().Transport,
		},
	)
	if err != nil {
		t.Fatalf("construct selected weather adapter: %v", err)
	}
	result, err := client.Lookup(t.Context(), ports.ExternalSearchRequest{
		Query:    "成都天气",
		Location: "成都",
	})
	if err != nil {
		t.Fatalf("lookup through selected weather adapter: %v", err)
	}
	if calls != 2 || !strings.Contains(result.Summary, "成都，四川") ||
		len(result.References) != 1 {
		t.Fatalf("weather calls=%d result=%+v", calls, result)
	}
	for _, reference := range result.References {
		if !strings.HasPrefix(reference.URL, upstream.URL) ||
			strings.Contains(reference.URL, "?") {
			t.Fatalf("weather evidence reference=%+v", reference)
		}
	}
}
