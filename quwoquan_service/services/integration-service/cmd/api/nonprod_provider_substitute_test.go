package main

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestNonprodProviderSubstituteExercisesProtocolSurfaces(t *testing.T) {
	substitute := &nonprodProviderSubstitute{counts: make(map[string]uint64)}
	substitute.ready.Store(true)
	server := httptest.NewServer(substitute.routes())
	defer server.Close()

	postJSON := func(path string, payload any) map[string]any {
		t.Helper()
		encoded, err := json.Marshal(payload)
		if err != nil {
			t.Fatal(err)
		}
		response, err := http.Post(
			server.URL+path,
			"application/json",
			bytes.NewReader(encoded),
		)
		if err != nil {
			t.Fatal(err)
		}
		defer response.Body.Close()
		if response.StatusCode != http.StatusOK {
			body, _ := io.ReadAll(response.Body)
			t.Fatalf("%s returned %d: %s", path, response.StatusCode, body)
		}
		var decoded map[string]any
		if err := json.NewDecoder(response.Body).Decode(&decoded); err != nil {
			t.Fatal(err)
		}
		return decoded
	}

	completion := postJSON("/v1/chat/completions", map[string]any{
		"messages": []map[string]string{{
			"role": "system", "content": "你是技能选择器",
		}},
	})
	choices, ok := completion["choices"].([]any)
	if !ok || len(choices) != 1 {
		t.Fatalf("completion response has no choice: %#v", completion)
	}

	embedding := postJSON("/v1/embeddings", map[string]any{
		"input": []string{"alpha", "beta"},
	})
	data, ok := embedding["data"].([]any)
	if !ok || len(data) != 2 {
		t.Fatalf("embedding response cardinality mismatch: %#v", embedding)
	}
	first, ok := data[0].(map[string]any)
	if !ok {
		t.Fatalf("embedding item is invalid: %#v", data[0])
	}
	vector, ok := first["embedding"].([]any)
	if !ok || len(vector) != 1536 {
		t.Fatalf("embedding vector dimension mismatch: %d", len(vector))
	}

	for _, path := range []string{
		"/search/html?q=west-lake",
		"/weather/geocoding?name=hangzhou",
		"/weather/forecast?latitude=30.2&longitude=120.1",
		"/finance/chart/000001.SZ",
	} {
		response, err := http.Get(server.URL + path)
		if err != nil {
			t.Fatal(err)
		}
		_ = response.Body.Close()
		if response.StatusCode != http.StatusOK {
			t.Fatalf("%s returned %d", path, response.StatusCode)
		}
	}

	receipt, err := http.Get(server.URL + "/receipts")
	if err != nil {
		t.Fatal(err)
	}
	defer receipt.Body.Close()
	var receiptBody struct {
		Calls map[string]uint64 `json:"calls"`
	}
	if err := json.NewDecoder(receipt.Body).Decode(&receiptBody); err != nil {
		t.Fatal(err)
	}
	for _, capability := range []string{
		"assistant.model.generation",
		"assistant.public.search",
		"assistant.weather.geocoding",
		"assistant.weather.forecast",
		"assistant.finance.quote",
		"content.embedding.generation",
	} {
		if receiptBody.Calls[capability] == 0 {
			t.Fatalf("missing substitute receipt for %s", capability)
		}
	}
}

func TestNonprodProviderSubstituteIsDisabledInProd(t *testing.T) {
	substitute, err := startNonprodProviderSubstitute("prod")
	if err != nil {
		t.Fatal(err)
	}
	if substitute != nil {
		t.Fatal("Prod must not start the nonprod Provider substitute listener")
	}
}
