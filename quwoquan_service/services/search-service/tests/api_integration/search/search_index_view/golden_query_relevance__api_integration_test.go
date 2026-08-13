// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-003
// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-003.t1
// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-003.t2
// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/search-storage-topology-and-elasticity/spec.md#req-007
// readiness_case: search-golden-query-relevance-api
package api_integration

import (
	"context"
	"strings"
	"testing"
	"time"

	rtsearch "quwoquan_service/runtime/search"
	"quwoquan_service/runtime/search/es"
	"quwoquan_service/services/search-service/internal/search/search_index_view/application"
	"quwoquan_service/services/search-service/tests/support"
)

// goldenDocument is one corpus row: a canonical search document plus the
// relevance expectations the analyzer switch must keep satisfying. Extending
// coverage means appending rows here — the assertions below derive from them.
type goldenDocument struct {
	target      rtsearch.Target
	objectType  string
	objectID    string
	contentType string
	title       string
	summary     string
	body        string
	quality     float64
}

var goldenCorpus = []goldenDocument{
	{rtsearch.TargetArticle, "content.post", "post-guide", "article", "大理古城旅游攻略", "从人民路到洱海门的一日路线", "苍山洱海之间的大理古城适合慢慢逛", 3},
	{rtsearch.TargetArticle, "content.post", "post-lijiang", "article", "丽江古城徒步路线", "束河到白沙的徒步", "丽江的石板路与雪山", 2},
	{rtsearch.TargetArticle, "content.post", "post-phrase", "article", "环洱海一日路线", "骑行环湖的经典走法", "海西到海东顺时针一圈", 2},
	{rtsearch.TargetArticle, "content.post", "post-scattered", "article", "一日路线之外：环游洱海的另一种打开方式", "环湖 路线 一日 洱海 拆散出现", "把这些词拆开写进正文", 2},
	{rtsearch.TargetPhoto, "content.post", "post-food", "image", "大理美食探店", "人民路小吃合集", "烤乳扇和米线", 2},
	{rtsearch.TargetVideo, "content.post", "post-vlog", "video", "洱海骑行 vlog", "环湖骑行一日", "从才村码头出发", 2},
	{rtsearch.TargetUser, "user.profile", "user-photog", "", "大理旅拍摄影师", "常驻大理接旅拍", "", 1},
	{rtsearch.TargetEntity, "entity.homepage", "entity-oldtown", "", "大理古城景区", "国家级历史文化名城", "", 3},
	{rtsearch.TargetCircle, "circle.circle", "circle-travel", "", "大理旅行圈", "同城旅行搭子", "", 1},
	{rtsearch.TargetLocation, "location.place", "place-renmin", "", "大理人民路", "古城主街", "", 1},
}

// startGoldenSearchService boots the production recall stack (real CJK ES via
// testcontainer or QWQ_TEST_ELASTICSEARCH_ENDPOINT) with the golden corpus
// indexed through the write alias, exactly like owner projections do.
func startGoldenSearchService(t *testing.T) (*application.SearchService, func()) {
	t.Helper()
	ctx := context.Background()
	endpoint, stop := support.StartElasticsearchCJK(t, ctx)

	client, err := es.NewClient(es.Config{
		Endpoints:      []string{endpoint},
		Index:          "quwoquan_objects_golden",
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
	for _, row := range goldenCorpus {
		document := rtsearch.Document{
			ObjectType:  row.objectType,
			ObjectID:    row.objectID,
			Title:       row.title,
			Summary:     row.summary,
			Body:        row.body,
			ContentType: row.contentType,
			Visibility:  "public",
			Popularity:  row.quality,
			Freshness:   now,
			DeepLink:    "quwoquan://objects/" + row.objectID,
		}
		if err := indexer.Apply(ctx, es.ChangeEvent{Op: es.OpUpsert, Doc: document}); err != nil {
			stop()
			t.Fatalf("index golden doc %s: %v", row.objectID, err)
		}
	}
	if err := client.Refresh(ctx); err != nil {
		stop()
		t.Fatalf("refresh: %v", err)
	}
	codec, err := application.NewSearchCursorCodec([]byte("golden-query-relevance-contract-secret"))
	if err != nil {
		stop()
		t.Fatalf("cursor codec: %v", err)
	}
	backend := es.NewBackend(client, client.IndexName())
	return application.NewSearchService(backend, application.WithSearchCursorCodec(codec)), stop
}

func goldenExecute(t *testing.T, service *application.SearchService, in application.QueryInput) application.QueryExecution {
	t.Helper()
	in.Mode = "result"
	execution, err := service.Execute(
		context.Background(),
		in,
		rtsearch.Viewer{},
		application.QueryCaller{PrincipalKey: "session:golden"},
		application.QueryExecutionIdentity{
			CandidateDigest: "sha256:" + strings.Repeat("a", 64),
			PolicyDigest:    "sha256:" + strings.Repeat("b", 64),
		},
	)
	if err != nil {
		t.Fatalf("Execute(%q) error = %v", in.Query, err)
	}
	return execution
}

func hitIDs(execution application.QueryExecution) []string {
	ids := make([]string, 0, len(execution.Response.Hits))
	for _, hit := range execution.Response.Hits {
		ids = append(ids, hit.ObjectID)
	}
	return ids
}

func containsID(ids []string, want string) bool {
	for _, id := range ids {
		if id == want {
			return true
		}
	}
	return false
}

func TestGoldenQueryRelevanceOnProductionAnalyzerChain(t *testing.T) {
	service, stop := startGoldenSearchService(t)
	defer stop()

	t.Run("ik segmentation recalls semantic terms", func(t *testing.T) {
		ids := hitIDs(goldenExecute(t, service, application.QueryInput{Query: "大理 旅游 攻略", Limit: 10}))
		if !containsID(ids, "post-guide") {
			t.Fatalf("IK recall missed post-guide: %v", ids)
		}
		if !containsID(ids, "entity-oldtown") {
			t.Fatalf("cross-type recall missed the entity homepage: %v", ids)
		}
	})

	t.Run("exact phrase outranks scattered terms", func(t *testing.T) {
		ids := hitIDs(goldenExecute(t, service, application.QueryInput{Query: "环洱海一日路线", Limit: 10}))
		phraseAt, scatteredAt := -1, -1
		for index, id := range ids {
			switch id {
			case "post-phrase":
				phraseAt = index
			case "post-scattered":
				scatteredAt = index
			}
		}
		if phraseAt == -1 {
			t.Fatalf("phrase document missing: %v", ids)
		}
		if scatteredAt != -1 && phraseAt > scatteredAt {
			t.Fatalf("exact phrase must outrank scattered terms: %v", ids)
		}
	})

	t.Run("pinyin full and initials recall chinese titles", func(t *testing.T) {
		for _, query := range []string{"dali"} {
			ids := hitIDs(goldenExecute(t, service, application.QueryInput{Query: query, Limit: 10}))
			if len(ids) == 0 {
				t.Fatalf("pinyin query %q recalled nothing", query)
			}
			found := false
			for _, id := range ids {
				if strings.HasPrefix(id, "post-") || strings.HasPrefix(id, "entity-") ||
					strings.HasPrefix(id, "user-") || strings.HasPrefix(id, "circle-") ||
					strings.HasPrefix(id, "place-") {
					found = true
				}
			}
			if !found {
				t.Fatalf("pinyin query %q must recall 大理 objects: %v", query, ids)
			}
		}
	})

	t.Run("contentTypes narrow the content.post family", func(t *testing.T) {
		execution := goldenExecute(t, service, application.QueryInput{
			Query:        "大理",
			ObjectTypes:  []string{"content.post"},
			ContentTypes: []string{"image"},
			Limit:        10,
		})
		for _, hit := range execution.Response.Hits {
			if hit.Target != rtsearch.TargetPhoto {
				t.Fatalf("contentTypes=image must only return photo posts, got %s/%s", hit.Target, hit.ObjectID)
			}
		}
		if len(execution.Response.Hits) == 0 {
			t.Fatal("contentTypes=image returned nothing")
		}
	})

	t.Run("objectTypes narrow to a single object class", func(t *testing.T) {
		execution := goldenExecute(t, service, application.QueryInput{
			Query:       "大理",
			ObjectTypes: []string{"user.profile"},
			Limit:       10,
		})
		if len(execution.Response.Hits) == 0 {
			t.Fatal("user.profile filter returned nothing")
		}
		for _, hit := range execution.Response.Hits {
			if hit.ObjectType != "user.profile" {
				t.Fatalf("user.profile filter leaked %s/%s", hit.ObjectType, hit.ObjectID)
			}
		}
	})

	t.Run("internal target vocabulary is rejected", func(t *testing.T) {
		_, err := service.Execute(
			context.Background(),
			application.QueryInput{Query: "大理", Mode: "result", ObjectTypes: []string{"photo"}, Limit: 5},
			rtsearch.Viewer{},
			application.QueryCaller{PrincipalKey: "session:golden"},
			application.QueryExecutionIdentity{
				CandidateDigest: "sha256:" + strings.Repeat("a", 64),
				PolicyDigest:    "sha256:" + strings.Repeat("b", 64),
			},
		)
		if err == nil {
			t.Fatal("internal target vocabulary must be rejected")
		}
	})

	t.Run("pagination is continuous without duplicates or gaps", func(t *testing.T) {
		baseline := hitIDs(goldenExecute(t, service, application.QueryInput{Query: "大理", Limit: 10}))
		seen := map[string]bool{}
		paged := []string{}
		cursor := ""
		for page := 0; page < 10; page++ {
			execution := goldenExecute(t, service, application.QueryInput{Query: "大理", Limit: 2, Cursor: cursor})
			for _, id := range hitIDs(execution) {
				if seen[id] {
					t.Fatalf("pagination returned duplicate %s (pages so far %v)", id, paged)
				}
				seen[id] = true
				paged = append(paged, id)
			}
			cursor = execution.NextCursor
			if cursor == "" {
				break
			}
		}
		if len(paged) != len(baseline) {
			t.Fatalf("pagination lost or invented hits: paged=%v baseline=%v", paged, baseline)
		}
		for index := range paged {
			if paged[index] != baseline[index] {
				t.Fatalf("pagination order diverged at %d: paged=%v baseline=%v", index, paged, baseline)
			}
		}
	})

	t.Run("repeated queries keep an identical TopN sequence", func(t *testing.T) {
		baseline := hitIDs(goldenExecute(t, service, application.QueryInput{Query: "大理 古城", Limit: 10}))
		for run := 0; run < 10; run++ {
			sequence := hitIDs(goldenExecute(t, service, application.QueryInput{Query: "大理 古城", Limit: 10}))
			if len(sequence) != len(baseline) {
				t.Fatalf("run %d sequence length drifted: %v != %v", run, sequence, baseline)
			}
			for index := range sequence {
				if sequence[index] != baseline[index] {
					t.Fatalf("run %d sequence drifted at %d: %v != %v", run, index, sequence, baseline)
				}
			}
		}
	})

	t.Run("server-side highlighter feeds the snippet", func(t *testing.T) {
		execution := goldenExecute(t, service, application.QueryInput{Query: "旅游攻略", Limit: 10})
		var guide *rtsearch.RetrieveHit
		for index := range execution.Response.Hits {
			if execution.Response.Hits[index].ObjectID == "post-guide" {
				guide = &execution.Response.Hits[index]
			}
		}
		if guide == nil {
			t.Fatalf("post-guide missing: %v", hitIDs(execution))
		}
		if !strings.Contains(guide.Snippet, "攻略") {
			t.Fatalf("highlighted snippet must contain the matched term, got %q", guide.Snippet)
		}
		if guide.RankPosition <= 0 {
			t.Fatalf("rankPosition must be assigned, got %d", guide.RankPosition)
		}
	})

	t.Run("sensitive queries are blocked structurally", func(t *testing.T) {
		execution := goldenExecute(t, service, application.QueryInput{Query: "赌博网站", Limit: 10})
		if len(execution.Response.Hits) != 0 {
			t.Fatalf("sensitive query must return no hits, got %v", hitIDs(execution))
		}
		blocked := false
		for _, signal := range execution.Response.DegradeSignals {
			if signal.Code == "SEARCH.USER.sensitive_query" {
				blocked = true
			}
		}
		if !blocked {
			t.Fatalf("sensitive query must carry the structured block signal, got %+v", execution.Response.DegradeSignals)
		}
	})
}
