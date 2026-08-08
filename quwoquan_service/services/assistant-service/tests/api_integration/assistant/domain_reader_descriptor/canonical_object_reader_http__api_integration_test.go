// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/domain-reader-connector-grant/spec.md#gwt-001
package api_integration

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/domainreader"
	contextinfra "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/skillcontext"
	readerresource "quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/infrastructure/resource"
)

func TestCanonicalObjectReadersUseGeneratedPublicQueriesAndBoundedProjection(t *testing.T) {
	observedAt := time.Date(2026, 8, 4, 10, 30, 0, 0, time.UTC)
	timestamp := observedAt.Add(-time.Minute).Format(time.RFC3339Nano)
	server := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if request.Method != http.MethodGet || request.Header.Get("Accept") != "application/json" {
			t.Errorf("request=%s %s accept=%q", request.Method, request.URL.Path, request.Header.Get("Accept"))
		}
		if request.Header.Get("Authorization") != "" || request.Header.Get("Cookie") != "" {
			t.Errorf("public Reader inherited credentials: headers=%v", request.Header)
		}
		writer.Header().Set("Content-Type", "application/json")
		switch {
		case strings.HasPrefix(request.URL.Path, "/circles/"):
			circleID := strings.TrimPrefix(request.URL.Path, "/circles/")
			visibility := "public"
			if circleID == "private" {
				visibility = "private"
			}
			_ = json.NewEncoder(writer).Encode(map[string]any{"data": map[string]any{
				"id": circleID, "name": "西湖同行圈", "description": "周末共同出行",
				"status": "active", "visibility": visibility, "joinPolicy": "open",
				"kind": "interest", "displaySubjectType": "circle", "memberCount": 12,
				"createdAt": timestamp, "updatedAt": timestamp, "ownerId": "must-not-project",
			}})
		case strings.HasPrefix(request.URL.Path, "/content/posts/"):
			postID := strings.TrimPrefix(request.URL.Path, "/content/posts/")
			policy := "inherit"
			if postID == "excluded" {
				policy = "exclude"
			}
			secret := "must-not-project"
			if postID == "oversized" {
				secret = strings.Repeat("x", 513<<10)
			}
			_ = json.NewEncoder(writer).Encode(map[string]any{
				"postId": postID, "contentType": "article", "assistantUsePolicy": policy,
				"title": "西湖一日餐饮路线", "summary": "吃玩路线", "status": "published",
				"visibility": "public", "createdAt": timestamp, "updatedAt": timestamp,
				"likeCount": 1, "commentCount": 2, "shareCount": 3, "viewCount": 4,
				"internalSecret": secret,
			})
		case strings.HasPrefix(request.URL.Path, "/homepages/"):
			homepageID := strings.TrimPrefix(request.URL.Path, "/homepages/")
			status := "published"
			if homepageID == "candidate" {
				status = "candidate"
			}
			_ = json.NewEncoder(writer).Encode(map[string]any{
				"homepageId": homepageID, "title": "西湖", "homepageType": "place",
				"status": status, "claimStatus": "unclaimed", "verified": true,
				"ratingCount": 8, "createdAt": timestamp, "updatedAt": timestamp,
				"sourceUrls":  []string{"https://example.com/west-lake"},
				"ownerUserId": "must-not-project",
			})
		default:
			http.NotFound(writer, request)
		}
	}))
	defer server.Close()

	readers, err := domainreader.NewCanonicalReaders(domainreader.CanonicalReadersConfig{
		Descriptors: canonicalObjectDescriptorCatalog(t),
		Definitions: domainreader.ProductionReaderDefinitions(),
		ServiceTransports: map[string]domainreader.ReaderTransport{
			"circle-service":  {BaseURL: server.URL, HTTPClient: server.Client()},
			"content-service": {BaseURL: server.URL, HTTPClient: server.Client()},
			"entity-service":  {BaseURL: server.URL, HTTPClient: server.Client()},
		},
		Now: func() time.Time { return observedAt },
	})
	if err != nil {
		t.Fatal(err)
	}
	circleReader, ok := readers.Reader("circle.current_context")
	if !ok {
		t.Fatal("circle Reader is unavailable")
	}
	contentReader, ok := readers.Reader("content.current_context")
	if !ok {
		t.Fatal("content Reader is unavailable")
	}
	entityReader, ok := readers.Reader("entity.current_context")
	if !ok {
		t.Fatal("entity Reader is unavailable")
	}
	tests := []struct {
		name           string
		reader         domainreader.ObjectContextReader
		target         domainreader.ObjectTarget
		operationRef   string
		identityField  string
		forbiddenField string
	}{
		{
			name: "circle", reader: circleReader,
			target:       domainreader.ObjectTarget{ObjectTypeRef: "circle.Circle", ObjectID: "circle-1"},
			operationRef: "circle.circle.GetCircle", identityField: "id", forbiddenField: "ownerId",
		},
		{
			name: "content", reader: contentReader,
			target:       domainreader.ObjectTarget{ObjectTypeRef: "content.Post", ObjectID: "post-1"},
			operationRef: "content.post.GetPost", identityField: "postId", forbiddenField: "internalSecret",
		},
		{
			name: "entity", reader: entityReader,
			target:       domainreader.ObjectTarget{ObjectTypeRef: "entity.Homepage", ObjectID: "homepage-1"},
			operationRef: "entity.homepage.GetHomepageDetail", identityField: "homepageId", forbiddenField: "ownerUserId",
		},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			result, err := test.reader.ReadObjectContext(t.Context(), test.target)
			if err != nil {
				t.Fatal(err)
			}
			if result.Target != test.target || result.OperationRef != test.operationRef ||
				!result.CapturedAt.Equal(observedAt) ||
				!strings.HasPrefix(result.SourceDigest, "sha256:") || len(result.SourceDigest) != 71 ||
				result.Value[test.identityField] != test.target.ObjectID || result.Value[test.forbiddenField] != nil ||
				result.TokenCost <= 0 || result.Summary == "" {
				t.Fatalf("result=%+v", result)
			}
		})
	}

	for _, rejected := range []struct {
		reader domainreader.ObjectContextReader
		target domainreader.ObjectTarget
	}{
		{circleReader, domainreader.ObjectTarget{ObjectTypeRef: "circle.Circle", ObjectID: "private"}},
		{contentReader, domainreader.ObjectTarget{ObjectTypeRef: "content.Post", ObjectID: "excluded"}},
		{contentReader, domainreader.ObjectTarget{ObjectTypeRef: "content.Post", ObjectID: "oversized"}},
		{entityReader, domainreader.ObjectTarget{ObjectTypeRef: "entity.Homepage", ObjectID: "candidate"}},
	} {
		if _, err := rejected.reader.ReadObjectContext(t.Context(), rejected.target); err == nil {
			t.Fatalf("unsafe or unbounded target was accepted: %+v", rejected.target)
		}
	}
}

func TestCanonicalObjectReaderAssemblyFailsClosedWhenOwnerEndpointIsMissing(t *testing.T) {
	_, err := domainreader.NewCanonicalReaders(domainreader.CanonicalReadersConfig{
		Descriptors: canonicalObjectDescriptorCatalog(t),
		Definitions: domainreader.ProductionReaderDefinitions(),
		ServiceTransports: map[string]domainreader.ReaderTransport{
			"circle-service": {BaseURL: "http://circle.invalid", HTTPClient: http.DefaultClient},
		},
	})
	if err == nil {
		t.Fatal("partial canonical Reader bundle was accepted")
	}
}

func TestCanonicalObjectReaderAssemblyFailsClosedForUnknownAndDuplicateDefinitions(t *testing.T) {
	catalog := canonicalObjectDescriptorCatalog(t)
	notCalled := func(
		_ domainreader.ReaderTransport,
		_ domainreader.ReaderAuthority,
		_ func() time.Time,
	) (domainreader.ObjectContextReader, error) {
		t.Fatal("invalid definition reached its adapter factory")
		return nil, nil
	}
	_, err := domainreader.NewCanonicalReaders(domainreader.CanonicalReadersConfig{
		Descriptors: catalog,
		Definitions: []domainreader.ReaderDefinition{{
			DescriptorID: "content.unknown_context",
			Build:        notCalled,
		}},
	})
	if err == nil {
		t.Fatal("definition without canonical Descriptor was accepted")
	}
	definition := domainreader.ProductionReaderDefinitions()[0]
	_, err = domainreader.NewCanonicalReaders(domainreader.CanonicalReadersConfig{
		Descriptors: catalog,
		Definitions: []domainreader.ReaderDefinition{definition, definition},
		ServiceTransports: map[string]domainreader.ReaderTransport{
			"circle-service": {BaseURL: "http://circle.invalid", HTTPClient: http.DefaultClient},
		},
	})
	if err == nil {
		t.Fatal("duplicate Reader definition was accepted")
	}
}

func canonicalObjectDescriptorCatalog(t *testing.T) *readerresource.Catalog {
	t.Helper()
	descriptors, err := contextinfra.RuntimeDescriptors()
	if err != nil {
		t.Fatal(err)
	}
	catalog, err := readerresource.NewCatalog(descriptors)
	if err != nil {
		t.Fatal(err)
	}
	return catalog
}
