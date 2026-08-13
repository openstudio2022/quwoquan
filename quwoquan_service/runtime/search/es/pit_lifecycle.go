package es

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"strings"

	rtsearch "quwoquan_service/runtime/search"
)

// ErrPITInvalid marks a search that failed because its point-in-time snapshot
// no longer exists (expired keep_alive, node restart, explicit close). It
// wraps the backend-agnostic rtsearch sentinel so owners fail closed without
// depending on this package.
var ErrPITInvalid = fmt.Errorf("%w: search point-in-time is invalid", rtsearch.ErrPaginationSnapshotInvalid)

// PITKeepAlive is the snapshot lease for one pagination step. Every follow-up
// page renews it, so an actively paging user keeps the snapshot alive while an
// abandoned one releases its segment references within this window.
const PITKeepAlive = "90s"

// OpenPIT opens a point-in-time reader over the read alias and returns its id.
//
// PITs are opened lazily: the first page never pays for one (most searches are
// never paged), the first follow-up page opens it, and later pages renew it via
// the search body. This bounds live PITs to actively-paging users instead of
// every search (peak-RPS x keep_alive would otherwise pin thousands of
// snapshots).
func (c *Client) OpenPIT(ctx context.Context) (string, error) {
	status, data, err := c.send(ctx, http.MethodPost, "/"+c.index+"/_pit?keep_alive="+PITKeepAlive, nil, "application/json")
	if err != nil {
		return "", err
	}
	if status < 200 || status >= 300 {
		if retryableDependencyStatus(status) {
			return "", fmt.Errorf("%w: es open pit status %d", ErrDependencyUnavailable, status)
		}
		return "", fmt.Errorf("es: open pit status %d: %s", status, truncateBytes(data, 300))
	}
	var parsed struct {
		ID string `json:"id"`
	}
	if err := json.Unmarshal(data, &parsed); err != nil || strings.TrimSpace(parsed.ID) == "" {
		return "", fmt.Errorf("es: open pit returned no id: %s", truncateBytes(data, 300))
	}
	return parsed.ID, nil
}

// ClosePIT releases a point-in-time reader (best-effort; an already-expired
// PIT is not an error).
func (c *Client) ClosePIT(ctx context.Context, id string) error {
	if strings.TrimSpace(id) == "" {
		return nil
	}
	status, data, err := c.send(ctx, http.MethodDelete, "/_pit", map[string]any{"id": id}, "application/json")
	if err != nil {
		return err
	}
	if status == http.StatusNotFound {
		return nil
	}
	if status < 200 || status >= 300 {
		return fmt.Errorf("es: close pit status %d: %s", status, truncateBytes(data, 300))
	}
	return nil
}

// pitSearchInvalid reports whether a failed _search response indicates the
// point-in-time is gone (rather than a transport or request-shape problem).
func pitSearchInvalid(status int, body []byte) bool {
	if status != http.StatusNotFound && status != http.StatusBadRequest {
		return false
	}
	return bytes.Contains(body, []byte("search_context_missing_exception")) ||
		bytes.Contains(body, []byte("point in time")) ||
		bytes.Contains(body, []byte("point_in_time"))
}
