// spec_ref: specs/feature-tree/gateway-orchestrator-foundation/unified-entry-security/spec.md#sit-001
// readiness_case: shared-admission-api
package api_integration

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"github.com/prometheus/client_golang/prometheus"

	rtauth "quwoquan_service/runtime/auth"
	rterr "quwoquan_service/runtime/errors"
	httpadapter "quwoquan_service/services/api-edge/internal/edge_security/rate_limit_bucket/adapters/inbound/http"
	"quwoquan_service/services/api-edge/internal/edge_security/rate_limit_bucket/application"
	"quwoquan_service/services/api-edge/internal/edge_security/rate_limit_bucket/domain"
	admissionmetrics "quwoquan_service/services/api-edge/internal/edge_security/rate_limit_bucket/infrastructure/observability"
	"quwoquan_service/services/api-edge/internal/edge_security/rate_limit_bucket/infrastructure/redisstore"
)

func TestStableAndGrayReplicasShareOneAtomicAdmissionBucket(t *testing.T) {
	redisAddress, stopRedis := startRedisServer(t)
	storeConfig := redisstore.Config{
		Mode:         "standalone",
		Addr:         redisAddress,
		PoolSize:     8,
		DialTimeout:  200 * time.Millisecond,
		ReadTimeout:  200 * time.Millisecond,
		WriteTimeout: 200 * time.Millisecond,
	}
	stableStore, err := redisstore.New(storeConfig)
	if err != nil {
		t.Fatalf("new stable store: %v", err)
	}
	t.Cleanup(func() { _ = stableStore.Close() })
	grayStore, err := redisstore.New(storeConfig)
	if err != nil {
		t.Fatalf("new gray store: %v", err)
	}
	t.Cleanup(func() { _ = grayStore.Close() })

	registry := prometheus.NewRegistry()
	metrics := admissionmetrics.NewMetrics(registry)
	policies := integrationPolicies(4, 10*time.Second)
	stableAdmission, err := application.NewService("prod", stableStore, policies, metrics)
	if err != nil {
		t.Fatalf("new stable admission: %v", err)
	}
	grayAdmission, err := application.NewService("prod", grayStore, policies, metrics)
	if err != nil {
		t.Fatalf("new gray admission: %v", err)
	}

	token, verifier := integrationAccessCredential(t)
	authority := staticAuthority{snapshot: rtauth.AccountSecuritySnapshot{
		AccountState: "active",
		AuthEpoch:    7,
	}}
	descriptor := rtauth.OperationSecurityDescriptor{
		CanonicalOperationID: "content.post.CreatePost",
		ContractGraphSHA256:  "api-edge-api-integration",
		Method:               http.MethodPost,
		PathTemplate:         "/content/posts",
		OperationKind:        "command",
		MutationTarget:       "Post",
		InvariantTarget:      "Post",
		AuthMode:             "required",
		ActorRequirement:     "persona",
		Principal:            "persona",
		Idempotency:          "required",
		CommercialStatus:     "ready",
		TimeoutMilliseconds:  1500,
	}

	var ownerCalls atomic.Int64
	owner := httptest.NewServer(http.HandlerFunc(func(
		response http.ResponseWriter,
		request *http.Request,
	) {
		if authorization := request.Header.Get("Authorization"); authorization != "Bearer "+token {
			t.Errorf("owner received authorization=%q", authorization)
		}
		if leaked := request.Header.Get("X-Edge-Client-IP"); leaked != "" {
			t.Errorf("edge-only network identity leaked to owner: %q", leaked)
		}
		if digest := request.Header.Get("X-Contract-Graph-SHA256"); digest != descriptor.ContractGraphSHA256 {
			t.Errorf("owner contract digest=%q", digest)
		}
		ownerCalls.Add(1)
		response.WriteHeader(http.StatusNoContent)
	}))
	t.Cleanup(owner.Close)

	stableHandler := integrationEdgeHandler(t, stableAdmission, verifier, authority, descriptor, owner.URL)
	grayHandler := integrationEdgeHandler(t, grayAdmission, verifier, authority, descriptor, owner.URL)
	stableClient := startUnixHTTPReplica(t, "stable", stableHandler)
	grayClient := startUnixHTTPReplica(t, "gray", grayHandler)
	clients := []*http.Client{stableClient, grayClient}

	type requestResult struct {
		response *http.Response
		err      error
	}
	start := make(chan struct{})
	results := make(chan requestResult, 8)
	for attempt := 0; attempt < 8; attempt++ {
		client := clients[attempt%len(clients)]
		go func() {
			<-start
			response, requestErr := executeIntegrationRequestResult(client, token)
			results <- requestResult{response: response, err: requestErr}
		}()
	}
	close(start)
	allowed := 0
	denied := 0
	for attempt := 0; attempt < 8; attempt++ {
		result := <-results
		if result.err != nil {
			t.Fatalf("concurrent admission request: %v", result.err)
		}
		if result.response.StatusCode == http.StatusNoContent {
			allowed++
			_ = result.response.Body.Close()
			continue
		}
		assertTypedAdmissionError(
			t,
			result.response,
			http.StatusTooManyRequests,
			"GATEWAY.USER.rate_limited",
		)
		denied++
	}
	if allowed != 4 || denied != 4 {
		t.Fatalf("atomic concurrent decisions allowed=%d denied=%d want=4/4", allowed, denied)
	}
	if calls := ownerCalls.Load(); calls != 4 {
		t.Fatalf("owner calls=%d want=4; replicas did not share one atomic bucket", calls)
	}

	// IssueConnectionTicket is authored as a session operation. Stable and gray
	// must therefore consume one shared Redis-backed session bucket and surface
	// the gateway-owned 429 contract, rather than a second realtime-owned limit.
	sessionPolicies := integrationPolicies(1, time.Second)
	stableSessionAdmission, err := application.NewService("prod", stableStore, sessionPolicies, metrics)
	if err != nil {
		t.Fatalf("new stable session admission: %v", err)
	}
	graySessionAdmission, err := application.NewService("prod", grayStore, sessionPolicies, metrics)
	if err != nil {
		t.Fatalf("new gray session admission: %v", err)
	}
	sessionDescriptor := rtauth.OperationSecurityDescriptor{
		CanonicalOperationID: "realtime.connection.IssueConnectionTicket",
		ContractGraphSHA256:  descriptor.ContractGraphSHA256,
		Method:               http.MethodPost,
		PathTemplate:         "/realtime/tickets",
		OperationKind:        "session",
		AuthMode:             "required",
		ActorRequirement:     "persona",
		Principal:            "persona",
		Idempotency:          "none",
		CommercialStatus:     "ready",
		TimeoutMilliseconds:  1500,
	}
	stableSessionHandler := integrationEdgeHandler(
		t,
		stableSessionAdmission,
		verifier,
		authority,
		sessionDescriptor,
		owner.URL,
	)
	graySessionHandler := integrationEdgeHandler(
		t,
		graySessionAdmission,
		verifier,
		authority,
		sessionDescriptor,
		owner.URL,
	)
	stableSessionClient := startUnixHTTPReplica(t, "session-stable", stableSessionHandler)
	graySessionClient := startUnixHTTPReplica(t, "session-gray", graySessionHandler)
	firstSessionResponse := executeSessionIntegrationRequest(t, stableSessionClient, token)
	if firstSessionResponse.StatusCode != http.StatusNoContent {
		t.Fatalf(
			"first IssueConnectionTicket status=%d body=%s",
			firstSessionResponse.StatusCode,
			readBody(firstSessionResponse),
		)
	}
	_ = firstSessionResponse.Body.Close()
	secondSessionResponse := executeSessionIntegrationRequest(t, graySessionClient, token)
	retryAfter := assertTypedAdmissionError(
		t,
		secondSessionResponse,
		http.StatusTooManyRequests,
		"GATEWAY.USER.rate_limited",
	)
	if retryAfter != 1 {
		t.Fatalf("IssueConnectionTicket Retry-After=%d want=1", retryAfter)
	}
	if calls := ownerCalls.Load(); calls != 5 {
		t.Fatalf("owner calls=%d want=5; denied session request reached realtime owner", calls)
	}

	// A repeated command idempotency key is intentionally not a second quota
	// path: admission is consumed before owner-level idempotency semantics.
	stopRedis()
	failure := executeIntegrationRequest(t, stableClient, token)
	assertTypedAdmissionError(
		t,
		failure,
		http.StatusServiceUnavailable,
		"GATEWAY.MIDDLEWARE.rate_limit_state_unavailable",
	)
	if calls := ownerCalls.Load(); calls != 5 {
		t.Fatalf("owner calls after Redis fault=%d want=5", calls)
	}
	assertAdmissionMetricContract(t, registry)
}

func integrationPolicies(limit int64, window time.Duration) application.PolicySet {
	byKind := make(map[string]domain.Policy, 3)
	for _, operationKind := range []string{"command", "query", "session"} {
		byKind[operationKind] = domain.Policy{
			Limit:        limit,
			Window:       window,
			StateFailure: domain.FailurePolicyFailClosed,
		}
	}
	return application.PolicySet{ByOperationKind: byKind}
}

func integrationAccessCredential(t *testing.T) (string, *rtauth.Verifier) {
	t.Helper()
	config := rtauth.TokenConfig{
		Secret:       []byte("api-edge-integration-secret-32-bytes-minimum"),
		Issuer:       "api-edge-integration",
		Audience:     "quwoquan-api",
		Type:         rtauth.TokenTypeAccess,
		TokenVersion: 1,
		TTL:          time.Minute,
		ClockSkew:    time.Second,
	}
	signer, err := rtauth.NewHS256Signer(config)
	if err != nil {
		t.Fatalf("new signer: %v", err)
	}
	verifier, err := rtauth.NewHS256Verifier(config)
	if err != nil {
		t.Fatalf("new verifier: %v", err)
	}
	token, err := signer.Sign(rtauth.TokenSubject{
		AccountID: "account-api-edge-integration",
		PersonaID: "persona-api-edge-integration",
		AuthEpoch: 7,
	})
	if err != nil {
		t.Fatalf("sign access credential: %v", err)
	}
	return token, verifier
}

func integrationEdgeHandler(
	t *testing.T,
	admission *application.Service,
	verifier *rtauth.Verifier,
	authority rtauth.AccountSecurityAuthority,
	descriptor rtauth.OperationSecurityDescriptor,
	ownerURL string,
) http.Handler {
	t.Helper()
	origin, err := url.Parse(ownerURL)
	if err != nil || origin.Scheme == "" || origin.Host == "" {
		t.Fatalf("parse owner origin: %v", err)
	}
	ownerProxy, err := httpadapter.NewOwnerProxy(httpadapter.OwnerProxyConfig{
		Routes: []httpadapter.OwnerRoute{{
			OperationPrefix: strings.SplitN(descriptor.CanonicalOperationID, ".", 2)[0] + ".",
			Upstream:        origin,
		}},
		BudgetAllowance:      500 * time.Millisecond,
		TrustedNetworkHeader: "X-Edge-Client-IP",
		ContractGraphSHA256:  descriptor.ContractGraphSHA256,
	})
	if err != nil {
		t.Fatalf("new owner proxy: %v", err)
	}
	handler := httpadapter.AdmissionMiddleware(
		admission,
		httpadapter.SubjectResolver{TrustedNetworkHeader: "X-Edge-Client-IP"},
	)(ownerProxy)
	handler = rtauth.RequireGeneratedOperationAuthorization(
		[]rtauth.OperationSecurityDescriptor{descriptor},
	)(handler)
	handler = rtauth.Middleware(rtauth.MiddlewareConfig{
		AccessTokenVerifier:      verifier,
		AccountSecurityAuthority: authority,
	})(handler)
	return httpadapter.PreserveCredentialTransport(handler)
}

func executeIntegrationRequest(
	t *testing.T,
	client *http.Client,
	token string,
) *http.Response {
	t.Helper()
	response, err := executeIntegrationRequestResult(client, token)
	if err != nil {
		t.Fatalf("execute edge request: %v", err)
	}
	return response
}

func executeIntegrationRequestResult(
	client *http.Client,
	token string,
) (*http.Response, error) {
	request, err := http.NewRequest(http.MethodPost, "http://api-edge.local/content/posts", strings.NewReader(`{"title":"single track"}`))
	if err != nil {
		return nil, err
	}
	request.Header.Set("Authorization", "Bearer "+token)
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", "same-key-does-not-bypass-admission")
	request.Header.Set("X-Edge-Client-IP", "198.51.100.20")
	response, err := client.Do(request)
	if err != nil {
		return nil, err
	}
	return response, nil
}

func executeSessionIntegrationRequest(
	t *testing.T,
	client *http.Client,
	token string,
) *http.Response {
	t.Helper()
	request, err := http.NewRequest(http.MethodPost, "http://api-edge.local/realtime/tickets", nil)
	if err != nil {
		t.Fatalf("new IssueConnectionTicket request: %v", err)
	}
	request.Header.Set("Authorization", "Bearer "+token)
	request.Header.Set("X-Edge-Client-IP", "198.51.100.20")
	response, err := client.Do(request)
	if err != nil {
		t.Fatalf("execute IssueConnectionTicket request: %v", err)
	}
	return response
}

func assertTypedAdmissionError(
	t *testing.T,
	response *http.Response,
	wantStatus int,
	wantCode string,
) int {
	t.Helper()
	defer response.Body.Close()
	var body rterr.ErrorResponse
	if err := json.NewDecoder(response.Body).Decode(&body); err != nil {
		t.Fatalf("decode status=%d response: %v", response.StatusCode, err)
	}
	if response.StatusCode != wantStatus || body.Code != wantCode {
		t.Fatalf("status=%d code=%q want status=%d code=%q", response.StatusCode, body.Code, wantStatus, wantCode)
	}
	headerSeconds, err := strconv.Atoi(response.Header.Get("Retry-After"))
	if err != nil {
		t.Fatalf("Retry-After=%q: %v", response.Header.Get("Retry-After"), err)
	}
	if headerSeconds != body.Recovery.AfterSeconds ||
		body.Recovery.Action != "retry" ||
		body.Recovery.DisruptionLevel != "snackbar" {
		t.Fatalf("Retry-After=%d recovery=%+v", headerSeconds, body.Recovery)
	}
	return headerSeconds
}

func assertAdmissionMetricContract(t *testing.T, registry *prometheus.Registry) {
	t.Helper()
	families, err := registry.Gather()
	if err != nil {
		t.Fatalf("gather admission metrics: %v", err)
	}
	outcomes := map[string]bool{}
	for _, family := range families {
		if family.GetName() != "api_edge_admission_decisions_total" {
			continue
		}
		for _, metric := range family.Metric {
			for _, label := range metric.Label {
				name := label.GetName()
				if name == "subject" || name == "persona" || name == "stage" || name == "instance" {
					t.Fatalf("high-cardinality or rollout label escaped: %s", name)
				}
				if name == "outcome" {
					outcomes[label.GetValue()] = true
				}
			}
		}
	}
	for _, required := range []string{"allowed", "rate_limited", "state_unavailable_denied"} {
		if !outcomes[required] {
			t.Fatalf("missing admission metric outcome %q: %v", required, outcomes)
		}
	}
}

func startUnixHTTPReplica(t *testing.T, stage string, handler http.Handler) *http.Client {
	t.Helper()
	socket := filepath.Join(shortTempDir(t), string(stage[0])+".sock")
	listener, err := net.Listen("unix", socket)
	if err != nil {
		t.Fatalf("listen %s replica: %v", stage, err)
	}
	server := &http.Server{Handler: handler, ReadHeaderTimeout: time.Second}
	serveDone := make(chan error, 1)
	go func() { serveDone <- server.Serve(listener) }()
	t.Cleanup(func() {
		shutdownContext, cancel := context.WithTimeout(context.Background(), time.Second)
		defer cancel()
		_ = server.Shutdown(shutdownContext)
		if serveErr := <-serveDone; serveErr != nil && !errors.Is(serveErr, http.ErrServerClosed) {
			t.Errorf("%s replica serve: %v", stage, serveErr)
		}
	})
	transport := &http.Transport{DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
		return (&net.Dialer{Timeout: time.Second}).DialContext(ctx, "unix", socket)
	}}
	t.Cleanup(transport.CloseIdleConnections)
	return &http.Client{Transport: transport, Timeout: 3 * time.Second}
}

func startRedisServer(t *testing.T) (string, func()) {
	t.Helper()
	binary, err := exec.LookPath("redis-server")
	if err != nil {
		t.Fatalf("redis-server is required for api_integration: %v", err)
	}
	socket := filepath.Join(shortTempDir(t), "r.sock")
	command := exec.Command(
		binary,
		"--port", "0",
		"--unixsocket", socket,
		"--unixsocketperm", "700",
		"--save", "",
		"--appendonly", "no",
	)
	var logs bytes.Buffer
	command.Stdout = &logs
	command.Stderr = &logs
	if err := command.Start(); err != nil {
		t.Fatalf("start redis-server: %v", err)
	}
	var stopOnce sync.Once
	stop := func() {
		stopOnce.Do(func() {
			if command.Process != nil {
				_ = command.Process.Kill()
			}
			_ = command.Wait()
		})
	}
	t.Cleanup(stop)

	address := "unix://" + socket
	deadline := time.Now().Add(3 * time.Second)
	for {
		client, clientErr := redisstore.NewClient(redisstore.Config{
			Mode:         "standalone",
			Addr:         address,
			PoolSize:     1,
			DialTimeout:  100 * time.Millisecond,
			ReadTimeout:  100 * time.Millisecond,
			WriteTimeout: 100 * time.Millisecond,
		})
		if clientErr == nil {
			pingContext, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
			pingErr := client.Ping(pingContext).Err()
			cancel()
			_ = client.Close()
			if pingErr == nil {
				return address, stop
			}
		}
		if time.Now().After(deadline) {
			stop()
			t.Fatalf("redis-server did not become ready: %s", logs.String())
		}
		time.Sleep(20 * time.Millisecond)
	}
}

func shortTempDir(t *testing.T) string {
	t.Helper()
	directory, err := os.MkdirTemp(os.TempDir(), "qe-")
	if err != nil {
		t.Fatalf("create short temporary directory: %v", err)
	}
	t.Cleanup(func() {
		if err := os.RemoveAll(directory); err != nil {
			t.Errorf("remove temporary directory %s: %v", directory, err)
		}
	})
	return directory
}

func readBody(response *http.Response) string {
	defer response.Body.Close()
	var body bytes.Buffer
	_, _ = body.ReadFrom(response.Body)
	return body.String()
}

type staticAuthority struct {
	snapshot rtauth.AccountSecuritySnapshot
	err      error
}

func (authority staticAuthority) ReadAccountSecurity(
	context.Context,
	string,
) (rtauth.AccountSecuritySnapshot, error) {
	return authority.snapshot, authority.err
}
