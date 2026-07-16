package api_integration

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"testing"
	"time"

	embeddedpostgres "github.com/fergusstrange/embedded-postgres"
	"github.com/jackc/pgx/v5/pgxpool"

	generatedcontrolplane "quwoquan_service/generated/control_plane"
	operationsecurity "quwoquan_service/generated/operationsecurity"
	"quwoquan_service/internal/platform/testinfra"
	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	confighttp "quwoquan_service/services/platform-ops-service/internal/adapters/http/config_layer"
	configapp "quwoquan_service/services/platform-ops-service/internal/application/platform_ops/config_layer"
	configpersistence "quwoquan_service/services/platform-ops-service/internal/infrastructure/platform_ops/config_layer/persistence"
)

var (
	platformOpsEmbeddedPG *embeddedpostgres.EmbeddedPostgres
	platformOpsPGPool     *pgxpool.Pool
)

func TestMain(m *testing.M) {
	const port = uint32(15437)
	platformOpsEmbeddedPG = embeddedpostgres.NewDatabase(
		embeddedpostgres.DefaultConfig().
			Version(testinfra.StableEmbeddedPostgresVersion).
			Port(port).
			Username("postgres").
			Password("postgres"),
	)
	if err := platformOpsEmbeddedPG.Start(); err != nil {
		panic("platform-ops embedded-postgres start: " + err.Error())
	}
	ctx, cancel := context.WithTimeout(context.Background(), 20*time.Second)
	defer cancel()
	var err error
	platformOpsPGPool, err = pgxpool.New(ctx, fmt.Sprintf(
		"postgres://postgres:postgres@127.0.0.1:%d/postgres?sslmode=disable", port,
	))
	if err != nil {
		panic(err)
	}
	if err := platformOpsPGPool.Ping(ctx); err != nil {
		panic(err)
	}
	code := m.Run()
	platformOpsPGPool.Close()
	if err := platformOpsEmbeddedPG.Stop(); err != nil && code == 0 {
		code = 1
	}
	os.Exit(code)
}

func TestConfigLayerHTTPBoundaryUsesGeneratedGuardAndAtomicPostgres(t *testing.T) {
	store, err := configpersistence.NewPostgresStore(platformOpsPGPool)
	if err != nil {
		t.Fatal(err)
	}
	ctx := context.Background()
	if err := store.EnsureSchema(ctx); err != nil {
		t.Fatalf("ensure config layer schema: %v", err)
	}
	if _, err := platformOpsPGPool.Exec(ctx, `
TRUNCATE platform_config_layer_receipts, platform_ops_outbox, platform_config_layers CASCADE`); err != nil {
		t.Fatalf("truncate config layer tables: %v", err)
	}
	catalog, err := configpersistence.NewGeneratedConfigKeyCatalog(
		generatedcontrolplane.MustLoadPlatformConfigSchema(),
	)
	if err != nil {
		t.Fatalf("build generated config catalog: %v", err)
	}
	facade, err := configapp.NewFacade(store, store, catalog)
	if err != nil {
		t.Fatal(err)
	}
	handler, err := confighttp.NewHandler(facade)
	if err != nil {
		t.Fatal(err)
	}
	guarded := platformConfigAuthenticatedHandler(t, handler)
	path := "/v1/control-plane/platform/configs/sys.content.mongo.max_pool_size:update"
	body := `{"layerId":"service:gamma:gamma-user-a:content-service","expectedVersion":0,"scopeLevel":"service","scopeId":"content-service","environment":"gamma","cluster":"gamma-user-a","service":"content-service","value":{"kind":"int","intValue":120}}`

	unauthorized := performPlatformConfigRequest(guarded, http.MethodPost, path, body, "", "config-api-1")
	assertPlatformConfigError(t, unauthorized, http.StatusUnauthorized, "GATEWAY.USER.unauthorized")

	readOnly := platformConfigAccessToken(t, "ops.platform.config.read")
	forbidden := performPlatformConfigRequest(guarded, http.MethodPost, path, body, readOnly, "config-api-1")
	assertPlatformConfigError(t, forbidden, http.StatusForbidden, "GATEWAY.USER.forbidden")

	writeToken := platformConfigAccessToken(t, "ops.platform.config.write")
	created := performPlatformConfigRequest(guarded, http.MethodPost, path, body, writeToken, "config-api-1")
	if created.Code != http.StatusOK {
		t.Fatalf("create config layer status=%d body=%s", created.Code, created.Body.String())
	}
	replayed := performPlatformConfigRequest(guarded, http.MethodPost, path, body, writeToken, "config-api-1")
	if replayed.Code != http.StatusOK || !strings.Contains(replayed.Body.String(), `"replayed":true`) {
		t.Fatalf("replay config layer status=%d body=%s", replayed.Code, replayed.Body.String())
	}
	conflictBody := strings.Replace(body, `"intValue":120`, `"intValue":121`, 1)
	conflict := performPlatformConfigRequest(guarded, http.MethodPost, path, conflictBody, writeToken, "config-api-1")
	assertPlatformConfigError(t, conflict, http.StatusConflict, "OPS.USER.config_idempotency_conflict")

	readToken := platformConfigAccessToken(t, "ops.platform.config.read")
	layers := performPlatformConfigRequest(
		guarded, http.MethodGet, "/v1/control-plane/platform/configs/layers", "", readToken, "",
	)
	if layers.Code != http.StatusOK || !strings.Contains(layers.Body.String(), "service:gamma:gamma-user-a:content-service") {
		t.Fatalf("list config layers status=%d body=%s", layers.Code, layers.Body.String())
	}
	resolved := performPlatformConfigRequest(
		guarded, http.MethodGet,
		"/v1/control-plane/platform/configs/resolve?env=gamma&cluster=gamma-user-a&service=content-service",
		"", readToken, "",
	)
	if resolved.Code != http.StatusOK || !strings.Contains(resolved.Body.String(), `"intValue":120`) {
		t.Fatalf("resolve config status=%d body=%s", resolved.Code, resolved.Body.String())
	}

	var layerCount, receiptCount, outboxCount int
	err = platformOpsPGPool.QueryRow(ctx, `
SELECT
  (SELECT COUNT(*) FROM platform_config_layers),
  (SELECT COUNT(*) FROM platform_config_layer_receipts),
  (SELECT COUNT(*) FROM platform_ops_outbox)`).Scan(&layerCount, &receiptCount, &outboxCount)
	if err != nil {
		t.Fatalf("inspect config layer transaction: %v", err)
	}
	if layerCount != 1 || receiptCount != 1 || outboxCount != 1 {
		t.Fatalf("atomic config commit counts layer=%d receipt=%d outbox=%d", layerCount, receiptCount, outboxCount)
	}
}

func platformConfigAuthenticatedHandler(t *testing.T, next http.Handler) http.Handler {
	t.Helper()
	verifier, err := rtauth.NewHS256Verifier(platformConfigTokenConfig())
	if err != nil {
		t.Fatal(err)
	}
	next = rtauth.RequireGeneratedOperationAuthorization(operationsecurity.ForDomain("ops"))(next)
	return rtauth.Middleware(rtauth.MiddlewareConfig{AccessTokenVerifier: verifier})(next)
}

func platformConfigAccessToken(t *testing.T, scopes string) string {
	t.Helper()
	signer, err := rtauth.NewHS256Signer(platformConfigTokenConfig())
	if err != nil {
		t.Fatal(err)
	}
	token, err := signer.Sign(rtauth.TokenSubject{
		AccountID: "platform-operator", Scopes: strings.Fields(scopes), Roles: []string{"operator"},
	})
	if err != nil {
		t.Fatal(err)
	}
	return token
}

func platformConfigTokenConfig() rtauth.TokenConfig {
	return rtauth.TokenConfig{
		Secret: []byte("platform-ops-api-integration-secret-32bytes"),
		Issuer: "platform-ops-api-integration", Audience: "quwoquan-api",
		Type: rtauth.TokenTypeAccess, TokenVersion: 1, TTL: 5 * time.Minute, ClockSkew: time.Second,
	}
}

func performPlatformConfigRequest(
	handler http.Handler,
	method, path, body, token, idempotencyKey string,
) *httptest.ResponseRecorder {
	request := httptest.NewRequest(method, path, strings.NewReader(body))
	request.Header.Set("Content-Type", "application/json")
	if token != "" {
		request.Header.Set("Authorization", "Bearer "+token)
	}
	if idempotencyKey != "" {
		request.Header.Set("Idempotency-Key", idempotencyKey)
	}
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}

func assertPlatformConfigError(t *testing.T, recorder *httptest.ResponseRecorder, status int, code string) {
	t.Helper()
	if recorder.Code != status {
		t.Fatalf("error status=%d want=%d body=%s", recorder.Code, status, recorder.Body.String())
	}
	var response rterr.ErrorResponse
	if err := json.Unmarshal(recorder.Body.Bytes(), &response); err != nil {
		t.Fatalf("decode error response: %v body=%s", err, recorder.Body.String())
	}
	if response.Code != code {
		t.Fatalf("error code=%q want=%q body=%s", response.Code, code, recorder.Body.String())
	}
}
