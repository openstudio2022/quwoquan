package http_test

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"quwoquan_service/generated/operationsecurity"
	"quwoquan_service/runtime/auth"
	wire "quwoquan_service/services/content-service/generated/content/post/contract/releasequery"
	adapter "quwoquan_service/services/content-service/internal/content/post/adapters/inbound/http"
	app "quwoquan_service/services/content-service/internal/content/post/application/public"
	"strings"
	"testing"
	"time"
)

type commitReader struct{ calls int }

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-004
func TestCommitReceiptRealSignerRuntimeGuard(t *testing.T) {
	reader := &commitReader{}
	mux := http.NewServeMux()
	adapter.NewReleaseCommitReceiptHandler(reader, "alpha").Register(mux)
	config := auth.TokenConfig{Secret: bytes.Repeat([]byte{0x63}, 32), Issuer: "receipt-test", Audience: "content-service", Type: auth.TokenTypeAccess, TokenVersion: 1, TTL: time.Minute}
	verifier, err := auth.NewHS256Verifier(config)
	if err != nil {
		t.Fatal(err)
	}
	guarded := auth.Middleware(auth.MiddlewareConfig{AccessTokenVerifier: verifier})(auth.EnforceRuntimeOperationContract(operationsecurity.ForDomain("content"))(adapter.RequireSensitiveOperationPrincipal(mux)))
	raw := `{"release":{"environment":"alpha","sourceOwner":"qwq_data","releaseId":"a","manifestDigest":"sha256:` + strings.Repeat("a", 64) + `"},"expected":{"found":false,"environment":"alpha","sourceOwner":"qwq_data","releaseId":"","manifestDigest":"","revision":0,"projectionVersion":0,"activatedAt":null}}`
	call := func(token string) int {
		request := httptest.NewRequest(http.MethodPost, "/internal/content/release-commit-receipts:query", strings.NewReader(raw))
		request.Header.Set("Authorization", token)
		w := httptest.NewRecorder()
		guarded.ServeHTTP(w, request)
		return w.Code
	}
	if code := call(""); code != 401 {
		t.Fatal("unsigned", code)
	}
	for _, test := range []struct {
		scope  string
		status int
	}{{"wrong.scope", 403}, {"content.release.fence.read", 200}} {
		signer, err := auth.NewHS256ServiceAuthorizationProvider(config, "search-service", []string{test.scope})
		if err != nil {
			t.Fatal(err)
		}
		token, err := signer.AuthorizationHeader(t.Context())
		if err != nil {
			t.Fatal(err)
		}
		if code := call(token); code != test.status {
			t.Fatal(test.scope, code)
		}
	}
	if reader.calls != 1 {
		t.Fatal("unauthorized reached reader", reader.calls)
	}
}

func (r *commitReader) ReadContentReleaseCommitReceipt(_ context.Context, q wire.ReadContentReleaseCommitReceiptQuery) (wire.ContentReleaseCommitReceipt, error) {
	r.calls++
	now := time.Date(2026, 9, 13, 0, 0, 0, 0, time.UTC)
	after := q.Expected
	after.Found = true
	after.ReleaseId = q.Release.ReleaseId
	after.ManifestDigest = q.Release.ManifestDigest
	after.Revision++
	after.ProjectionVersion = 1
	after.ActivatedAt = &now
	result := wire.ContentReleaseCommitReceipt{Transition: wire.ContentReleaseFenceChangedPayload{Before: q.Expected, After: after}}
	result.EventId = app.ReleaseFenceEventID(after)
	result.PayloadDigest = app.ReleaseFencePayloadDigest(result.Transition)
	return result, nil
}

// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-004
// handler形状测试，不替代生产guard/signer或真实receipt持久化证据。
func TestCommitReceiptHandlerRequiresExactExpectedPresence(t *testing.T) {
	reader := &commitReader{}
	mux := http.NewServeMux()
	adapter.NewReleaseCommitReceiptHandler(reader, "alpha").Register(mux)
	expected := map[string]any{"found": false, "environment": "alpha", "sourceOwner": "qwq_data", "releaseId": "", "manifestDigest": "", "revision": 0, "projectionVersion": 0, "activatedAt": nil}
	q := map[string]any{"release": map[string]any{"environment": "alpha", "sourceOwner": "qwq_data", "releaseId": "a", "manifestDigest": "sha256:" + strings.Repeat("a", 64)}, "expected": expected}
	call := func() int {
		raw, _ := json.Marshal(q)
		w := httptest.NewRecorder()
		mux.ServeHTTP(w, httptest.NewRequest(http.MethodPost, "/internal/content/release-commit-receipts:query", bytes.NewReader(raw)))
		return w.Code
	}
	if code := call(); code != 200 {
		t.Fatal(code)
	}
	for _, key := range []string{"found", "revision", "activatedAt"} {
		value := expected[key]
		delete(expected, key)
		if code := call(); code != 422 {
			t.Fatal("missing", key, code)
		}
		expected[key] = value
	}
	q["unknown"] = true
	if code := call(); code != 422 {
		t.Fatal(code)
	}
	if reader.calls != 1 {
		t.Fatal("invalid request reached reader")
	}
}
