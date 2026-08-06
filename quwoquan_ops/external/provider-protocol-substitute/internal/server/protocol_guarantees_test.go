package server

import (
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"fmt"
	"net"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"testing"
)

func TestIdempotencyReplaysOneEffectAndRejectsConflictingPayload(t *testing.T) {
	server, _ := newTestServer(t)
	handler := server.Handler()
	key := "native-idempotency-scene-0001"
	headers := http.Header{
		"Content-Type":    []string{"application/json"},
		idempotencyHeader: []string{key},
	}
	first := perform(
		handler,
		http.MethodPost,
		"/push/send",
		strings.NewReader(`{"requestId":"native-one"}`),
		headers,
	)
	replayHeaders := headers.Clone()
	replayHeaders.Set("X-Request-ID", "second-transport-attempt")
	replay := perform(
		handler,
		http.MethodPost,
		"/push/send",
		strings.NewReader(`{"requestId":"native-one"}`),
		replayHeaders,
	)
	conflict := perform(
		handler,
		http.MethodPost,
		"/push/send",
		strings.NewReader(`{"requestId":"native-conflict"}`),
		headers,
	)
	if first.Code != http.StatusAccepted || replay.Code != http.StatusAccepted ||
		first.Body.String() != replay.Body.String() || conflict.Code != http.StatusConflict {
		t.Fatalf(
			"idempotency statuses/body first=%d replay=%d conflict=%d",
			first.Code,
			replay.Code,
			conflict.Code,
		)
	}

	readback := performOperator(handler, http.MethodGet, "/control/readback", nil)
	var payload struct {
		Effects     map[string]uint64       `json:"effects"`
		Invocations []InvocationLedgerEntry `json:"invocations"`
	}
	if err := json.Unmarshal(readback.Body.Bytes(), &payload); err != nil {
		t.Fatal(err)
	}
	if payload.Effects["integration.push.delivery/deliver"] != 1 ||
		len(payload.Invocations) != 3 {
		t.Fatalf("idempotency readback=%s", readback.Body.String())
	}
	states := []string{"new", "replay", "conflict"}
	for index, expected := range states {
		entry := payload.Invocations[index]
		if entry.IdempotencyState != expected ||
			entry.IdempotencyKeyDigest == "" ||
			entry.EffectOrdinal != payload.Invocations[0].EffectOrdinal {
			t.Fatalf("entry[%d]=%+v", index, entry)
		}
	}
}

func TestCallbackChannelRecordsStrictCompletionOrderAndCleansUp(t *testing.T) {
	server, _ := newTestServer(t)
	handler := server.Handler()
	payload := fmt.Sprintf(`{
		"environment":"alpha",
		"target":"alpha-local",
		"configurationDigest":%q,
		"runtimeCompositionDigest":%q,
		"capabilityId":"integration.push.delivery",
		"operation":"deliver",
		"owner":"attempt:callback-order",
		"ttlSeconds":30,
		"maxCallbacks":2
	}`, testConfigurationDigest, testRuntimeDigest)
	created := performOperator(
		handler,
		http.MethodPost,
		"/control/callback-channels",
		strings.NewReader(payload),
	)
	if created.Code != http.StatusCreated {
		t.Fatalf("create callback channel=%d %s", created.Code, created.Body.String())
	}
	var channel CallbackChannel
	if err := json.Unmarshal(created.Body.Bytes(), &channel); err != nil {
		t.Fatal(err)
	}
	for index := 1; index <= 2; index++ {
		headers := http.Header{
			"Content-Type":        []string{"application/json"},
			callbackChannelHeader: []string{channel.ChannelID},
			"X-Request-ID":        []string{fmt.Sprintf("callback-%d", index)},
		}
		response := perform(
			handler,
			http.MethodPost,
			"/push/send",
			strings.NewReader(fmt.Sprintf(`{"requestId":"callback-%d"}`, index)),
			headers,
		)
		if response.Code != http.StatusAccepted {
			t.Fatalf("callback invocation %d=%d %s", index, response.Code, response.Body.String())
		}
	}
	state := performOperator(
		handler,
		http.MethodGet,
		"/control/callback-channels/"+channel.ChannelID,
		nil,
	)
	if err := json.Unmarshal(state.Body.Bytes(), &channel); err != nil {
		t.Fatal(err)
	}
	if channel.State != "exhausted" || len(channel.Events) != 2 ||
		channel.Events[0].Sequence != 1 || channel.Events[1].Sequence != 2 ||
		channel.Events[0].CallOrdinal >= channel.Events[1].CallOrdinal ||
		channel.CleanupReceipt == nil || channel.CleanupReceipt.Status != "restored" {
		t.Fatalf("callback channel=%+v", channel)
	}
}

func TestTLSLedgerBindsDNSAuthorityAndTLS13(t *testing.T) {
	server, _ := newTestServer(t)
	tlsServer := httptest.NewUnstartedServer(server.Handler())
	tlsServer.StartTLS()
	defer tlsServer.Close()
	parsed, err := url.Parse(tlsServer.URL)
	if err != nil {
		t.Fatal(err)
	}
	pool := x509.NewCertPool()
	pool.AddCert(tlsServer.Certificate())
	transport := &http.Transport{
		TLSClientConfig: &tls.Config{
			MinVersion: tls.VersionTLS13,
			RootCAs:    pool,
			ServerName: "example.com",
		},
		DialContext: func(ctx context.Context, network, _ string) (net.Conn, error) {
			return (&net.Dialer{}).DialContext(ctx, network, parsed.Host)
		},
	}
	client := &http.Client{Transport: transport}
	request, err := http.NewRequest(
		http.MethodGet,
		"https://example.com:"+parsed.Port()+"/weather/forecast",
		nil,
	)
	if err != nil {
		t.Fatal(err)
	}
	response, err := client.Do(request)
	if err != nil {
		t.Fatal(err)
	}
	_ = response.Body.Close()
	readback := performOperator(server.Handler(), http.MethodGet, "/control/readback", nil)
	var payload struct {
		Invocations []InvocationLedgerEntry `json:"invocations"`
	}
	if err := json.Unmarshal(readback.Body.Bytes(), &payload); err != nil {
		t.Fatal(err)
	}
	if len(payload.Invocations) != 1 ||
		payload.Invocations[0].NetworkHostDigest != digestText("dns\nexample.com") ||
		payload.Invocations[0].TLSServerNameDigest != digestText("dns\nexample.com") ||
		payload.Invocations[0].TLSVersion != "TLSv1.3" {
		t.Fatalf("TLS ledger=%+v", payload.Invocations)
	}
}
