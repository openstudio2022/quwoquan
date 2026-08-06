// spec_ref: specs/feature-tree/runtime/runtime-external-integration/provider-adapter-conformance-suite/spec.md#gwt-001
// readiness_case: weather-provider-protocol-local
package local_contract

import (
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/weather"
)

func TestWeatherProviderRejectsInsecureOrCredentialBearingEndpoints(t *testing.T) {
	for _, config := range []weather.Config{
		{
			GeocodingURL: "http://weather.example.test/geocode",
			ForecastURL:  "https://weather.example.test/forecast",
		},
		{
			GeocodingURL: "https://token@weather.example.test/geocode",
			ForecastURL:  "https://weather.example.test/forecast",
		},
	} {
		if _, err := weather.New(config, &http.Client{}); err == nil {
			t.Fatalf("unsafe weather config accepted: %+v", config)
		}
	}
}

func TestWeatherProviderProtocolConformance(t *testing.T) {
	t.Run("normalizes successful provider wire", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(
			w http.ResponseWriter,
			request *http.Request,
		) {
			w.Header().Set("Content-Type", "application/json")
			switch request.URL.Path {
			case "/geocode":
				_, _ = w.Write([]byte(
					`{"results":[{"name":"成都","latitude":30.67,"longitude":104.06,"admin1":"四川","timezone":"Asia/Shanghai"}]}`,
				))
			case "/forecast":
				_, _ = w.Write([]byte(
					`{"current":{"time":"2026-08-06T12:00","temperature_2m":31.2,"apparent_temperature":34.1,"relative_humidity_2m":66,"precipitation":0.2,"weather_code":2,"wind_speed_10m":8.3},"daily":{"time":["2026-08-06"],"weather_code":[2],"temperature_2m_max":[34],"temperature_2m_min":[25],"precipitation_probability_max":[40]}}`,
				))
			default:
				http.NotFound(w, request)
			}
		}))
		defer server.Close()

		client := newWeatherProtocolClient(t, server, time.Second)
		result, err := client.Lookup(t.Context(), ports.ExternalSearchRequest{
			Query:    "成都天气",
			Location: "成都",
		})
		if err != nil {
			t.Fatalf("weather lookup failed: %v", err)
		}
		if !strings.Contains(result.Summary, "成都，四川") ||
			!strings.Contains(result.Summary, "31.2°C") ||
			len(result.References) != 1 ||
			result.References[0].Source != "weather_public_provider" {
			t.Fatalf("normalized weather result=%+v", result)
		}
		for _, reference := range result.References {
			if strings.Contains(reference.URL, "?") ||
				strings.Contains(reference.URL, "成都") {
				t.Fatalf("weather evidence URL was not redacted: %+v", reference)
			}
		}
	})

	t.Run("maps 429 to unavailable without synthesized weather", func(t *testing.T) {
		var attempts atomic.Int32
		server := httptest.NewServer(http.HandlerFunc(func(
			w http.ResponseWriter,
			_ *http.Request,
		) {
			attempts.Add(1)
			http.Error(w, "rate limited", http.StatusTooManyRequests)
		}))
		defer server.Close()

		client := newWeatherProtocolClient(t, server, time.Second)
		_, err := client.Lookup(t.Context(), ports.ExternalSearchRequest{
			Query: "成都天气",
		})
		assertWeatherProviderFailure(
			t,
			err,
			ports.ProviderFailureUnavailable,
		)
		if attempts.Load() != 2 {
			t.Fatalf("429 attempts=%d, want bounded retry budget 2", attempts.Load())
		}
	})

	t.Run("maps malformed response to invalid response", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(
			w http.ResponseWriter,
			_ *http.Request,
		) {
			_, _ = w.Write([]byte(`{"results":`))
		}))
		defer server.Close()

		client := newWeatherProtocolClient(t, server, time.Second)
		_, err := client.Lookup(t.Context(), ports.ExternalSearchRequest{
			Query: "成都天气",
		})
		assertWeatherProviderFailure(
			t,
			err,
			ports.ProviderFailureInvalidResponse,
		)
	})

	t.Run("maps transport deadline to timeout", func(t *testing.T) {
		server := httptest.NewServer(http.HandlerFunc(func(
			w http.ResponseWriter,
			_ *http.Request,
		) {
			time.Sleep(50 * time.Millisecond)
			_, _ = w.Write([]byte(`{"results":[]}`))
		}))
		defer server.Close()

		client := newWeatherProtocolClient(t, server, 5*time.Millisecond)
		_, err := client.Lookup(t.Context(), ports.ExternalSearchRequest{
			Query: "成都天气",
		})
		assertWeatherProviderFailure(t, err, ports.ProviderFailureTimeout)
	})
}

func newWeatherProtocolClient(
	t *testing.T,
	server *httptest.Server,
	timeout time.Duration,
) *weather.Client {
	t.Helper()
	client, err := weather.New(
		weather.Config{
			GeocodingURL:  server.URL + "/geocode",
			ForecastURL:   server.URL + "/forecast",
			AllowInsecure: true,
			MaxAttempts:   2,
			RetryBackoff:  time.Millisecond,
		},
		&http.Client{Timeout: timeout},
	)
	if err != nil {
		t.Fatalf("construct weather protocol client: %v", err)
	}
	return client
}

func assertWeatherProviderFailure(
	t *testing.T,
	err error,
	reason ports.ProviderFailureReason,
) {
	t.Helper()
	var failure ports.ProviderFailure
	if !errors.As(err, &failure) || failure.Capability != "weather" ||
		failure.Reason != reason {
		t.Fatalf("weather provider error=%v, want reason=%s", err, reason)
	}
}
