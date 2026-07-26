package local_contract

import (
	"context"
	"net/http"
	"net/http/httptest"
	. "quwoquan_service/services/circle-service/internal/circle_management/circle_file/infrastructure/external"
	"strings"
	"testing"
	"time"

	rtauth "quwoquan_service/runtime/auth"
)

func TestMediaAssetOwnerReaderUsesShortLivedScopedCredentialAndStrictSlice(t *testing.T) {
	config := mediaReferenceTokenConfig()
	credentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		config, "circle-service", []string{"content.media.reference.read"},
	)
	if err != nil {
		t.Fatal(err)
	}
	verifier, err := rtauth.NewHS256Verifier(config)
	if err != nil {
		t.Fatal(err)
	}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, request *http.Request) {
		if request.URL.Path != "/internal/content/media/asset-ready:reference" ||
			request.URL.Query().Get("ownerPersonaId") != "persona-owner" {
			http.Error(w, "route drift", http.StatusBadRequest)
			return
		}
		token := strings.TrimPrefix(request.Header.Get("Authorization"), "Bearer ")
		claims, verifyErr := verifier.Verify(token)
		if verifyErr != nil || claims.Subject != "service:circle-service" ||
			claims.Scope != "content.media.reference.read" {
			http.Error(w, "credential drift", http.StatusUnauthorized)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"assetId":"asset-ready","ownerPersonaId":"persona-owner","processingStatus":"ready","contentType":"application/pdf","fileSize":2048}`))
	}))
	defer server.Close()

	reader, err := NewMediaAssetOwnerReader(server.URL, credentials, server.Client())
	if err != nil {
		t.Fatal(err)
	}
	asset, found, err := reader.ReadOwnedReadyAsset(context.Background(), "asset-ready", "persona-owner")
	if err != nil || !found {
		t.Fatalf("read owner-scoped MediaAsset found=%v err=%v", found, err)
	}
	if asset.AssetID != "asset-ready" || asset.OwnerPersonaID != "persona-owner" ||
		asset.ProcessingStatus != "ready" || asset.ContentType != "application/pdf" || asset.FileSize != 2048 {
		t.Fatalf("MediaAsset reference slice drift: %#v", asset)
	}
}

func TestMediaAssetOwnerReaderFailsClosed(t *testing.T) {
	config := mediaReferenceTokenConfig()
	credentials, err := rtauth.NewHS256ServiceAuthorizationProvider(
		config, "circle-service", []string{"content.media.reference.read"},
	)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := NewMediaAssetOwnerReader("", credentials, nil); err == nil {
		t.Fatal("relative or empty content-service URL must fail")
	}
	if _, err := NewMediaAssetOwnerReader("https://content.test", nil, nil); err == nil {
		t.Fatal("missing service credential provider must fail")
	}

	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, request *http.Request) {
		switch request.URL.Query().Get("ownerPersonaId") {
		case "persona-missing":
			w.WriteHeader(http.StatusNotFound)
		default:
			w.Header().Set("Content-Type", "application/json")
			_, _ = w.Write([]byte(`{"assetId":"asset","ownerPersonaId":"persona-owner","processingStatus":"processing","contentType":"image/jpeg","fileSize":10,"objectKey":"must-not-be-accepted"}`))
		}
	}))
	defer server.Close()
	reader, err := NewMediaAssetOwnerReader(server.URL, credentials, server.Client())
	if err != nil {
		t.Fatal(err)
	}
	if _, found, err := reader.ReadOwnedReadyAsset(context.Background(), "asset", "persona-missing"); err != nil || found {
		t.Fatalf("missing owner-scoped asset found=%v err=%v", found, err)
	}
	if _, _, err := reader.ReadOwnedReadyAsset(context.Background(), "asset", "persona-owner"); err == nil {
		t.Fatal("non-ready or storage-key-bearing response must fail strict decoding")
	}
}

func mediaReferenceTokenConfig() rtauth.TokenConfig {
	return rtauth.TokenConfig{
		Secret: []byte("0123456789abcdef0123456789abcdef"),
		Issuer: "https://auth.quwoquan.test", Audience: "quwoquan-api",
		Type: rtauth.TokenTypeAccess, TokenVersion: 1,
		TTL: 5 * time.Minute, ClockSkew: 5 * time.Second,
	}
}
