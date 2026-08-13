package es

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"sort"
	"strconv"
	"strings"
)

// writeAliasSuffix derives the write alias from the read alias:
// quwoquan_objects -> quwoquan_objects-write. Both aliases point at one
// versioned physical index (quwoquan_objects-vN) in steady state.
const writeAliasSuffix = "-write"

// physicalIndexFor resolves the single physical index behind an alias, or ""
// when the alias does not exist. Multiple physical indexes behind the read
// alias would double every hit, so that state fails closed.
func (c *Client) physicalIndexFor(ctx context.Context, alias string) (string, error) {
	status, data, err := c.send(ctx, http.MethodGet, "/_alias/"+alias, nil, "application/json")
	if err != nil {
		return "", err
	}
	if status == http.StatusNotFound {
		return "", nil
	}
	if status < 200 || status >= 300 {
		if retryableDependencyStatus(status) {
			return "", fmt.Errorf("%w: es get alias status %d", ErrDependencyUnavailable, status)
		}
		return "", fmt.Errorf("es: get alias status %d: %s", status, truncateBytes(data, 300))
	}
	var parsed map[string]any
	if err := json.Unmarshal(data, &parsed); err != nil {
		return "", fmt.Errorf("es: decode alias response: %w", err)
	}
	indexes := make([]string, 0, len(parsed))
	for name := range parsed {
		indexes = append(indexes, name)
	}
	if len(indexes) != 1 {
		sort.Strings(indexes)
		return "", fmt.Errorf(
			"es: alias %q must resolve to exactly one physical index, got %v",
			alias, indexes,
		)
	}
	return indexes[0], nil
}

// nextPhysicalIndex derives {alias}-v{N+1} from the current physical index.
func nextPhysicalIndex(alias, current string) (string, error) {
	prefix := alias + "-v"
	if !strings.HasPrefix(current, prefix) {
		return "", fmt.Errorf("es: physical index %q is not versioned under alias %q", current, alias)
	}
	version, err := strconv.Atoi(strings.TrimPrefix(current, prefix))
	if err != nil || version < 1 {
		return "", fmt.Errorf("es: physical index %q carries an invalid version", current)
	}
	return prefix + strconv.Itoa(version+1), nil
}

// BeginRebuild creates the next versioned physical index with the current
// schema and atomically moves the WRITE alias onto it. From this moment every
// incremental projection lands in the new index, so the follow-up owner
// backfills cannot lose the rebuild window. Reads keep serving the old index
// until PromoteRebuild.
func (c *Client) BeginRebuild(ctx context.Context) (string, error) {
	current, err := c.physicalIndexFor(ctx, c.index)
	if err != nil {
		return "", err
	}
	if current == "" {
		return "", fmt.Errorf("es: read alias %q does not exist; run EnsureIndex first", c.index)
	}
	next, err := nextPhysicalIndex(c.index, current)
	if err != nil {
		return "", err
	}
	createStatus, createData, err := c.send(ctx, http.MethodPut, "/"+next, BuildCreateIndexBody(c.cfg.Schema), "application/json")
	if err != nil {
		return "", err
	}
	if (createStatus < 200 || createStatus >= 300) &&
		!(createStatus == http.StatusBadRequest && bytes.Contains(createData, []byte("resource_already_exists_exception"))) {
		return "", fmt.Errorf("es: create rebuild index status %d: %s", createStatus, truncateBytes(createData, 300))
	}
	if err := c.moveAlias(ctx, c.WriteIndexName(), current, next, true); err != nil {
		return "", err
	}
	return next, nil
}

// PromoteRebuild atomically moves the READ alias onto the rebuilt index. The
// caller is expected to have completed and verified the owner backfills
// (doc-count / sampling comparison) before promoting.
func (c *Client) PromoteRebuild(ctx context.Context, next string) error {
	current, err := c.physicalIndexFor(ctx, c.index)
	if err != nil {
		return err
	}
	if current == "" {
		return fmt.Errorf("es: read alias %q does not exist", c.index)
	}
	if current == next {
		return nil
	}
	return c.moveAlias(ctx, c.index, current, next, false)
}

// CleanupRebuild deletes a retired physical index once neither alias
// references it (fails closed otherwise).
func (c *Client) CleanupRebuild(ctx context.Context, retired string) error {
	for _, alias := range []string{c.index, c.WriteIndexName()} {
		physical, err := c.physicalIndexFor(ctx, alias)
		if err != nil {
			return err
		}
		if physical == retired {
			return fmt.Errorf("es: index %q is still referenced by alias %q", retired, alias)
		}
	}
	status, data, err := c.send(ctx, http.MethodDelete, "/"+retired, nil, "application/json")
	if err != nil {
		return err
	}
	if status == http.StatusNotFound {
		return nil
	}
	if status < 200 || status >= 300 {
		return fmt.Errorf("es: delete retired index status %d: %s", status, truncateBytes(data, 300))
	}
	return nil
}

// DocCount returns the document count of one physical index (rebuild
// verification input; never used on the query path).
func (c *Client) DocCount(ctx context.Context, index string) (int64, error) {
	status, data, err := c.send(ctx, http.MethodGet, "/"+index+"/_count", nil, "application/json")
	if err != nil {
		return 0, err
	}
	if status < 200 || status >= 300 {
		return 0, fmt.Errorf("es: count status %d: %s", status, truncateBytes(data, 300))
	}
	var parsed struct {
		Count int64 `json:"count"`
	}
	if err := json.Unmarshal(data, &parsed); err != nil {
		return 0, fmt.Errorf("es: decode count response: %w", err)
	}
	return parsed.Count, nil
}

// moveAlias atomically re-points one alias from `from` to `to` in a single
// _aliases action set (no intermediate state where the alias is missing or
// doubled).
func (c *Client) moveAlias(ctx context.Context, alias, from, to string, isWrite bool) error {
	add := map[string]any{"index": to, "alias": alias}
	if isWrite {
		add["is_write_index"] = true
	}
	actions := map[string]any{
		"actions": []any{
			map[string]any{"remove": map[string]any{"index": from, "alias": alias}},
			map[string]any{"add": add},
		},
	}
	status, data, err := c.send(ctx, http.MethodPost, "/_aliases", actions, "application/json")
	if err != nil {
		return err
	}
	if status < 200 || status >= 300 {
		return fmt.Errorf("es: move alias %q status %d: %s", alias, status, truncateBytes(data, 300))
	}
	return nil
}
