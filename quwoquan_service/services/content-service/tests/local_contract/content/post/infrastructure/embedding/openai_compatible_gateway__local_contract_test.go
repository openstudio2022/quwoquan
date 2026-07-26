package embedding_test

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/embedding"
	"strings"
	"testing"
	"time"

	runtimeconfig "quwoquan_service/runtime/config"
	rterr "quwoquan_service/runtime/errors"
)

func TestLoadOpenAICompatibleBindingFailsClosedWithoutEndpoint(t *testing.T) {
	const secret = "embedding-secret-must-not-leak"
	t.Setenv("CONTENT_EMBEDDING_ENDPOINT", "")
	t.Setenv(EmbeddingAPIKeyEnv, secret)

	_, err := LoadOpenAICompatibleBinding(
		"beta",
		runtimeconfig.EnvRuntimeConfigProvider{},
	)
	if err == nil {
		t.Fatal("LoadOpenAICompatibleBinding() accepted a missing endpoint")
	}
	assertRequiredDependencyError(t, err)
	if strings.Contains(err.Error(), secret) {
		t.Fatalf("binding failure leaked API key: %v", err)
	}
}

func TestOpenAICompatibleGatewayUsesTypedPort(t *testing.T) {
	const secret = "embedding-test-secret"
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, request *http.Request) {
		if got := request.Header.Get("Authorization"); got != "Bearer "+secret {
			t.Errorf("Authorization = %q", got)
		}
		if request.Method != http.MethodPost {
			t.Errorf("method = %s", request.Method)
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"data":[{"index":0,"embedding":[0.1,0.2]}]}`))
	}))
	defer server.Close()

	gateway, err := NewOpenAICompatibleGateway(
		OpenAICompatibleBinding{
			Endpoint: server.URL,
			APIKey:   secret,
			Model:    "test-embedding-model",
			Timeout:  time.Second,
		},
		WithHTTPClient(server.Client()),
	)
	if err != nil {
		t.Fatalf("NewOpenAICompatibleGateway() error = %v", err)
	}
	vector, err := gateway.Embed(context.Background(), "内容语义输入")
	if err != nil {
		t.Fatalf("Embed() error = %v", err)
	}
	if len(vector) != 2 || vector[0] != 0.1 || vector[1] != 0.2 {
		t.Fatalf("Embed() vector = %#v", vector)
	}
}

func TestOpenAICompatibleGatewayRedactsProviderFailure(t *testing.T) {
	const secret = "embedding-secret-must-not-leak"
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		http.Error(w, "provider diagnostic bearer "+secret, http.StatusBadGateway)
	}))
	defer server.Close()

	gateway, err := NewOpenAICompatibleGateway(
		OpenAICompatibleBinding{
			Endpoint: server.URL,
			APIKey:   secret,
			Model:    "test-embedding-model",
			Timeout:  time.Second,
		},
		WithHTTPClient(server.Client()),
	)
	if err != nil {
		t.Fatalf("NewOpenAICompatibleGateway() error = %v", err)
	}
	_, err = gateway.Embed(context.Background(), "内容语义输入")
	if err == nil {
		t.Fatal("Embed() accepted provider failure")
	}
	assertRequiredDependencyError(t, err)
	if strings.Contains(err.Error(), secret) {
		t.Fatalf("provider failure leaked API key: %v", err)
	}
}

func assertRequiredDependencyError(t *testing.T, err error) {
	t.Helper()
	var appError *rterr.AppError
	if !errors.As(err, &appError) {
		t.Fatalf("error is not Runtime AppError: %T %v", err, err)
	}
	if got := appError.Code.String(); got != "CONTENT.SYSTEM.required_dependency_unavailable" {
		t.Fatalf("runtime error code = %q", got)
	}
}
