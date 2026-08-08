package domainreader

import (
	"net/http"
	"time"
)

// ReaderTransport is the composition-owned endpoint for a Descriptor owner.
// Authentication is intentionally absent: canonical public Readers never
// inherit a caller credential.
type ReaderTransport struct {
	BaseURL    string
	HTTPClient *http.Client
}

// ReaderAuthority is derived from one immutable Descriptor and handed to an
// adapter factory. It is never authored by ReaderDefinition.
type ReaderAuthority struct {
	DescriptorID     string
	DescriptorDigest string
	ResolverRef      string
	OwnerService     string
	OperationRef     string
	ObjectTypeRef    string
}

type ReaderFactory func(
	ReaderTransport,
	ReaderAuthority,
	func() time.Time,
) (ObjectContextReader, error)

// ReaderDefinition is the only composition registration needed for a Reader.
// DescriptorID is a reference; all policy and domain identities remain owned
// by DomainReaderDescriptor.
type ReaderDefinition struct {
	DescriptorID string
	SurfaceKinds []string
	Build        ReaderFactory
}

// ProductionReaderDefinitions is the production adapter composition. Adding
// another Reader appends one definition; AgentLoop and resolver assembly stay
// unchanged.
func ProductionReaderDefinitions() []ReaderDefinition {
	return []ReaderDefinition{
		httpReaderDefinition(
			"circle.circle_context",
			[]string{"circle"},
			circleReaderSpec(),
		),
		httpReaderDefinition(
			"content.post_context",
			nil,
			contentReaderSpec(),
		),
		httpReaderDefinition(
			"entity.homepage_context",
			nil,
			entityReaderSpec(),
		),
	}
}

func httpReaderDefinition(
	descriptorID string,
	surfaceKinds []string,
	spec objectReaderSpec,
) ReaderDefinition {
	return ReaderDefinition{
		DescriptorID: descriptorID,
		SurfaceKinds: append([]string(nil), surfaceKinds...),
		Build: func(
			transport ReaderTransport,
			authority ReaderAuthority,
			now func() time.Time,
		) (ObjectContextReader, error) {
			return newHTTPObjectReader(transport, authority, now, spec)
		},
	}
}
