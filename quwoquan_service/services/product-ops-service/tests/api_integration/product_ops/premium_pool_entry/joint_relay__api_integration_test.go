package api_integration

import (
	"context"
	"crypto"
	"crypto/rand"
	"crypto/rsa"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"math/big"
	"net/http"
	"net/http/httptest"
	"os"
	"quwoquan_service/generated/operationsecurity"
	"quwoquan_service/internal/platform/pgoutbox"
	redisplatform "quwoquan_service/internal/platform/redis"
	"quwoquan_service/runtime/auth"
	messaging "quwoquan_service/runtime/messaging"
	redisruntime "quwoquan_service/runtime/redis"
	rt "quwoquan_service/runtime/search"
	publisher "quwoquan_service/services/product-ops-service/internal/product_ops/event_record/infrastructure/messaging"
	premiumhttp "quwoquan_service/services/product-ops-service/internal/product_ops/premium_pool_entry/adapters/inbound/http"
	"quwoquan_service/services/product-ops-service/internal/product_ops/premium_pool_entry/application"
	"quwoquan_service/services/product-ops-service/internal/product_ops/premium_pool_entry/infrastructure/contentsource"
	"quwoquan_service/services/product-ops-service/internal/product_ops/premium_pool_entry/infrastructure/persistence"
	"strings"
	"testing"
	"time"
)

// spec_ref: specs/feature-tree/runtime/runtime-config/environment-topology-and-packaging/spec.md#gwt-007
// Python联合测试通过隔离loopback Redis启动本runner；Content source为typed fixture，其余PG/HTTP/relay均为生产实现。
func TestJointPremiumRelayHarness(t *testing.T) {
	addr := os.Getenv("QWQ_JOINT_REDIS_ADDR")
	if addr == "" {
		t.Skip("launched only by isolated joint Python suite")
	}
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Minute)
	defer cancel()
	t.Setenv("APP_ENV", "gamma")
	cfg := auth.TokenConfig{Secret: []byte("joint-relay-secret-012345678901234567890"), Issuer: "joint", Audience: "joint-services", Type: auth.TokenTypeAccess, TokenVersion: 1, TTL: time.Minute}
	verifier, _ := auth.NewHS256Verifier(cfg)
	operatorKey, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	b64 := base64.RawURLEncoding.EncodeToString
	jwks := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_ = json.NewEncoder(w).Encode(map[string]any{"keys": []any{map[string]any{"kty": "RSA", "kid": "joint-key", "alg": "RS256", "use": "sig", "n": b64(operatorKey.N.Bytes()), "e": b64(big.NewInt(int64(operatorKey.E)).Bytes())}}})
	}))
	defer jwks.Close()
	operatorVerifier, err := auth.NewOIDCVerifier(auth.OIDCConfig{Issuer: "joint-operator", Audience: "joint-ops", JWKSURL: jwks.URL, RequireMFA: true, HTTPClient: jwks.Client()})
	if err != nil {
		t.Fatal(err)
	}
	sign := func(actor, scope string) string {
		header, _ := json.Marshal(map[string]any{"alg": "RS256", "kid": "joint-key", "typ": "JWT"})
		now := time.Now().Unix()
		payload, _ := json.Marshal(map[string]any{"iss": "joint-operator", "aud": "joint-ops", "sub": actor, "scope": scope, "roles": []string{"operator"}, "amr": []string{"mfa"}, "iat": now, "nbf": now, "exp": now + 180, "jti": actor + scope})
		input := b64(header) + "." + b64(payload)
		sum := sha256.Sum256([]byte(input))
		sig, err := rsa.SignPKCS1v15(rand.Reader, operatorKey, crypto.SHA256, sum[:])
		if err != nil {
			t.Fatal(err)
		}
		return input + "." + b64(sig)
	}
	credentials, _ := auth.NewHS256ServiceAuthorizationProvider(cfg, "product-ops-service", []string{"content.release.source.read"})
	d := "sha256:" + strings.Repeat("a", 64)
	snapshots := map[string]rt.ReleasePostCandidateSnapshot{}
	for _, id := range []string{"A", "B"} {
		binding := rt.ReleaseCandidateBinding{Environment: "gamma", SourceOwner: "qwq_data", ReleaseID: id, ManifestDigest: d}
		s := rt.ReleasePostCandidateSnapshot{Release: binding, SourceClosureDigest: d, MediaClosureDigest: d, Posts: []rt.ReleasePostPublicSnapshot{{Identity: rt.ReleaseCandidateObjectIdentity{Release: binding, ObjectType: "content.post", ObjectID: "p", SourceVersion: 1, SourceDigest: d}, PostRef: "ref", AuthorID: "author", AuthorDisplayName: "Author", ContentType: "video", ContentIdentity: "work", Status: "published", Visibility: "public", ModerationStatus: "approved", TagRefs: []string{}, EntityRefs: []string{}, MediaAssetIDs: []string{"asset"}, MediaURLs: []string{"https://media.invalid/video"}, DurationMs: 1000, Width: 10, Height: 10, PublishedAt: "2026-09-13T00:00:00Z", UpdatedAt: "2026-09-13T00:00:00Z", DeepLink: "/content/p"}}}
		url := "https://media.invalid/video"
		s.Posts[0].VideoURL = &url
		_ = s.Seal()
		snapshots[id] = s
	}
	source := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		claims, err := verifier.Verify(strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer "))
		if err != nil || claims.Subject != "service:product-ops-service" || claims.Scope != "content.release.source.read" {
			http.Error(w, "forbidden", 403)
			return
		}
		var q struct {
			Release rt.ReleaseCandidateBinding `json:"release"`
		}
		if rt.DecodeCreatorValue(r.Body, &q) != nil {
			http.Error(w, "invalid", 422)
			return
		}
		s, ok := snapshots[q.Release.ReleaseID]
		if !ok || s.Release != q.Release {
			http.Error(w, "absent", 404)
			return
		}
		_ = json.NewEncoder(w).Encode(s)
	}))
	defer source.Close()
	store, _ := persistence.NewPostgresStore(premiumPoolPGPool)
	if err := store.EnsureSchema(ctx); err != nil {
		t.Fatal(err)
	}
	reader := &contentsource.Reader{Endpoint: source.URL, Client: source.Client(), Credential: func(ctx context.Context) (string, error) {
		h, e := credentials.AuthorizationHeader(ctx)
		return strings.TrimPrefix(h, "Bearer "), e
	}}
	service := application.NewService(store).WithCandidateSource(reader)
	handler := premiumhttp.NewHandler(service, func(w http.ResponseWriter, r *http.Request, status int, message, detail string) {
		http.Error(w, message, status)
	})
	router, err := redisplatform.NewRouter(redisruntime.RouterConfig{Scenes: map[string]redisruntime.SceneConfig{"general": {Mode: "standalone", Addr: addr}}, DefaultScene: "general"})
	if err != nil {
		t.Fatal(err)
	}
	defer router.Close()
	transport, err := messaging.NewRedisMessageTransport(router.Scene("general"), router.Scene("general"))
	if err != nil {
		t.Fatal(err)
	}
	relay := publisher.NewRedisEventPublisherWithTransport(transport, "product-ops-service", nil)
	dispatcher, _ := pgoutbox.NewDispatcher(premiumPoolPGPool, relay, "premium_pool_entry_outbox")
	guardedHandler := auth.Middleware(auth.MiddlewareConfig{OperatorOIDCVerifier: operatorVerifier})(auth.EnforceRuntimeOperationContract(operationsecurity.ForDomain("ops"))(handler))
	done := make(chan struct{})
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/fixture/snapshots" {
			_ = json.NewEncoder(w).Encode(snapshots)
			return
		}
		if r.URL.Path == "/fixture/done" {
			select {
			case <-done:
			default:
				close(done)
			}
			w.WriteHeader(204)
			return
		}
		claims, err := operatorVerifier.Verify(strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer "))
		if err != nil || claims.Scope != "ops.reco.write" {
			http.Error(w, "forbidden", 403)
			return
		}
		if r.URL.Path == "/fixture/fail-audit" {
			_, err := premiumPoolPGPool.Exec(ctx, `CREATE OR REPLACE FUNCTION joint_fail_audit() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'isolated joint failure'; END $$; CREATE TRIGGER joint_audit_failure BEFORE INSERT ON premium_pool_entry_audits FOR EACH ROW EXECUTE FUNCTION joint_fail_audit()`)
			if err != nil {
				t.Error(err)
				http.Error(w, "fixture failure", 500)
				return
			}
			w.WriteHeader(204)
			return
		}
		if r.URL.Path == "/fixture/recover-audit" {
			if _, err := premiumPoolPGPool.Exec(ctx, `DROP TRIGGER joint_audit_failure ON premium_pool_entry_audits`); err != nil {
				t.Error(err)
			}
			w.WriteHeader(204)
			return
		}
		if r.URL.Path == "/fixture/stats" {
			var revision, members, outbox, audits, receipts int
			_ = premiumPoolPGPool.QueryRow(ctx, `SELECT revision,jsonb_array_length(release_admissions) FROM premium_pool_entries WHERE content_id='p'`).Scan(&revision, &members)
			_ = premiumPoolPGPool.QueryRow(ctx, `SELECT count(*) FROM premium_pool_entry_outbox`).Scan(&outbox)
			_ = premiumPoolPGPool.QueryRow(ctx, `SELECT count(*) FROM premium_pool_entry_audits`).Scan(&audits)
			_ = premiumPoolPGPool.QueryRow(ctx, `SELECT count(*) FROM premium_pool_entry_command_receipts`).Scan(&receipts)
			_ = json.NewEncoder(w).Encode(map[string]int{"revision": revision, "members": members, "outbox": outbox, "audits": audits, "receipts": receipts})
			return
		}
		guardedHandler.ServeHTTP(w, r)
		if _, err := dispatcher.DispatchOnce(ctx); err != nil {
			t.Errorf("real dispatcher: %v", err)
		}
	}))
	defer server.Close()
	payload, _ := json.Marshal(map[string]string{"url": server.URL, "operatorA": sign("operator-a", "ops.reco.write"), "operatorB": sign("operator-b", "ops.reco.write"), "wrongScope": sign("operator-a", "ops.reco.read")})
	fmt.Printf("JOINT_READY %s\n", payload)
	select {
	case <-done:
	case <-ctx.Done():
		t.Fatal("joint consumer timeout")
	}
	var pending int
	if err := premiumPoolPGPool.QueryRow(ctx, "SELECT count(*) FROM premium_pool_entry_outbox WHERE dispatched_at IS NULL").Scan(&pending); err != nil || pending != 0 {
		t.Fatal("pending relay", pending, err)
	}
}
