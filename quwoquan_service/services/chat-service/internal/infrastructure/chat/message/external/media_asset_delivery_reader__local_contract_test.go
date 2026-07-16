package external

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
)

func TestMediaAssetDeliveryReaderUsesScopedCredentialAndStrictSlice(t *testing.T) {
	config := mediaDeliveryTokenConfig()
	credentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		config,
		"chat-service",
		[]string{"content.media.delivery.read"},
	)
	if err != nil {
		t.Fatal(err)
	}
	verifier, err := rtauth.NewHS256Verifier(config)
	if err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, request *http.Request) {
		if request.URL.Path != "/internal/v1/content/media/asset-audio:delivery-reference" ||
			request.URL.Query().Get("ownerPersonaId") != "persona-owner" {
			http.Error(w, "route drift", http.StatusBadRequest)
			return
		}
		token := strings.TrimPrefix(request.Header.Get("Authorization"), "Bearer ")
		claims, verifyErr := verifier.Verify(token)
		if verifyErr != nil || claims.Subject != "service:chat-service" ||
			claims.Scope != "content.media.delivery.read" {
			http.Error(w, "credential drift", http.StatusUnauthorized)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"assetId":"asset-audio","ownerPersonaId":"persona-owner","processingStatus":"ready","mediaType":"audio","contentType":"audio/mp4","fileSize":2048,"cdnUrl":"https://media.test/asset-audio"}`))
	}))
	defer server.Close()

	reader, err := NewMediaAssetDeliveryReader(server.URL, credentials, server.Client())
	if err != nil {
		t.Fatal(err)
	}
	asset, found, err := reader.ReadOwnedReadyAsset(context.Background(), "asset-audio", "persona-owner")
	if err != nil || !found {
		t.Fatalf("read owner-scoped MediaAsset found=%v err=%v", found, err)
	}
	if asset.AssetID != "asset-audio" || asset.OwnerPersonaID != "persona-owner" ||
		asset.ProcessingStatus != "ready" || asset.MediaType != "audio" ||
		asset.ContentType != "audio/mp4" || asset.FileSize != 2048 ||
		asset.DeliveryURL != "https://media.test/asset-audio" {
		t.Fatalf("MediaAsset delivery slice drift: %#v", asset)
	}
}

func TestMediaAssetDeliveryReaderFailsClosed(t *testing.T) {
	config := mediaDeliveryTokenConfig()
	credentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		config,
		"chat-service",
		[]string{"content.media.delivery.read"},
	)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := NewMediaAssetDeliveryReader("", credentials, nil); err == nil {
		t.Fatal("empty content-service URL must fail")
	}
	if _, err := NewMediaAssetDeliveryReader("https://content.test?removed=1", credentials, nil); err == nil {
		t.Fatal("URL with query must fail")
	}
	if _, err := NewMediaAssetDeliveryReader("https://content.test", nil, nil); err == nil {
		t.Fatal("missing service credential provider must fail")
	}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, request *http.Request) {
		switch request.URL.Query().Get("ownerPersonaId") {
		case "persona-missing":
			w.WriteHeader(http.StatusNotFound)
		default:
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"assetId":"asset","ownerPersonaId":"persona-owner","processingStatus":"ready","mediaType":"image","contentType":"image/png","fileSize":10,"cdnUrl":"https://media.test/asset","objectKey":"must-not-pass"}`))
		}
	}))
	defer server.Close()
	reader, err := NewMediaAssetDeliveryReader(server.URL, credentials, server.Client())
	if err != nil {
		t.Fatal(err)
	}
	if _, found, err := reader.ReadOwnedReadyAsset(context.Background(), "asset", "persona-missing"); err != nil || found {
		t.Fatalf("missing asset found=%v err=%v", found, err)
	}
	if _, _, err := reader.ReadOwnedReadyAsset(context.Background(), "asset", "persona-owner"); err == nil {
		t.Fatal("storage-key-bearing response must fail strict decoding")
	}
}

func mediaDeliveryTokenConfig() rtauth.TokenConfig {
	return rtauth.TokenConfig{
		Secret: []byte("0123456789abcdef0123456789abcdef"),
		Issuer: "https://auth.quwoquan.test", Audience: "quwoquan-api",
		Type: rtauth.TokenTypeAccess, TokenVersion: 1,
		TTL: 5 * time.Minute, ClockSkew: 5 * time.Second,
	}
}
