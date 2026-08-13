// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/search-storage-topology-and-elasticity/spec.md#req-007
// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/search-storage-topology-and-elasticity/spec.md#gwt-003
// readiness_case: search-pit-pagination-api
package api_integration

import (
	"context"
	"errors"
	"strconv"
	"strings"
	"testing"
	"time"

	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
	"quwoquan_service/services/search-service/internal/search/search_index_view/application"
	"quwoquan_service/services/search-service/tests/support"
)

// spySnapshots forwards to the real es.Client PIT capability while recording
// opened ids, so the expiry scenario can revoke a live snapshot exactly the
// way keep_alive lapse / node restart would.
type spySnapshots struct {
	inner  application.PaginationSnapshots
	opened []string
}

func (s *spySnapshots) OpenPIT(ctx context.Context) (string, error) {
	id, err := s.inner.OpenPIT(ctx)
	if err == nil {
		s.opened = append(s.opened, id)
	}
	return id, err
}

func (s *spySnapshots) ClosePIT(ctx context.Context, id string) error {
	return s.inner.ClosePIT(ctx, id)
}

func startPITSearchService(t *testing.T) (*application.SearchService, *es.Client, *spySnapshots, func()) {
	t.Helper()
	ctx := context.Background()
	endpoint, stop := support.StartElasticsearchCJK(t, ctx)
	client, err := es.NewClient(es.Config{
		Endpoints:      []string{endpoint},
		Index:          "quwoquan_objects_pit",
		RequestTimeout: 30 * time.Second,
	})
	if err != nil {
		stop()
		t.Fatalf("es client: %v", err)
	}
	if err := client.EnsureIndex(ctx); err != nil {
		stop()
		t.Fatalf("EnsureIndex: %v", err)
	}
	indexer := es.NewIndexer(client, client.WriteIndexName())
	now := time.Date(2026, 8, 1, 0, 0, 0, 0, time.UTC)
	for index := 0; index < 9; index++ {
		if err := indexer.Apply(ctx, es.ChangeEvent{Op: es.OpUpsert, Doc: rtsearch.Document{
			ObjectType:  "content.post",
			ObjectID:    "pit-post-" + strconv.Itoa(index),
			Title:       "大理翻页快照第" + strconv.Itoa(index) + "篇",
			Summary:     "翻页快照语料",
			ContentType: "article",
			Visibility:  "public",
			Popularity:  float64(index % 3),
			Freshness:   now,
			DeepLink:    "quwoquan://content/posts/pit-post-" + strconv.Itoa(index),
		}}); err != nil {
			stop()
			t.Fatalf("index pit doc %d: %v", index, err)
		}
	}
	if err := client.Refresh(ctx); err != nil {
		stop()
		t.Fatalf("refresh: %v", err)
	}
	codec, err := application.NewSearchCursorCodec([]byte("pit-pagination-snapshot-contract-secret"))
	if err != nil {
		stop()
		t.Fatalf("cursor codec: %v", err)
	}
	spy := &spySnapshots{inner: client}
	service := application.NewSearchService(
		es.NewBackend(client, client.IndexName()),
		application.WithSearchCursorCodec(codec),
		application.WithPaginationSnapshots(spy),
	)
	return service, client, spy, stop
}

func pitExecute(t *testing.T, service *application.SearchService, cursor string) application.QueryExecution {
	t.Helper()
	execution, err := service.Execute(
		context.Background(),
		application.QueryInput{Query: "大理", Mode: "result", Limit: 2, Cursor: cursor},
		rtsearch.Viewer{},
		application.QueryCaller{PrincipalKey: "session:pit"},
		application.QueryExecutionIdentity{
			CandidateDigest: "sha256:" + strings.Repeat("a", 64),
			PolicyDigest:    "sha256:" + strings.Repeat("b", 64),
		},
	)
	if err != nil {
		t.Fatalf("Execute(hasCursor=%t) error = %v", cursor != "", err)
	}
	return execution
}

func TestPaginationSnapshotSurvivesConcurrentIndexWrites(t *testing.T) {
	service, client, spy, stop := startPITSearchService(t)
	defer stop()
	ctx := context.Background()

	// Snapshot baseline: the full sequence before any pagination starts.
	baseline := hitIDs(pitExecute(t, service, ""))
	if len(baseline) != 2 {
		t.Fatalf("first page must hold the page limit, got %v", baseline)
	}

	first := pitExecute(t, service, "")
	if first.NextCursor == "" {
		t.Fatal("first page must issue a continuation cursor")
	}
	if len(spy.opened) != 0 {
		t.Fatal("first pages must never open a pagination snapshot (lazy PIT)")
	}

	second := pitExecute(t, service, first.NextCursor)
	if len(spy.opened) != 1 {
		t.Fatalf("the first follow-up page must open exactly one snapshot, got %d", len(spy.opened))
	}

	// Mid-pagination index churn: a new matching document arrives and an
	// unvisited one is deleted. The open snapshot must keep serving the state
	// the pagination started on.
	indexer := es.NewIndexer(client, client.WriteIndexName())
	if err := indexer.Apply(ctx, es.ChangeEvent{Op: es.OpUpsert, Doc: rtsearch.Document{
		ObjectType: "content.post", ObjectID: "pit-post-late",
		Title: "大理翻页快照插队新文档", Summary: "翻页开始后写入",
		ContentType: "article", Visibility: "public", Popularity: 99,
		Freshness: time.Now().UTC(), DeepLink: "quwoquan://content/posts/pit-post-late",
	}}); err != nil {
		t.Fatalf("late upsert: %v", err)
	}
	if err := indexer.Apply(ctx, es.ChangeEvent{Op: es.OpDelete, Doc: rtsearch.Document{
		ObjectType: "content.post", ObjectID: "pit-post-8",
	}}); err != nil {
		t.Fatalf("late delete: %v", err)
	}
	if err := client.Refresh(ctx); err != nil {
		t.Fatalf("refresh: %v", err)
	}

	seen := map[string]bool{}
	sequence := append([]string{}, hitIDs(second)...)
	for _, id := range hitIDs(first) {
		seen[id] = true
	}
	for _, id := range hitIDs(second) {
		if seen[id] {
			t.Fatalf("second page duplicated %s", id)
		}
		seen[id] = true
	}
	cursor := second.NextCursor
	for page := 0; page < 10 && cursor != ""; page++ {
		execution := pitExecute(t, service, cursor)
		for _, id := range hitIDs(execution) {
			if id == "pit-post-late" {
				t.Fatal("documents written after the pagination started must not leak into the snapshot")
			}
			if seen[id] {
				t.Fatalf("pagination duplicated %s under concurrent writes", id)
			}
			seen[id] = true
			sequence = append(sequence, id)
		}
		cursor = execution.NextCursor
	}
	if !seen["pit-post-8"] {
		t.Fatalf("the snapshot must keep serving documents deleted mid-pagination, sequence=%v", sequence)
	}
	if len(seen) != 9 {
		t.Fatalf("pagination must cover the exact snapshot corpus (9 docs), got %d: %v", len(seen), sequence)
	}
}

func TestExpiredPaginationSnapshotFailsTheCursorClosed(t *testing.T) {
	service, client, spy, stop := startPITSearchService(t)
	defer stop()

	first := pitExecute(t, service, "")
	second := pitExecute(t, service, first.NextCursor)
	if second.NextCursor == "" || len(spy.opened) != 1 {
		t.Fatalf("expected an open snapshot and a continuation, cursor=%v opened=%d", second.NextCursor != "", len(spy.opened))
	}

	// Revoke the live snapshot exactly like keep_alive lapse / node restart.
	if err := client.ClosePIT(context.Background(), spy.opened[0]); err != nil {
		t.Fatalf("revoke snapshot: %v", err)
	}

	_, err := service.Execute(
		context.Background(),
		application.QueryInput{Query: "大理", Mode: "result", Limit: 2, Cursor: second.NextCursor},
		rtsearch.Viewer{},
		application.QueryCaller{PrincipalKey: "session:pit"},
		application.QueryExecutionIdentity{
			CandidateDigest: "sha256:" + strings.Repeat("a", 64),
			PolicyDigest:    "sha256:" + strings.Repeat("b", 64),
		},
	)
	if !errors.Is(err, application.ErrSearchCursor) {
		t.Fatalf("an expired snapshot must fail the cursor closed, got %v", err)
	}
}
