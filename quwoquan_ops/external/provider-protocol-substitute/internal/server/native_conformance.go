package server

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/hex"
	"encoding/json"
	"encoding/pem"
	"errors"
	"fmt"
	"io"
	"math/big"
	"net"
	"net/http"
	"net/url"
	"os"
	"sort"
	"strings"
	"time"
)

const (
	nativeAssertionMarker = "QWQ_PROVIDER_CONFORMANCE_ASSERTION:"
	nativeCleanupMarker   = "QWQ_PROVIDER_CONFORMANCE_CLEANUP:"
)

var nativePublicAssertions = map[string]struct{}{
	"provider.success":           {},
	"provider.validation":        {},
	"provider.auth":              {},
	"provider.network_dns":       {},
	"provider.timeout":           {},
	"provider.throttle":          {},
	"provider.retry":             {},
	"provider.idempotency":       {},
	"provider.callback_ordering": {},
	"provider.redaction":         {},
	"provider.observability":     {},
}

type nativeHTTPResult struct {
	Status int
	Body   []byte
}

type nativeHarness struct {
	environment      string
	capabilityID     string
	operations       []string
	assertionIDs     []string
	capabilityAssert string
	configuration    string
	runtime          string
	operatorToken    string
	origin           string
	client           *http.Client
	closeServer      func() error
	facts            map[string][]any
	cleanupReceipts  []string
	requestOrdinal   uint64
}

// RunNativeConformance owns the offline Provider assertion receipts. It starts
// the real substitute handler behind a TLS 1.3 localhost listener and derives
// every marker from protocol readback; callers may relay bytes but must not
// create or enrich markers.
func RunNativeConformance(output io.Writer) error {
	harness, err := newNativeHarness()
	if err != nil {
		return err
	}
	defer harness.closeServer()
	if err := harness.execute(); err != nil {
		return err
	}
	return harness.emit(output)
}

func newNativeHarness() (*nativeHarness, error) {
	environment := strings.TrimSpace(os.Getenv("QWQ_PROVIDER_CONFORMANCE_ENVIRONMENT"))
	if environment != "alpha" && environment != "beta" && environment != "gamma" {
		return nil, errors.New("native substitute conformance requires Alpha/Beta/Gamma")
	}
	capabilityID := strings.TrimSpace(os.Getenv("QWQ_PROVIDER_CONFORMANCE_CAPABILITY_ID"))
	operations := canonicalProviderScopes[capabilityID]
	if len(operations) == 0 {
		return nil, errors.New("native substitute capability is not canonical")
	}
	operationNames := make([]string, 0, len(operations))
	for operation := range operations {
		operationNames = append(operationNames, operation)
	}
	sort.Strings(operationNames)
	var assertionIDs []string
	if err := json.Unmarshal(
		[]byte(os.Getenv("QWQ_PROVIDER_CONFORMANCE_ASSERTION_IDS")),
		&assertionIDs,
	); err != nil {
		return nil, errors.New("native substitute assertion IDs are invalid")
	}
	seen := make(map[string]struct{}, len(assertionIDs))
	capabilityAssertions := make([]string, 0, 1)
	for _, assertionID := range assertionIDs {
		if assertionID == "" {
			return nil, errors.New("native substitute assertion ID is empty")
		}
		if _, duplicate := seen[assertionID]; duplicate {
			return nil, errors.New("native substitute assertion IDs are not unique")
		}
		seen[assertionID] = struct{}{}
		if _, public := nativePublicAssertions[assertionID]; !public {
			capabilityAssertions = append(capabilityAssertions, assertionID)
		}
	}
	for assertionID := range nativePublicAssertions {
		if _, found := seen[assertionID]; !found {
			return nil, fmt.Errorf("native substitute assertion %s is missing", assertionID)
		}
	}
	if len(capabilityAssertions) != 1 {
		return nil, errors.New("native substitute requires one capability assertion")
	}
	configuration := digestText("native-config\n" + environment + "\n" + capabilityID)
	runtime := digestText("native-runtime\n" + environment + "\n" + capabilityID)
	operatorBytes := make([]byte, 32)
	if _, err := rand.Read(operatorBytes); err != nil {
		return nil, errors.New("native substitute operator material unavailable")
	}
	operatorToken := hex.EncodeToString(operatorBytes)
	instance, err := New(Config{
		Environment:              environment,
		ConfigurationDigest:      configuration,
		RuntimeCompositionDigest: runtime,
		OperatorToken:            operatorToken,
	})
	if err != nil {
		return nil, err
	}
	origin, client, closeServer, err := startNativeTLSServer(instance.Handler())
	if err != nil {
		return nil, err
	}
	return &nativeHarness{
		environment:      environment,
		capabilityID:     capabilityID,
		operations:       operationNames,
		assertionIDs:     assertionIDs,
		capabilityAssert: capabilityAssertions[0],
		configuration:    configuration,
		runtime:          runtime,
		operatorToken:    operatorToken,
		origin:           origin,
		client:           client,
		closeServer:      closeServer,
		facts:            make(map[string][]any),
	}, nil
}

func (h *nativeHarness) execute() error {
	for _, operation := range h.operations {
		if err := h.executeOperation(operation); err != nil {
			return fmt.Errorf("native %s/%s: %w", h.capabilityID, operation, err)
		}
	}
	readback, err := h.controlJSON(http.MethodGet, "/control/readback", nil, http.StatusOK)
	if err != nil {
		return err
	}
	encoded, err := json.Marshal(readback)
	if err != nil {
		return err
	}
	if bytesContainAny(encoded, h.operatorToken, "native-redaction-canary") {
		return errors.New("native readback leaked protected material")
	}
	invocations, ok := readback["invocations"].([]any)
	if !ok || len(invocations) == 0 {
		return errors.New("native readback has no invocation ledger")
	}
	h.facts["provider.redaction"] = append(h.facts["provider.redaction"], digestText(string(encoded)))
	h.facts["provider.observability"] = append(
		h.facts["provider.observability"],
		map[string]any{"readbackDigest": digestText(string(encoded)), "invocationCount": len(invocations)},
	)
	for _, assertionID := range h.assertionIDs {
		if len(h.facts[assertionID]) == 0 {
			return fmt.Errorf("native assertion %s has no protocol facts", assertionID)
		}
	}
	return nil
}

func (h *nativeHarness) executeOperation(operation string) error {
	success, err := h.invoke(operation, "native-redaction-canary-success", nil, "")
	if err != nil || (success.Status != http.StatusOK && success.Status != http.StatusAccepted) {
		return errors.New("success protocol response is invalid")
	}
	entry, err := h.latestInvocation(operation)
	if err != nil {
		return err
	}
	h.facts["provider.success"] = append(h.facts["provider.success"], entry)
	h.facts[h.capabilityAssert] = append(h.facts[h.capabilityAssert], entry)
	expectedDNS := digestText("dns\nlocalhost")
	if entry["networkHostDigest"] != expectedDNS ||
		entry["tlsServerNameDigest"] != expectedDNS || entry["tlsVersion"] != "TLSv1.3" {
		return errors.New("TLS ledger does not prove localhost DNS authority")
	}
	h.facts["provider.network_dns"] = append(h.facts["provider.network_dns"], entry)

	for _, scene := range []struct {
		assertion  string
		scenario   string
		parameters map[string]int
		status     int
		outcome    string
	}{
		{"provider.validation", "validation", map[string]int{}, 400, "validation_rejected"},
		{"provider.auth", "auth", map[string]int{}, 401, "auth_rejected"},
		{"provider.timeout", "delay_timeout", map[string]int{"delayMillis": 2}, 504, "timeout"},
		{"provider.throttle", "throttle", map[string]int{"retryAfterSeconds": 1}, 429, "throttled"},
	} {
		lease, err := h.acquireFault(operation, scene.scenario, scene.parameters, 1)
		if err != nil {
			return err
		}
		result, err := h.invoke(operation, "native-fault", nil, "")
		if err != nil || result.Status != scene.status {
			return fmt.Errorf("%s status mismatch", scene.scenario)
		}
		invocation, err := h.latestInvocation(operation)
		if err != nil || invocation["outcome"] != scene.outcome ||
			invocation["leaseId"] != lease["leaseId"] {
			return fmt.Errorf("%s invocation mismatch", scene.scenario)
		}
		state, err := h.readFault(fmt.Sprint(lease["leaseId"]))
		if err != nil || state["state"] != "exhausted" {
			return fmt.Errorf("%s did not exhaust", scene.scenario)
		}
		if err := h.captureCleanup(state); err != nil {
			return err
		}
		h.facts[scene.assertion] = append(h.facts[scene.assertion], invocation)
	}

	retryLease, err := h.acquireFault(
		operation,
		"transient_then_success",
		map[string]int{"remainingFailures": 1},
		2,
	)
	if err != nil {
		return err
	}
	firstRetry, err := h.invoke(operation, "native-retry", nil, "")
	if err != nil || firstRetry.Status != http.StatusServiceUnavailable {
		return errors.New("retry transient response is invalid")
	}
	firstRetryEntry, _ := h.latestInvocation(operation)
	secondRetry, err := h.invoke(operation, "native-retry", nil, "")
	if err != nil || (secondRetry.Status != http.StatusOK && secondRetry.Status != http.StatusAccepted) {
		return errors.New("retry recovery response is invalid")
	}
	secondRetryEntry, _ := h.latestInvocation(operation)
	retryState, err := h.readFault(fmt.Sprint(retryLease["leaseId"]))
	if err != nil || retryState["state"] != "exhausted" {
		return errors.New("retry lease did not exhaust")
	}
	if err := h.captureCleanup(retryState); err != nil {
		return err
	}
	h.facts["provider.retry"] = append(
		h.facts["provider.retry"], firstRetryEntry, secondRetryEntry,
	)

	if err := h.executeIdempotency(operation); err != nil {
		return err
	}
	return h.executeCallbackOrdering(operation)
}

func (h *nativeHarness) executeIdempotency(operation string) error {
	before, err := h.controlJSON(
		http.MethodGet,
		"/control/readback",
		nil,
		http.StatusOK,
	)
	if err != nil {
		return err
	}
	scope := providerScopeKey(h.capabilityID, operation)
	beforeEffects, err := nativeEffectCount(before, scope)
	if err != nil {
		return err
	}
	key := fmt.Sprintf("native-idempotency-%s-%d", safeIdentifier(operation), h.requestOrdinal+1)
	first, err := h.invoke(operation, "native-idempotency", map[string]string{idempotencyHeader: key}, "")
	if err != nil {
		return err
	}
	firstEntry, _ := h.latestInvocation(operation)
	replay, err := h.invoke(operation, "native-idempotency", map[string]string{idempotencyHeader: key}, "")
	if err != nil {
		return err
	}
	replayEntry, _ := h.latestInvocation(operation)
	conflict, err := h.invoke(
		operation,
		"native-idempotency",
		map[string]string{idempotencyHeader: key},
		"conformanceConflict=1",
	)
	if err != nil {
		return err
	}
	conflictEntry, _ := h.latestInvocation(operation)
	after, err := h.controlJSON(
		http.MethodGet,
		"/control/readback",
		nil,
		http.StatusOK,
	)
	if err != nil {
		return err
	}
	afterEffects, err := nativeEffectCount(after, scope)
	if err != nil {
		return err
	}
	firstEffect, firstEffectOK := firstEntry["effectOrdinal"].(float64)
	replayEffect, replayEffectOK := replayEntry["effectOrdinal"].(float64)
	conflictEffect, conflictEffectOK := conflictEntry["effectOrdinal"].(float64)
	firstKeyDigest := fmt.Sprint(firstEntry["idempotencyKeyDigest"])
	if first.Status != replay.Status || string(first.Body) != string(replay.Body) ||
		conflict.Status != http.StatusConflict || firstEntry["idempotencyState"] != "new" ||
		replayEntry["idempotencyState"] != "replay" ||
		conflictEntry["idempotencyState"] != "conflict" ||
		!firstEffectOK || !replayEffectOK || !conflictEffectOK || firstEffect <= 0 ||
		firstEffect != replayEffect || firstEffect != conflictEffect ||
		firstKeyDigest == "" || firstKeyDigest != fmt.Sprint(replayEntry["idempotencyKeyDigest"]) ||
		firstKeyDigest != fmt.Sprint(conflictEntry["idempotencyKeyDigest"]) ||
		afterEffects-beforeEffects != 1 {
		return errors.New("idempotency ledger did not prove one effect")
	}
	h.facts["provider.idempotency"] = append(
		h.facts["provider.idempotency"], firstEntry, replayEntry, conflictEntry,
	)
	return nil
}

func (h *nativeHarness) executeCallbackOrdering(operation string) error {
	owner := "attempt:native-callback-" + safeIdentifier(operation)
	channel, err := h.controlJSON(
		http.MethodPost,
		"/control/callback-channels",
		map[string]any{
			"environment":              h.environment,
			"target":                   h.environment + "-local",
			"configurationDigest":      h.configuration,
			"runtimeCompositionDigest": h.runtime,
			"capabilityId":             h.capabilityID,
			"operation":                operation,
			"owner":                    owner,
			"ttlSeconds":               30,
			"maxCallbacks":             2,
		},
		http.StatusCreated,
	)
	if err != nil {
		return err
	}
	channelID := fmt.Sprint(channel["channelId"])
	invocations := make([]map[string]any, 0, 2)
	for index := 1; index <= 2; index++ {
		result, invokeErr := h.invoke(
			operation,
			fmt.Sprintf("native-callback-%d", index),
			map[string]string{callbackChannelHeader: channelID},
			"",
		)
		if invokeErr != nil || (result.Status != http.StatusOK && result.Status != http.StatusAccepted) {
			return errors.New("callback source invocation failed")
		}
		invocation, invocationErr := h.latestInvocation(operation)
		if invocationErr != nil {
			return invocationErr
		}
		invocations = append(invocations, invocation)
	}
	state, err := h.controlJSON(
		http.MethodGet,
		"/control/callback-channels/"+channelID,
		nil,
		http.StatusOK,
	)
	if err != nil || state["state"] != "exhausted" {
		return errors.New("callback channel did not exhaust")
	}
	events, ok := state["events"].([]any)
	if !ok || len(events) != 2 {
		return errors.New("callback channel has incomplete events")
	}
	first, firstOK := events[0].(map[string]any)
	second, secondOK := events[1].(map[string]any)
	firstCall, firstCallOK := first["callOrdinal"].(float64)
	secondCall, secondCallOK := second["callOrdinal"].(float64)
	firstEffect, firstEffectOK := first["effectOrdinal"].(float64)
	secondEffect, secondEffectOK := second["effectOrdinal"].(float64)
	if !firstOK || !secondOK || first["sequence"] != float64(1) ||
		second["sequence"] != float64(2) ||
		!firstCallOK || !secondCallOK || firstCall >= secondCall ||
		!firstEffectOK || !secondEffectOK || firstEffect <= 0 ||
		firstEffect >= secondEffect ||
		first["callOrdinal"] != invocations[0]["callOrdinal"] ||
		second["callOrdinal"] != invocations[1]["callOrdinal"] ||
		first["effectOrdinal"] != invocations[0]["effectOrdinal"] ||
		second["effectOrdinal"] != invocations[1]["effectOrdinal"] ||
		first["requestDigest"] != invocations[0]["requestDigest"] ||
		second["requestDigest"] != invocations[1]["requestDigest"] ||
		first["traceDigest"] != invocations[0]["traceDigest"] ||
		second["traceDigest"] != invocations[1]["traceDigest"] ||
		first["requestDigest"] == second["requestDigest"] {
		return errors.New("callback channel sequence is not monotonic")
	}
	if err := h.captureCleanup(state); err != nil {
		return err
	}
	h.facts["provider.callback_ordering"] = append(
		h.facts["provider.callback_ordering"], first, second,
	)
	return nil
}

func nativeEffectCount(readback map[string]any, scope string) (float64, error) {
	effects, ok := readback["effects"].(map[string]any)
	if !ok {
		return 0, errors.New("native effect readback is absent")
	}
	value := effects[scope]
	if value == nil {
		return 0, nil
	}
	count, ok := value.(float64)
	if !ok || count < 0 {
		return 0, errors.New("native effect readback is invalid")
	}
	return count, nil
}

func (h *nativeHarness) invoke(
	operation string,
	canary string,
	headers map[string]string,
	extraQuery string,
) (nativeHTTPResult, error) {
	method, path, body, err := nativeProbe(h.capabilityID, operation, canary)
	if err != nil {
		return nativeHTTPResult{}, err
	}
	if extraQuery != "" {
		separator := "?"
		if strings.Contains(path, "?") {
			separator = "&"
		}
		path += separator + extraQuery
	}
	h.requestOrdinal++
	if headers == nil {
		headers = make(map[string]string)
	}
	headers["X-Request-ID"] = fmt.Sprintf("native-%d", h.requestOrdinal)
	headers["traceparent"] = fmt.Sprintf(
		"00-%032x-%016x-01",
		h.requestOrdinal,
		h.requestOrdinal,
	)
	return h.httpRequest(method, path, body, headers)
}

func (h *nativeHarness) acquireFault(
	operation string,
	scenario string,
	parameters map[string]int,
	maxMatches int,
) (map[string]any, error) {
	return h.controlJSON(
		http.MethodPost,
		"/control/fault-leases",
		map[string]any{
			"environment":              h.environment,
			"target":                   h.environment + "-local",
			"configurationDigest":      h.configuration,
			"runtimeCompositionDigest": h.runtime,
			"capabilityId":             h.capabilityID,
			"operation":                operation,
			"scenario":                 scenario,
			"parameters":               parameters,
			"owner":                    "attempt:native-fault-" + safeIdentifier(operation),
			"ttlSeconds":               30,
			"maxMatches":               maxMatches,
		},
		http.StatusCreated,
	)
}

func (h *nativeHarness) readFault(leaseID string) (map[string]any, error) {
	return h.controlJSON(
		http.MethodGet,
		"/control/fault-leases/"+leaseID,
		nil,
		http.StatusOK,
	)
}

func (h *nativeHarness) captureCleanup(state map[string]any) error {
	receipt, ok := state["cleanupReceipt"].(map[string]any)
	if !ok || receipt["status"] != "restored" {
		return errors.New("native scene cleanup receipt is missing")
	}
	ref := fmt.Sprint(receipt["receiptRef"])
	if !strings.HasPrefix(ref, "receipt:provider-") {
		return errors.New("native scene cleanup receipt is invalid")
	}
	h.cleanupReceipts = append(h.cleanupReceipts, ref)
	return nil
}

func (h *nativeHarness) latestInvocation(operation string) (map[string]any, error) {
	readback, err := h.controlJSON(http.MethodGet, "/control/readback", nil, http.StatusOK)
	if err != nil {
		return nil, err
	}
	invocations, ok := readback["invocations"].([]any)
	if !ok {
		return nil, errors.New("native invocation ledger is absent")
	}
	for index := len(invocations) - 1; index >= 0; index-- {
		entry, entryOK := invocations[index].(map[string]any)
		if entryOK && entry["capabilityId"] == h.capabilityID && entry["operation"] == operation {
			return entry, nil
		}
	}
	return nil, errors.New("native invocation ledger did not record operation")
}

func (h *nativeHarness) controlJSON(
	method string,
	path string,
	body map[string]any,
	expectedStatus int,
) (map[string]any, error) {
	result, err := h.httpRequest(
		method,
		path,
		body,
		map[string]string{"Authorization": "Bearer " + h.operatorToken},
	)
	if err != nil || result.Status != expectedStatus {
		return nil, fmt.Errorf("native control %s returned %d", path, result.Status)
	}
	var payload map[string]any
	if err := json.Unmarshal(result.Body, &payload); err != nil {
		return nil, errors.New("native control returned malformed JSON")
	}
	return payload, nil
}

func (h *nativeHarness) httpRequest(
	method string,
	path string,
	body map[string]any,
	headers map[string]string,
) (nativeHTTPResult, error) {
	var encoded io.Reader
	if body != nil {
		payload, err := json.Marshal(body)
		if err != nil {
			return nativeHTTPResult{}, err
		}
		encoded = strings.NewReader(string(payload))
	}
	request, err := http.NewRequest(method, h.origin+path, encoded)
	if err != nil {
		return nativeHTTPResult{}, err
	}
	if body != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	for key, value := range headers {
		request.Header.Set(key, value)
	}
	response, err := h.client.Do(request)
	if err != nil {
		return nativeHTTPResult{}, err
	}
	defer response.Body.Close()
	responseBody, err := io.ReadAll(io.LimitReader(response.Body, maximumProviderRequestBytes))
	return nativeHTTPResult{Status: response.StatusCode, Body: responseBody}, err
}

func (h *nativeHarness) emit(output io.Writer) error {
	for _, assertionID := range h.assertionIDs {
		digest := digestJSON(map[string]any{
			"environment":  h.environment,
			"capabilityId": h.capabilityID,
			"assertionId":  assertionID,
			"runtime":      h.runtime,
			"facts":        h.facts[assertionID],
		})
		marker := map[string]any{
			"assertionId":     assertionID,
			"status":          "passed",
			"sceneReceiptRef": "receipt:provider-native-scene:" + digest[:24],
			"logRef":          "log:provider-protocol-substitute:" + digest[:24],
			"traceRef":        "trace:provider-protocol-substitute:" + digest[24:48],
			"metricRefs": []string{
				"metric:provider-protocol-substitute:" + safeIdentifier(assertionID),
			},
		}
		encoded, _ := json.Marshal(marker)
		if _, err := fmt.Fprintln(output, nativeAssertionMarker+string(encoded)); err != nil {
			return err
		}
	}
	sort.Strings(h.cleanupReceipts)
	cleanupDigest := digestJSON(map[string]any{
		"environment":  h.environment,
		"capabilityId": h.capabilityID,
		"runtime":      h.runtime,
		"receipts":     h.cleanupReceipts,
	})
	cleanup, _ := json.Marshal(map[string]any{
		"status":     "restored",
		"receiptRef": "receipt:provider-native-cleanup:" + cleanupDigest[:24],
	})
	_, err := fmt.Fprintln(output, nativeCleanupMarker+string(cleanup))
	return err
}

func nativeProbe(
	capabilityID string,
	operation string,
	canary string,
) (string, string, map[string]any, error) {
	switch capabilityID {
	case "assistant.model.generation":
		return http.MethodPost, "/v1/chat/completions", map[string]any{
			"messages": []map[string]string{{"role": "user", "content": canary}},
			"stream":   operation == "stream",
		}, nil
	case "assistant.public.search":
		return http.MethodGet, "/search/html?q=" + url.QueryEscape(canary), nil, nil
	case "assistant.weather.forecast":
		return http.MethodGet, "/weather/forecast?latitude=30.2741&longitude=120.1551", nil, nil
	case "assistant.finance.quote":
		return http.MethodGet, "/finance/chart/000001.SS", nil, nil
	case "content.embedding.generation":
		return http.MethodPost, "/v1/embeddings", map[string]any{"input": []string{canary}}, nil
	case "integration.location.lookup":
		if operation == "nearby" {
			return http.MethodGet, "/map/reverse_geocoding/v3/?location=30.2741%2C120.1551", nil, nil
		}
		return http.MethodGet, "/map/place/v2/search?query=" + url.QueryEscape(canary) + "&location=30.2741%2C120.1551", nil, nil
	case "identity.carrier.one_tap":
		return http.MethodPost, "/carrier/resolve", map[string]any{"token": canary}, nil
	case "identity.social.login":
		if operation == "authorize" {
			return http.MethodPost, "/federated/verify", map[string]any{"action": "authorize", "provider": "alipay"}, nil
		}
		return http.MethodPost, "/federated/verify", map[string]any{
			"action": "resolveIdentity", "provider": "wechat", "code": canary,
		}, nil
	case "integration.push.delivery":
		return http.MethodPost, "/push/send", map[string]any{
			"requestId": canary, "title": "conformance", "body": "conformance",
		}, nil
	default:
		return "", "", nil, errors.New("native capability has no protocol request")
	}
}

func startNativeTLSServer(
	handler http.Handler,
) (string, *http.Client, func() error, error) {
	serverCertificate, root, err := nativeTLSCertificate()
	if err != nil {
		return "", nil, nil, err
	}
	listener, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return "", nil, nil, err
	}
	tlsListener := tls.NewListener(listener, &tls.Config{
		MinVersion:   tls.VersionTLS13,
		Certificates: []tls.Certificate{serverCertificate},
	})
	httpServer := &http.Server{Handler: handler, ReadHeaderTimeout: 3 * time.Second}
	go func() { _ = httpServer.Serve(tlsListener) }()
	pool := x509.NewCertPool()
	pool.AddCert(root)
	client := &http.Client{
		Timeout: 5 * time.Second,
		Transport: &http.Transport{TLSClientConfig: &tls.Config{
			MinVersion: tls.VersionTLS13,
			RootCAs:    pool,
		}},
	}
	_, port, _ := net.SplitHostPort(listener.Addr().String())
	origin := "https://localhost:" + port
	closeServer := func() error {
		ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer cancel()
		return httpServer.Shutdown(ctx)
	}
	return origin, client, closeServer, nil
}

func nativeTLSCertificate() (tls.Certificate, *x509.Certificate, error) {
	now := time.Now().UTC()
	caKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		return tls.Certificate{}, nil, err
	}
	caTemplate := &x509.Certificate{
		SerialNumber:          big.NewInt(1),
		Subject:               pkix.Name{CommonName: "Quwoquan Native Provider Conformance CA"},
		NotBefore:             now.Add(-time.Minute),
		NotAfter:              now.Add(time.Hour),
		IsCA:                  true,
		BasicConstraintsValid: true,
		KeyUsage:              x509.KeyUsageCertSign | x509.KeyUsageDigitalSignature,
	}
	caDER, err := x509.CreateCertificate(rand.Reader, caTemplate, caTemplate, &caKey.PublicKey, caKey)
	if err != nil {
		return tls.Certificate{}, nil, err
	}
	caCertificate, err := x509.ParseCertificate(caDER)
	if err != nil {
		return tls.Certificate{}, nil, err
	}
	leafKey, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		return tls.Certificate{}, nil, err
	}
	leafTemplate := &x509.Certificate{
		SerialNumber: big.NewInt(2),
		Subject:      pkix.Name{CommonName: "localhost"},
		NotBefore:    now.Add(-time.Minute),
		NotAfter:     now.Add(time.Hour),
		DNSNames:     []string{"localhost"},
		IPAddresses:  []net.IP{net.ParseIP("127.0.0.1")},
		ExtKeyUsage:  []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
		KeyUsage:     x509.KeyUsageDigitalSignature,
	}
	leafDER, err := x509.CreateCertificate(
		rand.Reader,
		leafTemplate,
		caCertificate,
		&leafKey.PublicKey,
		caKey,
	)
	if err != nil {
		return tls.Certificate{}, nil, err
	}
	leafKeyDER, err := x509.MarshalPKCS8PrivateKey(leafKey)
	if err != nil {
		return tls.Certificate{}, nil, err
	}
	certificate, err := tls.X509KeyPair(
		pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: leafDER}),
		pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: leafKeyDER}),
	)
	return certificate, caCertificate, err
}

func digestJSON(value any) string {
	encoded, _ := json.Marshal(value)
	return strings.TrimPrefix(digestText(string(encoded)), "sha256:")
}

func safeIdentifier(value string) string {
	return strings.NewReplacer(".", "_", "/", "_", ":", "_").Replace(value)
}

func bytesContainAny(value []byte, candidates ...string) bool {
	text := string(value)
	for _, candidate := range candidates {
		if candidate != "" && strings.Contains(text, candidate) {
			return true
		}
	}
	return false
}
