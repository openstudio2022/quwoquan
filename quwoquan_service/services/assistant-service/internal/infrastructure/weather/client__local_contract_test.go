package weather

import (
	"context"
	"errors"
	"io"
	"net/http"
	"strings"
	"testing"

	"quwoquan_service/services/assistant-service/internal/application"
)

type roundTripFunc func(*http.Request) (*http.Response, error)

func (fn roundTripFunc) RoundTrip(request *http.Request) (*http.Response, error) {
	return fn(request)
}

func TestAuthorityReferencesPrioritizeNationalAndRegionalSources(t *testing.T) {
	summary := authoritySummary(
		"Hangzhou weather",
		"杭州，浙江",
		"杭州实时天气。",
	)
	if !strings.Contains(summary, "国家级气象服务入口") ||
		strings.Contains(summary, "MET Norway") {
		t.Fatalf("summary=%q", summary)
	}
	references := authorityReferences("Hangzhou weather", "杭州，浙江")
	if len(references) != 4 {
		t.Fatalf("references=%#v", references)
	}
	if references[3].Source != "zhejiang_meteorological_bureau" {
		t.Fatalf("regional source=%q", references[3].Source)
	}
}

func TestLookupDoesNotSelectUnboundMetNoFallback(t *testing.T) {
	var hosts []string
	client, err := New(Config{
		GeocodingURL: "https://geocoding-api.open-meteo.com/search",
		ForecastURL:  "https://api.open-meteo.com/forecast",
	}, &http.Client{Transport: roundTripFunc(func(request *http.Request) (*http.Response, error) {
		hosts = append(hosts, request.URL.Host)
		status := http.StatusServiceUnavailable
		body := "unavailable"
		if request.URL.Host == "geocoding-api.open-meteo.com" {
			status = http.StatusOK
			body = `{"results":[{"name":"杭州","latitude":30.2741,"longitude":120.1551,"timezone":"Asia/Shanghai"}]}`
		}
		return &http.Response{
			StatusCode: status,
			Body:       io.NopCloser(strings.NewReader(body)),
			Header:     make(http.Header),
		}, nil
	})})
	if err != nil {
		t.Fatalf("New() error = %v", err)
	}

	_, err = client.Lookup(
		context.Background(),
		application.ExternalSearchRequest{LocationSearchName: "杭州"},
	)
	var failure application.ProviderFailure
	if !errors.As(err, &failure) {
		t.Fatalf("error = %v, want ProviderFailure", err)
	}
	if failure.Capability != "weather" || failure.Reason != application.ProviderFailureUnavailable {
		t.Fatalf("failure = %+v", failure)
	}
	if len(hosts) != 3 {
		t.Fatalf("requests = %v, want geocoding plus two Open-Meteo forecast attempts", hosts)
	}
	for _, host := range hosts {
		if host != "geocoding-api.open-meteo.com" && host != "api.open-meteo.com" {
			t.Fatalf("unexpected implicit provider fallback host %q", host)
		}
	}
}
