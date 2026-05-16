package persistence

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"
	"time"

	"quwoquan_service/services/product-ops-service/internal/application"
)

type ElasticsearchEventMirror struct {
	baseURL string
	client  *http.Client
}

func NewElasticsearchEventMirror(baseURL string, opts ...func(*ElasticsearchEventMirror)) *ElasticsearchEventMirror {
	m := &ElasticsearchEventMirror{
		baseURL: strings.TrimRight(strings.TrimSpace(baseURL), "/"),
		client:  &http.Client{Timeout: 5 * time.Second},
	}
	for _, opt := range opts {
		opt(m)
	}
	return m
}

func WithESHTTPClient(c *http.Client) func(*ElasticsearchEventMirror) {
	return func(m *ElasticsearchEventMirror) { m.client = c }
}

func (m *ElasticsearchEventMirror) MirrorEvents(ctx context.Context, events []application.EventDrilldownItem) error {
	if m == nil || m.baseURL == "" || len(events) == 0 {
		return nil
	}
	var bulk bytes.Buffer
	for _, event := range events {
		if event.EventType != "exception" && event.EventName != "runtime_exception" {
			continue
		}
		index := "quwoquan-exceptions-" + eventDate(event.OccurredAt)
		meta := map[string]any{"index": map[string]any{"_index": index, "_id": event.EventID}}
		if err := writeJSONLine(&bulk, meta); err != nil {
			return err
		}
		if err := writeJSONLine(&bulk, event); err != nil {
			return err
		}
	}
	if bulk.Len() == 0 {
		return nil
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, m.baseURL+"/_bulk", &bulk)
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/x-ndjson")
	resp, err := m.client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		return fmt.Errorf("elasticsearch mirror status=%d", resp.StatusCode)
	}
	return nil
}

func writeJSONLine(buf *bytes.Buffer, value any) error {
	data, err := json.Marshal(value)
	if err != nil {
		return err
	}
	buf.Write(data)
	buf.WriteByte('\n')
	return nil
}

func eventDate(raw string) string {
	parsed, err := time.Parse(time.RFC3339Nano, raw)
	if err != nil {
		return time.Now().UTC().Format("2006.01.02")
	}
	return parsed.UTC().Format("2006.01.02")
}
