// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/autonomous-web-exploration/spec.md#gwt-003
package assistant_run_test

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	rtsearch "quwoquan_service/runtime/search"
	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tool"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/searchclient"
)

// A search surface that ignores the objectTypes filter is the whole reason this
// enforcement cannot live in the request. This stub answers every query with one
// hit and one citation per object type, including the ones 小趣 must never see.
func newIgnoringSearchStub(t *testing.T) *httptest.Server {
	t.Helper()
	objectTypes := []string{
		rtsearch.ObjectTypeContentPost,
		rtsearch.ObjectTypeChatMessage,
		rtsearch.ObjectTypeChatConversation,
		rtsearch.ObjectTypeChatContact,
		rtsearch.ObjectTypeUserProfile,
		rtsearch.ObjectTypeCircle,
		"content.private_draft",
	}
	return httptest.NewServer(http.HandlerFunc(func(
		writer http.ResponseWriter,
		request *http.Request,
	) {
		hits := make([]rtsearch.RetrieveHit, 0, len(objectTypes))
		citations := make([]rtsearch.Citation, 0, len(objectTypes))
		for _, objectType := range objectTypes {
			hits = append(hits, rtsearch.RetrieveHit{
				ObjectType: objectType,
				ObjectID:   objectType + "-1",
				Title:      objectType,
			})
			citations = append(citations, rtsearch.Citation{
				CitationID: objectType + "-citation",
				ObjectType: objectType,
				ObjectID:   objectType + "-1",
				Title:      objectType,
			})
		}
		writer.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(writer).Encode(rtsearch.RetrieveResponse{
			Hits:      hits,
			Citations: citations,
			Provenance: rtsearch.Provenance{
				Provider:    "search-service",
				GeneratedAt: time.Unix(1_700_000_000, 0).UTC(),
			},
		})
	}))
}

func TestAppSearchDropsHitsForObjectTypesTheContractClosesToTheAssistant(t *testing.T) {
	server := newIgnoringSearchStub(t)
	defer server.Close()

	client, err := searchclient.New(server.URL, server.Client())
	if err != nil {
		t.Fatalf("new search client: %v", err)
	}
	result, err := client.Handler()(t.Context(), toolpkg.Request{
		Input: map[string]any{"query": "西湖"},
	})
	if err != nil {
		t.Fatalf("execute app_search adapter: %v", err)
	}

	readable := map[string]bool{}
	for _, objectType := range searchclient.AssistantReadableObjectTypes() {
		readable[objectType] = true
	}
	results, ok := result.Output["results"].([]map[string]any)
	if !ok {
		t.Fatalf("results=%#v", result.Output["results"])
	}
	if len(results) == 0 {
		t.Fatal("every hit was dropped; the filter must keep the open object types")
	}
	for _, hit := range results {
		objectID, _ := hit["objectId"].(string)
		// objectId is `<objectType>-1` in the stub, so a leaked type is nameable.
		for closed := range map[string]bool{
			rtsearch.ObjectTypeChatMessage:      true,
			rtsearch.ObjectTypeChatConversation: true,
			rtsearch.ObjectTypeChatContact:      true,
			rtsearch.ObjectTypeUserProfile:      true,
			"content.private_draft":             true,
		} {
			if objectID == closed+"-1" {
				t.Fatalf(
					"app_search returned a hit for %q, which no object contract opens "+
						"to the assistant",
					closed,
				)
			}
		}
	}

	citations, ok := result.Output["citations"].([]map[string]any)
	if !ok {
		t.Fatalf("citations=%#v", result.Output["citations"])
	}
	for _, citation := range citations {
		objectType, _ := citation["objectType"].(string)
		if !readable[objectType] {
			t.Fatalf(
				"app_search returned a citation for %q, which is not citable by the "+
					"assistant",
				objectType,
			)
		}
	}
	// user.profile is registered searchable and reachable in the index, but its
	// owner opens only owner-scoped reads. This client queries the shared index
	// without an end-user identity, so it must not surface those rows at all.
	if readable[rtsearch.ObjectTypeUserProfile] {
		t.Fatal("user.profile must not be readable through the unscoped index query")
	}
}

func TestRetrieveRefusesToWidenToObjectTypesTheAssistantMayNotRead(t *testing.T) {
	server := newIgnoringSearchStub(t)
	defer server.Close()

	client, err := searchclient.New(server.URL, server.Client())
	if err != nil {
		t.Fatalf("new search client: %v", err)
	}
	// Asking only for closed types must not fall through to an unfiltered query:
	// an empty objectTypes list means "every type" on the wire.
	response, err := client.Retrieve(
		t.Context(),
		"西湖",
		[]string{rtsearch.ObjectTypeChatMessage, rtsearch.ObjectTypeUserProfile},
		10,
	)
	if err != nil {
		t.Fatalf("retrieve: %v", err)
	}
	if len(response.Hits) != 0 || len(response.Citations) != 0 {
		t.Fatalf(
			"caller-requested closed types returned hits=%d citations=%d",
			len(response.Hits),
			len(response.Citations),
		)
	}
}
