// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/search-storage-topology-and-elasticity/spec.md#req-007
// spec_ref: specs/feature-tree/global-search-experience/search-provider-routing-and-storage-topology/canonical-search-contract/spec.md#gwt-003.t5
package local_contract

import (
	"context"
	"strings"
	"testing"

	rtsearch "quwoquan_service/runtime/search"
	application "quwoquan_service/services/search-service/internal/search/search_index_view/application"
)

// TestSearchRepeatedExecutionKeepsTopNSequenceIdentical pins the repeatability
// contract: the same input through the same public entrypoint must yield the
// exact (objectType, objectId) TopN sequence on every execution — including
// equal-score / equal-title ties, which are the classic source of replica- and
// refresh-dependent jitter. The deterministic total order lives in
// rtsearch.LessHitStable and the ES sort mirrors it key-by-key.
func TestSearchRepeatedExecutionKeepsTopNSequenceIdentical(t *testing.T) {
	documents := []rtsearch.Document{
		{ObjectType: rtsearch.ObjectTypeContentPost, ObjectID: "post-c", Title: "西湖游记", Visibility: "public"},
		{ObjectType: rtsearch.ObjectTypeContentPost, ObjectID: "post-a", Title: "西湖游记", Visibility: "public"},
		{ObjectType: rtsearch.ObjectTypeContentPost, ObjectID: "post-b", Title: "西湖游记", Visibility: "public"},
		{ObjectType: rtsearch.ObjectTypeEntityHomepage, ObjectID: "entity-1", Title: "西湖", Visibility: "public"},
		{ObjectType: rtsearch.ObjectTypeUserProfile, ObjectID: "user-9", Title: "西湖摄影师", Visibility: "public"},
	}
	codec, err := application.NewSearchCursorCodec([]byte("search-repeatability-contract-secret"))
	if err != nil {
		t.Fatalf("NewSearchCursorCodec() error = %v", err)
	}
	service := application.NewSearchService(
		rtsearch.NewSliceBackend(documents),
		application.WithSearchCursorCodec(codec),
	)
	input := application.QueryInput{
		Query:       "西湖",
		Mode:        "result",
		ObjectTypes: []string{"content.post", "entity.homepage", "user.profile"},
		Limit:       5,
	}
	caller := application.QueryCaller{PrincipalKey: "session:repeatability"}
	identity := application.QueryExecutionIdentity{
		CandidateDigest: "sha256:" + strings.Repeat("a", 64),
		PolicyDigest:    "sha256:" + strings.Repeat("b", 64),
	}

	var baseline []string
	for run := 0; run < 20; run++ {
		execution, err := service.Execute(context.Background(), input, rtsearch.Viewer{}, caller, identity)
		if err != nil {
			t.Fatalf("run %d Execute() error = %v", run, err)
		}
		sequence := make([]string, 0, len(execution.Response.Hits))
		for _, hit := range execution.Response.Hits {
			sequence = append(sequence, hit.ObjectType+"/"+hit.ObjectID)
		}
		if len(sequence) == 0 {
			t.Fatalf("run %d returned no hits", run)
		}
		if baseline == nil {
			baseline = sequence
			continue
		}
		if len(sequence) != len(baseline) {
			t.Fatalf("run %d TopN length drifted: %v != %v", run, sequence, baseline)
		}
		for index := range sequence {
			if sequence[index] != baseline[index] {
				t.Fatalf("run %d TopN sequence drifted at %d: %v != %v", run, index, sequence, baseline)
			}
		}
	}

	// 同分同题的三个 post 之间必须由 ObjectID 升序钉死（LessHitStable 的
	// 最后一级 tie-break），否则等分命中会在副本/刷新间跳动。
	postOrder := make([]string, 0, 3)
	for _, entry := range baseline {
		if strings.HasPrefix(entry, rtsearch.ObjectTypeContentPost+"/") {
			postOrder = append(postOrder, strings.TrimPrefix(entry, rtsearch.ObjectTypeContentPost+"/"))
		}
	}
	if len(postOrder) != 3 || postOrder[0] != "post-a" || postOrder[1] != "post-b" || postOrder[2] != "post-c" {
		t.Fatalf("equal-score tie-break must order by ObjectID asc, got %v", postOrder)
	}
}
