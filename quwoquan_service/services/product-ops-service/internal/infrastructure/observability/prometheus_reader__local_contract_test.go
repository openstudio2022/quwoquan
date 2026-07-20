package observability

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestPrometheusReaderReturnsSingleVectorSample(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/v1/query" {
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
		if r.URL.Query().Get("query") != "up" {
			t.Fatalf("unexpected query: %q", r.URL.Query().Get("query"))
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"status":"success","data":{"resultType":"vector","result":[{"metric":{"job":"test"},"value":[1710000000,"0.125"]}]}}`))
	}))
	defer server.Close()

	reader, err := NewPrometheusReader(server.URL, server.Client())
	if err != nil {
		t.Fatalf("new reader: %v", err)
	}
	value, err := reader.Query(context.Background(), "up")
	if err != nil {
		t.Fatalf("query: %v", err)
	}
	if value != 0.125 {
		t.Fatalf("value = %v, want 0.125", value)
	}
}

func TestPrometheusReaderRejectsEmptyVector(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		_, _ = w.Write([]byte(`{"status":"success","data":{"resultType":"vector","result":[]}}`))
	}))
	defer server.Close()

	reader, err := NewPrometheusReader(server.URL, server.Client())
	if err != nil {
		t.Fatalf("new reader: %v", err)
	}
	if _, err := reader.Query(context.Background(), "up"); err == nil {
		t.Fatal("expected empty vector error")
	}
}
