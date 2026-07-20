package intersectionclient

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"

	"quwoquan_service/services/search-service/internal/application"
)

type delegatedAuthorizationStub struct {
	personaID string
	header    string
}

func (s *delegatedAuthorizationStub) AuthorizationHeaderForPersona(
	_ context.Context,
	personaID string,
) (string, error) {
	s.personaID = personaID
	return s.header, nil
}

func TestClientUsesGeneratedRouteDelegatedActorAndCanonicalWireFields(t *testing.T) {
	authorization := &delegatedAuthorizationStub{header: "Bearer delegated-token"}
	server := httptest.NewServer(http.HandlerFunc(func(
		response http.ResponseWriter,
		request *http.Request,
	) {
		if request.URL.Path != "/content/intersections/object" {
			t.Errorf("path=%q", request.URL.Path)
		}
		if request.URL.Query().Get("objectId") != "post-1" ||
			request.URL.Query().Get("objectType") != "post" ||
			request.URL.Query().Get("limit") != "1" {
			t.Errorf("query=%q", request.URL.RawQuery)
		}
		if request.Header.Get("Authorization") != "Bearer delegated-token" {
			t.Errorf("authorization=%q", request.Header.Get("Authorization"))
		}
		response.Header().Set("Content-Type", "application/json")
		_, _ = response.Write([]byte(`{
			"items":[{
				"intersectionId":"ix-1",
				"dimension":"content",
				"intersectionClass":"fact",
				"primaryText":"你们都喜欢摄影",
				"intersectionPoints":[
					{"sourceRef":""},
					{"sourceRef":"sharedFollowees"},
					{"sourceRef":"coCommented"}
				]
			}]
		}`))
	}))
	defer server.Close()

	client, err := New(Config{
		BaseURL:       server.URL,
		HTTPClient:    server.Client(),
		Authorization: authorization,
	})
	if err != nil {
		t.Fatalf("new client: %v", err)
	}
	facts, err := client.ListObjectIntersections(
		context.Background(),
		application.ObjectIntersectionQuery{
			ViewerPersonaID: "persona-1",
			ObjectID:        "post-1",
			ObjectType:      "post",
			Limit:           1,
		},
	)
	if err != nil {
		t.Fatalf("list intersections: %v", err)
	}
	if authorization.personaID != "persona-1" {
		t.Fatalf("delegated persona=%q", authorization.personaID)
	}
	if len(facts) != 1 {
		t.Fatalf("facts=%#v", facts)
	}
	if facts[0].PrimaryText != "你们都喜欢摄影" ||
		facts[0].SourceRef != "sharedFollowees" ||
		facts[0].IntersectionClass != "fact" {
		t.Fatalf("fact=%#v", facts[0])
	}
	if len(facts[0].SourceRefs) != 2 ||
		facts[0].SourceRefs[1] != "coCommented" {
		t.Fatalf("source refs=%#v", facts[0].SourceRefs)
	}
}
