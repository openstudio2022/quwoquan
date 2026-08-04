package domainreader

import (
	"fmt"
	"net/http"
	"strings"
	"time"
)

const canonicalObjectResponseLimit int64 = 512 << 10

type CanonicalReadersConfig struct {
	ServiceBaseURLs    map[string]string
	ServiceHTTPClients map[string]*http.Client
	Now                func() time.Time
}

// CanonicalReaders is the complete object-neutral Reader bundle currently
// supported by AssistantRun. Construction is all-or-nothing so a deployment
// cannot advertise a resolver whose owning service endpoint is absent.
type CanonicalReaders struct {
	Circle  ObjectContextReader
	Content ObjectContextReader
	Entity  ObjectContextReader
}

// NewCanonicalReaders is the single assembly API for Circle, Content and
// Entity context. It validates every generated operation boundary before any
// resolver can be registered.
func NewCanonicalReaders(config CanonicalReadersConfig) (CanonicalReaders, error) {
	readers := CanonicalReaders{}
	targets := []struct {
		service string
		spec    objectReaderSpec
		assign  func(ObjectContextReader)
	}{
		{service: "circle-service", spec: circleReaderSpec(), assign: func(value ObjectContextReader) { readers.Circle = value }},
		{service: "content-service", spec: contentReaderSpec(), assign: func(value ObjectContextReader) { readers.Content = value }},
		{service: "entity-service", spec: entityReaderSpec(), assign: func(value ObjectContextReader) { readers.Entity = value }},
	}
	for _, target := range targets {
		baseURL := strings.TrimSpace(config.ServiceBaseURLs[target.service])
		if baseURL == "" {
			return CanonicalReaders{}, fmt.Errorf("missing %s base URL", target.service)
		}
		httpClient := config.ServiceHTTPClients[target.service]
		if httpClient == nil {
			return CanonicalReaders{}, fmt.Errorf("missing %s observed HTTP client", target.service)
		}
		reader, err := newHTTPObjectReader(baseURL, httpClient, config.Now, target.spec)
		if err != nil {
			return CanonicalReaders{}, err
		}
		target.assign(reader)
	}
	return readers, nil
}

func circleReaderSpec() objectReaderSpec {
	return objectReaderSpec{
		domain: "circle", operationRef: "circle.circle.GetCircle",
		objectTypeRef: "circle.Circle", pathParameter: "circleId",
		responseObjectField: "data", identityField: "id",
		projectionFields: []string{
			"id", "name", "description", "rulesText", "welcomeMessage", "coverUrl", "iconUrl",
			"category", "subCategory", "tags", "memberCount", "postCount", "weeklyActiveCount",
			"status", "visibility", "joinPolicy", "kind", "displaySubjectType", "createdAt", "updatedAt",
		},
		requiredFields: []string{"id", "name", "status", "visibility", "updatedAt"},
		requiredStringValues: map[string][]string{
			"status": {"active"}, "visibility": {"public"},
		},
		timestampFields:  []string{"createdAt", "updatedAt"},
		summaryFields:    []string{"name", "description"},
		maxResponseBytes: canonicalObjectResponseLimit,
	}
}

func contentReaderSpec() objectReaderSpec {
	return objectReaderSpec{
		domain: "content", operationRef: "content.post.GetPost",
		objectTypeRef: "content.Post", pathParameter: "postId", identityField: "postId",
		projectionFields: []string{
			"postId", "contentType", "contentIdentity", "assistantUsePolicy", "authorId", "authorDisplayName",
			"title", "body", "summary", "tagRefs", "entityRefs", "semanticMentions", "mediaAssetIds",
			"coverUrl", "thumbnailUrl", "sourceAttribution", "articleMarkdown", "location", "locationName",
			"geoTagRef", "visitedAt", "primaryHomepageId", "canonicalEntityId", "primaryHomepageType",
			"status", "visibility", "likeCount", "commentCount", "shareCount", "viewCount",
			"createdAt", "updatedAt", "publishedAt",
		},
		requiredFields: []string{"postId", "contentType", "assistantUsePolicy", "status", "visibility", "updatedAt"},
		requiredStringValues: map[string][]string{
			"assistantUsePolicy": {"inherit"}, "status": {"published"}, "visibility": {"public"},
		},
		timestampFields:  []string{"createdAt", "updatedAt", "publishedAt", "visitedAt"},
		summaryFields:    []string{"title", "summary", "body"},
		maxResponseBytes: canonicalObjectResponseLimit,
	}
}

func entityReaderSpec() objectReaderSpec {
	return objectReaderSpec{
		domain: "entity", operationRef: "entity.homepage.GetHomepageDetail",
		objectTypeRef: "entity.Homepage", pathParameter: "homepageId", identityField: "homepageId",
		projectionFields: []string{
			"homepageId", "title", "subtitle", "homepageType", "status", "claimStatus", "categoryTags",
			"coverUrl", "address", "city", "location", "verified", "establishedYear", "averageRating",
			"ratingCount", "reviewSummary", "structuredFacts", "assistantContext", "introductionMarkdown",
			"introductionAssets", "primarySource", "sourceUrls", "createdAt", "updatedAt", "publishedAt",
		},
		requiredFields:       []string{"homepageId", "title", "homepageType", "status", "updatedAt"},
		requiredStringValues: map[string][]string{"status": {"published"}},
		timestampFields:      []string{"createdAt", "updatedAt", "publishedAt"},
		summaryFields:        []string{"title", "subtitle", "introductionMarkdown"},
		maxResponseBytes:     canonicalObjectResponseLimit,
	}
}
