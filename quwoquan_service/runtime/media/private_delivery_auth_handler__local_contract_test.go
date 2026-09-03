// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/design.md#dec-031
package runtimemedia

import (
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
	"time"
)

func deliveryAuthProbe(
	t *testing.T,
	handler http.Handler,
	forwardedURI string,
) int {
	t.Helper()
	request := httptest.NewRequest(http.MethodGet, "/internal/media/delivery-auth", nil)
	if forwardedURI != "" {
		request.Header.Set("X-Forwarded-Uri", forwardedURI)
	}
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder.Code
}

func TestPrivateDeliveryAuthHandlerEnforcesSharedVerifier(t *testing.T) {
	const signKey = "edge-auth-test-key"
	now := time.Unix(1767225600, 0).UTC()
	handler := NewPrivateDeliveryAuthHandler(signKey, func() time.Time { return now })

	objectKey := "media/objects/sha256/aa/bb/" + strings.Repeat("a", 64) + ".jpg"
	signed := SignCDNURLUntil(
		"https://media-cdn.local",
		objectKey,
		signKey,
		now.Add(10*time.Minute),
	)
	parsed, err := url.Parse(signed)
	if err != nil {
		t.Fatalf("signed URL is unparseable: %v", err)
	}
	signedURI := parsed.EscapedPath() + "?" + parsed.RawQuery

	if got := deliveryAuthProbe(t, handler, signedURI); got != http.StatusNoContent {
		t.Fatalf("authentic signed URI = %d, want 204", got)
	}
	// 公开切片路径不归本端点评判：边缘匹配器误配也不能打断匿名公开面。
	publicURI := "/media/image/s/asset/image-001/v1/source.webp"
	if got := deliveryAuthProbe(t, handler, publicURI); got != http.StatusNoContent {
		t.Fatalf("public slice URI = %d, want 204", got)
	}
	for name, uri := range map[string]string{
		"missing signature":   parsed.EscapedPath(),
		"forged signature":    parsed.EscapedPath() + "?sign=" + strings.Repeat("f", 64) + "&t=" + parsed.Query().Get("t"),
		"tampered path":       "/media/objects/sha256/aa/bb/" + strings.Repeat("b", 64) + ".jpg?" + parsed.RawQuery,
		"tampered expiry":     parsed.EscapedPath() + "?sign=" + parsed.Query().Get("sign") + "&t=9999999999",
		"malformed forwarded": "://not-a-uri",
	} {
		t.Run(name, func(t *testing.T) {
			if got := deliveryAuthProbe(t, handler, uri); got != http.StatusForbidden {
				t.Fatalf("%s = %d, want 403", name, got)
			}
		})
	}
	// 过期即拒绝：同一 URI 在到期后必须失效。
	late := NewPrivateDeliveryAuthHandler(
		signKey,
		func() time.Time { return now.Add(11 * time.Minute) },
	)
	if got := deliveryAuthProbe(t, late, signedURI); got != http.StatusForbidden {
		t.Fatalf("expired signed URI = %d, want 403", got)
	}
	// 缺 X-Forwarded-Uri 的直接访问没有可判定对象。
	if got := deliveryAuthProbe(t, handler, ""); got != http.StatusForbidden {
		t.Fatalf("missing forwarded uri = %d, want 403", got)
	}
}

func TestPrivateDeliveryAuthHandlerFailsClosedWithoutKey(t *testing.T) {
	now := time.Unix(1767225600, 0).UTC()
	handler := NewPrivateDeliveryAuthHandler("", func() time.Time { return now })
	// signKey 缺失：私有前缀整体 fail closed，即使签名结构完整。
	uri := "/media/objects/sha256/aa/bb/" + strings.Repeat("a", 64) + ".jpg" +
		"?sign=" + strings.Repeat("a", 64) + "&t=1767226200"
	if got := deliveryAuthProbe(t, handler, uri); got != http.StatusForbidden {
		t.Fatalf("missing sign key = %d, want 403", got)
	}
	// 公开面不受 signKey 缺失影响。
	publicURI := "/media/image/s/asset/image-001/v1/source.webp"
	if got := deliveryAuthProbe(t, handler, publicURI); got != http.StatusNoContent {
		t.Fatalf("public slice with missing key = %d, want 204", got)
	}
}
