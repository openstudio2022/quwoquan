package es

import (
	"bytes"
	"context"
	"crypto/tls"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"sync/atomic"
	"time"

	rtsearch "quwoquan_service/runtime/search"
)

var ErrIndexSchemaIncompatible = errors.New("search index schema is incompatible")

// Config is the ES/OpenSearch connection + index configuration. It is supplied by
// the service from its package effective config (schema defaults plus one environment override)
// rather than read ad-hoc from os.Getenv in business code, so
// endpoints/credentials are auditable.
type Config struct {
	// Endpoints are base URLs (scheme+host[:port]); multiple enable failover.
	Endpoints []string
	// Username/Password (basic auth) or APIKey (ES API key); APIKey takes priority.
	Username string
	Password string
	APIKey   string
	// Index defaults to DefaultIndex when empty.
	Index string
	// RequestTimeout caps each HTTP round trip (default 5s).
	RequestTimeout time.Duration
	// InsecureTLS skips TLS verification (dev/self-signed only).
	InsecureTLS bool
	// Schema drives index settings/mappings on EnsureIndex.
	Schema IndexSchemaConfig
}

// Client is the production HTTP Searcher + Writer for ES/OpenSearch. It satisfies
// both the es.Searcher and es.Writer interfaces, and additionally manages index
// creation, bulk writes, and liveness probing.
type Client struct {
	cfg   Config
	http  *http.Client
	index string
	next  uint32 // round-robin cursor across endpoints
}

// Compile-time guarantees the client satisfies the transport interfaces.
var (
	_ Searcher = (*Client)(nil)
	_ Writer   = (*Client)(nil)
)

// NewClient validates the config and builds the HTTP client.
func NewClient(cfg Config) (*Client, error) {
	eps := make([]string, 0, len(cfg.Endpoints))
	for _, e := range cfg.Endpoints {
		e = strings.TrimRight(strings.TrimSpace(e), "/")
		if e != "" {
			eps = append(eps, e)
		}
	}
	if len(eps) == 0 {
		return nil, fmt.Errorf("es: no endpoints configured")
	}
	cfg.Endpoints = eps
	if strings.TrimSpace(cfg.Index) == "" {
		cfg.Index = DefaultIndex
	}
	timeout := cfg.RequestTimeout
	if timeout <= 0 {
		timeout = 5 * time.Second
	}
	transport := &http.Transport{}
	if cfg.InsecureTLS {
		transport.TLSClientConfig = &tls.Config{InsecureSkipVerify: true} //nolint:gosec // dev/self-signed only, gated by config
	}
	return &Client{
		cfg:   cfg,
		http:  &http.Client{Timeout: timeout, Transport: transport},
		index: cfg.Index,
	}, nil
}

// IndexName returns the configured unified index name.
func (c *Client) IndexName() string { return c.index }

// Search implements es.Searcher: POST {index}/_search and maps hits back to
// RecallCandidate (the shared ranker re-scores; this stays a thin transport).
func (c *Client) Search(ctx context.Context, index string, body map[string]any) ([]rtsearch.RecallCandidate, error) {
	if strings.TrimSpace(index) == "" {
		index = c.index
	}
	status, data, err := c.send(ctx, http.MethodPost, "/"+index+"/_search", body, "application/json")
	if err != nil {
		return nil, err
	}
	if status < 200 || status >= 300 {
		return nil, fmt.Errorf("es: search status %d: %s", status, truncateBytes(data, 300))
	}
	var parsed searchResponse
	if err := json.Unmarshal(data, &parsed); err != nil {
		return nil, fmt.Errorf("es: decode search response: %w", err)
	}
	out := make([]rtsearch.RecallCandidate, 0, len(parsed.Hits.Hits))
	for _, h := range parsed.Hits.Hits {
		out = append(out, IndexToCandidate(h.Source, h.Score))
	}
	return out, nil
}

// Upsert implements es.Writer: idempotent PUT {index}/_doc/{id}.
func (c *Client) Upsert(ctx context.Context, index, id string, doc map[string]any) error {
	if strings.TrimSpace(index) == "" {
		index = c.index
	}
	status, data, err := c.send(ctx, http.MethodPut, "/"+index+"/_doc/"+url.PathEscape(id), doc, "application/json")
	if err != nil {
		return err
	}
	if status < 200 || status >= 300 {
		return fmt.Errorf("es: upsert status %d: %s", status, truncateBytes(data, 300))
	}
	return nil
}

// Delete implements es.Writer: DELETE {index}/_doc/{id}; a missing doc is not an
// error (idempotent replay).
func (c *Client) Delete(ctx context.Context, index, id string) error {
	if strings.TrimSpace(index) == "" {
		index = c.index
	}
	status, data, err := c.send(ctx, http.MethodDelete, "/"+index+"/_doc/"+url.PathEscape(id), nil, "application/json")
	if err != nil {
		return err
	}
	if status == http.StatusNotFound {
		return nil
	}
	if status < 200 || status >= 300 {
		return fmt.Errorf("es: delete status %d: %s", status, truncateBytes(data, 300))
	}
	return nil
}

// Bulk applies a batch of change events in one _bulk round trip.
func (c *Client) Bulk(ctx context.Context, index string, events []ChangeEvent) error {
	if strings.TrimSpace(index) == "" {
		index = c.index
	}
	if len(events) == 0 {
		return nil
	}
	var buf bytes.Buffer
	for _, ev := range events {
		id := IndexID(ev.Doc)
		if ev.Op == OpDelete {
			meta, _ := json.Marshal(map[string]any{"delete": map[string]any{"_index": index, "_id": id}})
			buf.Write(meta)
			buf.WriteByte('\n')
			continue
		}
		meta, _ := json.Marshal(map[string]any{"index": map[string]any{"_index": index, "_id": id}})
		docLine, _ := json.Marshal(DocumentToIndex(ev.Doc))
		buf.Write(meta)
		buf.WriteByte('\n')
		buf.Write(docLine)
		buf.WriteByte('\n')
	}
	status, data, err := c.send(ctx, http.MethodPost, "/_bulk", buf.Bytes(), "application/x-ndjson")
	if err != nil {
		return err
	}
	if status < 200 || status >= 300 {
		return fmt.Errorf("es: bulk status %d: %s", status, truncateBytes(data, 300))
	}
	var br struct {
		Errors bool `json:"errors"`
	}
	if err := json.Unmarshal(data, &br); err == nil && br.Errors {
		return fmt.Errorf("es: bulk reported item errors: %s", truncateBytes(data, 500))
	}
	return nil
}

// EnsureIndex creates the unified index with the configured analyzer/mappings if
// it does not already exist. Safe to call on every boot (idempotent).
func (c *Client) EnsureIndex(ctx context.Context) error {
	status, _, err := c.send(ctx, http.MethodHead, "/"+c.index, nil, "application/json")
	if err != nil {
		return err
	}
	if status == http.StatusOK {
		mappingStatus, mappingData, mappingErr := c.send(
			ctx,
			http.MethodPut,
			"/"+c.index+"/_mapping",
			buildIndexMappings(c.cfg.Schema),
			"application/json",
		)
		if mappingErr != nil {
			return mappingErr
		}
		if mappingStatus >= 200 && mappingStatus < 300 {
			return nil
		}
		if mappingStatus == http.StatusBadRequest {
			return fmt.Errorf(
				"%w: update mapping status %d: %s",
				ErrIndexSchemaIncompatible,
				mappingStatus,
				truncateBytes(mappingData, 300),
			)
		}
		return fmt.Errorf(
			"es: update mapping status %d: %s",
			mappingStatus,
			truncateBytes(mappingData, 300),
		)
	}
	if status != http.StatusNotFound {
		return fmt.Errorf("es: head index status %d", status)
	}
	createStatus, createData, createErr := c.send(ctx, http.MethodPut, "/"+c.index, BuildCreateIndexBody(c.cfg.Schema), "application/json")
	if createErr != nil {
		return createErr
	}
	if createStatus < 200 || createStatus >= 300 {
		// Tolerate a concurrent creator winning the race.
		if createStatus == http.StatusBadRequest && bytes.Contains(createData, []byte("resource_already_exists_exception")) {
			return nil
		}
		return fmt.Errorf("es: create index status %d: %s", createStatus, truncateBytes(createData, 300))
	}
	return nil
}

// Ping checks cluster liveness (GET /), used by the service health checker.
func (c *Client) Ping(ctx context.Context) error {
	status, data, err := c.send(ctx, http.MethodGet, "/", nil, "application/json")
	if err != nil {
		return err
	}
	if status < 200 || status >= 300 {
		return fmt.Errorf("es: ping status %d: %s", status, truncateBytes(data, 200))
	}
	return nil
}

// send performs one request, failing over across endpoints on transport errors.
func (c *Client) send(ctx context.Context, method, path string, body any, contentType string) (int, []byte, error) {
	var payload []byte
	switch b := body.(type) {
	case nil:
		payload = nil
	case []byte:
		payload = b
	default:
		marshaled, err := json.Marshal(body)
		if err != nil {
			return 0, nil, fmt.Errorf("es: marshal request: %w", err)
		}
		payload = marshaled
	}

	n := len(c.cfg.Endpoints)
	start := int(atomic.AddUint32(&c.next, 1))
	var lastErr error
	for i := 0; i < n; i++ {
		base := c.cfg.Endpoints[(start+i)%n]
		var reader io.Reader
		if payload != nil {
			reader = bytes.NewReader(payload)
		}
		req, err := http.NewRequestWithContext(ctx, method, base+path, reader)
		if err != nil {
			return 0, nil, err
		}
		if payload != nil {
			req.Header.Set("Content-Type", contentType)
		}
		req.Header.Set("Accept", "application/json")
		c.applyAuth(req)

		resp, err := c.http.Do(req)
		if err != nil {
			lastErr = err
			continue // transport failure: try the next endpoint
		}
		data, readErr := io.ReadAll(resp.Body)
		_ = resp.Body.Close()
		if readErr != nil {
			lastErr = readErr
			continue
		}
		return resp.StatusCode, data, nil
	}
	if lastErr == nil {
		lastErr = fmt.Errorf("no endpoints")
	}
	return 0, nil, fmt.Errorf("es: all endpoints failed: %w", lastErr)
}

func (c *Client) applyAuth(req *http.Request) {
	switch {
	case c.cfg.APIKey != "":
		req.Header.Set("Authorization", "ApiKey "+c.cfg.APIKey)
	case c.cfg.Username != "":
		req.SetBasicAuth(c.cfg.Username, c.cfg.Password)
	}
}

type searchResponse struct {
	Hits struct {
		Hits []struct {
			ID     string         `json:"_id"`
			Score  float64        `json:"_score"`
			Source map[string]any `json:"_source"`
		} `json:"hits"`
	} `json:"hits"`
}

func truncateBytes(b []byte, n int) string {
	s := string(b)
	if len(s) > n {
		return s[:n]
	}
	return s
}
