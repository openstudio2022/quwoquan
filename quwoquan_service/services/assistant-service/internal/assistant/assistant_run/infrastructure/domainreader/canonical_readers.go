package domainreader

import (
	"context"
	"fmt"
	"strings"
	"time"

	readerports "quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/domain/ports"
)

const canonicalObjectResponseLimit int64 = 512 << 10

type CanonicalReadersConfig struct {
	Descriptors       readerports.Catalog
	Definitions       []ReaderDefinition
	ServiceTransports map[string]ReaderTransport
	Now               func() time.Time
}

// NewCanonicalReaders builds every registered adapter through one production
// path and then closes the Descriptor/adapter inventory. No vertical identity
// is switched on here.
func NewCanonicalReaders(config CanonicalReadersConfig) (CanonicalReaders, error) {
	if config.Descriptors == nil {
		return CanonicalReaders{}, fmt.Errorf("canonical domain reader descriptor catalog is unavailable")
	}
	if len(config.Definitions) == 0 {
		return CanonicalReaders{}, fmt.Errorf("canonical domain reader definitions are empty")
	}
	registrations := make([]ReaderRegistration, 0, len(config.Definitions))
	seenDefinitions := make(map[string]struct{}, len(config.Definitions))
	for _, raw := range config.Definitions {
		descriptorID := strings.TrimSpace(raw.DescriptorID)
		if descriptorID == "" || raw.Build == nil {
			return CanonicalReaders{}, fmt.Errorf("canonical domain reader definition is incomplete")
		}
		if _, duplicate := seenDefinitions[descriptorID]; duplicate {
			return CanonicalReaders{}, fmt.Errorf(
				"duplicate canonical domain reader definition %q",
				descriptorID,
			)
		}
		descriptor, err := config.Descriptors.GetDescriptor(
			context.Background(),
			descriptorID,
		)
		if err != nil {
			return CanonicalReaders{}, fmt.Errorf(
				"canonical domain reader definition %q has no descriptor: %w",
				descriptorID,
				err,
			)
		}
		if !isCanonicalObjectDescriptor(descriptor) {
			return CanonicalReaders{}, fmt.Errorf(
				"canonical domain reader definition %q references a non-public object descriptor",
				descriptorID,
			)
		}
		if err := validateCanonicalObjectDescriptor(descriptor); err != nil {
			return CanonicalReaders{}, err
		}
		transport, exists := config.ServiceTransports[descriptor.OwnerService]
		if !exists || strings.TrimSpace(transport.BaseURL) == "" || transport.HTTPClient == nil {
			return CanonicalReaders{}, fmt.Errorf(
				"canonical domain reader %q is missing %s transport",
				descriptorID,
				descriptor.OwnerService,
			)
		}
		authority := ReaderAuthority{
			DescriptorID:     descriptor.DescriptorID,
			DescriptorDigest: descriptor.DescriptorDigest,
			ResolverRef:      descriptor.ResolverRef,
			OwnerService:     descriptor.OwnerService,
			OperationRef:     descriptor.OwnerOperationRefs[0],
			ObjectTypeRef:    descriptor.ObjectTypeRefs[0],
		}
		reader, err := raw.Build(transport, authority, config.Now)
		if err != nil {
			return CanonicalReaders{}, fmt.Errorf(
				"build canonical domain reader %q: %w",
				descriptorID,
				err,
			)
		}
		registrations = append(registrations, ReaderRegistration{
			DescriptorID: descriptorID,
			SurfaceKinds: append([]string(nil), raw.SurfaceKinds...),
			Reader:       reader,
		})
		seenDefinitions[descriptorID] = struct{}{}
	}
	return NewCanonicalReaderRegistry(config.Descriptors, registrations...)
}

func circleReaderSpec() objectReaderSpec {
	return objectReaderSpec{
		pathParameter: "circleId", responseObjectField: "data", identityField: "id",
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
		pathParameter: "postId", identityField: "postId",
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
		pathParameter: "homepageId", identityField: "homepageId",
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
