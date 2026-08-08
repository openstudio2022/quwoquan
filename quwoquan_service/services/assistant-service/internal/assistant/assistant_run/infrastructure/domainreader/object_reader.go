package domainreader

import (
	"context"
	"fmt"
	"sort"
	"strings"
	"time"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	readermodel "quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/domain/model"
	readerports "quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/domain/ports"
)

const maxCanonicalReaderDescriptors = 100

type ObjectTarget struct {
	ObjectTypeRef string
	ObjectID      string
}

type ObjectContext struct {
	Target       ObjectTarget
	OperationRef string
	CapturedAt   time.Time
	SourceDigest string
	ArtifactRef  string
	TokenCost    int
	Value        map[string]any
	Summary      string
}

// ObjectContextReader is the object-neutral adapter boundary consumed by
// AssistantRun. Implementations may only use the public typed query declared
// by their DomainReaderDescriptor.
type ObjectContextReader interface {
	ReadObjectContext(context.Context, ObjectTarget) (ObjectContext, error)
}

// ReaderRegistration binds implementation-only facts to one canonical
// Descriptor. Resolver, owner operation and object type identities deliberately
// do not exist here: the Descriptor is their only authoring source.
type ReaderRegistration struct {
	DescriptorID string
	SurfaceKinds []string
	Reader       ObjectContextReader
}

// BoundReader is a read-only startup product. Its Descriptor fields were
// resolved from the Catalog rather than repeated by the adapter registration.
type BoundReader struct {
	Descriptor         readermodel.Descriptor
	SurfaceObjectTypes map[string]string
	Reader             ObjectContextReader
}

// CanonicalReaders is an immutable registry of Descriptor-owned Reader
// adapters. Resolver lookup is derived while the registry is assembled.
type CanonicalReaders struct {
	byResolver map[string]BoundReader
	ordered    []BoundReader
}

// NewCanonicalReaderRegistry closes the Descriptor/adapter inventory at
// startup. Missing and unknown adapters are fatal; the AgentLoop never owns a
// vertical-specific fallback path.
func NewCanonicalReaderRegistry(
	descriptors readerports.Catalog,
	registrations ...ReaderRegistration,
) (CanonicalReaders, error) {
	if descriptors == nil {
		return CanonicalReaders{}, fmt.Errorf("canonical domain reader descriptor catalog is unavailable")
	}
	listed, err := descriptors.ListDescriptors(context.Background(), maxCanonicalReaderDescriptors)
	if err != nil {
		return CanonicalReaders{}, fmt.Errorf("list canonical domain reader descriptors: %w", err)
	}
	if len(listed) == maxCanonicalReaderDescriptors {
		return CanonicalReaders{}, fmt.Errorf("canonical domain reader descriptor inventory exceeds startup bound")
	}
	publicObjects := make(map[string]readermodel.Descriptor)
	resolverOwners := make(map[string]string)
	for _, descriptor := range listed {
		if !isCanonicalObjectDescriptor(descriptor) {
			continue
		}
		if err := validateCanonicalObjectDescriptor(descriptor); err != nil {
			return CanonicalReaders{}, err
		}
		if _, duplicate := publicObjects[descriptor.DescriptorID]; duplicate {
			return CanonicalReaders{}, fmt.Errorf(
				"duplicate canonical domain reader descriptor %q",
				descriptor.DescriptorID,
			)
		}
		if owner, duplicate := resolverOwners[descriptor.ResolverRef]; duplicate {
			return CanonicalReaders{}, fmt.Errorf(
				"duplicate canonical domain reader resolver %q owned by %q and %q",
				descriptor.ResolverRef,
				owner,
				descriptor.DescriptorID,
			)
		}
		publicObjects[descriptor.DescriptorID] = descriptor.Clone()
		resolverOwners[descriptor.ResolverRef] = descriptor.DescriptorID
	}
	if len(publicObjects) == 0 {
		return CanonicalReaders{}, fmt.Errorf("canonical domain reader descriptor set is empty")
	}
	registry := CanonicalReaders{
		byResolver: make(map[string]BoundReader, len(registrations)),
		ordered:    make([]BoundReader, 0, len(registrations)),
	}
	registered := make(map[string]struct{}, len(registrations))
	for _, raw := range registrations {
		registration, err := canonicalReaderRegistration(raw)
		if err != nil {
			return CanonicalReaders{}, err
		}
		if _, duplicate := registered[registration.DescriptorID]; duplicate {
			return CanonicalReaders{}, fmt.Errorf(
				"duplicate canonical domain reader registration %q",
				registration.DescriptorID,
			)
		}
		descriptor, exists := publicObjects[registration.DescriptorID]
		if !exists {
			return CanonicalReaders{}, fmt.Errorf(
				"unknown canonical domain reader registration %q",
				registration.DescriptorID,
			)
		}
		surfaceTypes := make(map[string]string, len(registration.SurfaceKinds))
		for _, surfaceKind := range registration.SurfaceKinds {
			surfaceTypes[surfaceKind] = descriptor.ObjectTypeRefs[0]
		}
		bound := BoundReader{
			Descriptor:         descriptor.Clone(),
			SurfaceObjectTypes: surfaceTypes,
			Reader:             registration.Reader,
		}
		registry.byResolver[descriptor.ResolverRef] = bound
		registry.ordered = append(registry.ordered, bound)
		registered[registration.DescriptorID] = struct{}{}
	}
	for descriptorID, descriptor := range publicObjects {
		if _, exists := registered[descriptorID]; !exists {
			return CanonicalReaders{}, fmt.Errorf(
				"canonical domain reader descriptor %q (%s) has no adapter registration",
				descriptorID,
				descriptor.ResolverRef,
			)
		}
	}
	sort.Slice(registry.ordered, func(left, right int) bool {
		return registry.ordered[left].Descriptor.ResolverRef <
			registry.ordered[right].Descriptor.ResolverRef
	})
	return registry, nil
}

func (readers CanonicalReaders) BoundReaders() []BoundReader {
	result := make([]BoundReader, 0, len(readers.ordered))
	for _, reader := range readers.ordered {
		result = append(result, cloneBoundReader(reader))
	}
	return result
}

func (readers CanonicalReaders) Reader(resolverRef string) (ObjectContextReader, bool) {
	reader, found := readers.byResolver[strings.TrimSpace(resolverRef)]
	if !found || reader.Reader == nil {
		return nil, false
	}
	return reader.Reader, true
}

func (readers CanonicalReaders) OwnerServices() []string {
	seen := make(map[string]struct{}, len(readers.ordered))
	owners := make([]string, 0, len(readers.ordered))
	for _, reader := range readers.ordered {
		owner := reader.Descriptor.OwnerService
		if _, exists := seen[owner]; exists {
			continue
		}
		seen[owner] = struct{}{}
		owners = append(owners, owner)
	}
	sort.Strings(owners)
	return owners
}

func canonicalReaderRegistration(raw ReaderRegistration) (ReaderRegistration, error) {
	raw.DescriptorID = strings.TrimSpace(raw.DescriptorID)
	if raw.DescriptorID == "" || raw.Reader == nil {
		return ReaderRegistration{}, fmt.Errorf("canonical domain reader registration is incomplete")
	}
	seen := make(map[string]struct{}, len(raw.SurfaceKinds))
	surfaces := make([]string, 0, len(raw.SurfaceKinds))
	for _, surfaceKind := range raw.SurfaceKinds {
		surfaceKind = strings.TrimSpace(surfaceKind)
		if surfaceKind == "" {
			return ReaderRegistration{}, fmt.Errorf("canonical domain reader surface kind is blank")
		}
		if _, duplicate := seen[surfaceKind]; duplicate {
			continue
		}
		seen[surfaceKind] = struct{}{}
		surfaces = append(surfaces, surfaceKind)
	}
	sort.Strings(surfaces)
	raw.SurfaceKinds = surfaces
	return raw, nil
}

func isCanonicalObjectDescriptor(descriptor readermodel.Descriptor) bool {
	return descriptor.Authority == generated.AssistantContextAuthorityDomainCanonical &&
		descriptor.Sensitivity == generated.AssistantContextSensitivityPublic &&
		descriptor.CitationPolicy == readermodel.CitationEntityReference &&
		containsString(descriptor.AcceptedSourceKinds, "domain")
}

func validateCanonicalObjectDescriptor(descriptor readermodel.Descriptor) error {
	if strings.TrimSpace(descriptor.DescriptorID) == "" ||
		strings.TrimSpace(descriptor.ResolverRef) == "" ||
		strings.TrimSpace(descriptor.OwnerService) == "" ||
		strings.TrimSpace(descriptor.DescriptorDigest) == "" ||
		len(descriptor.OwnerOperationRefs) != 1 ||
		len(descriptor.ObjectTypeRefs) != 1 {
		return fmt.Errorf(
			"canonical domain reader descriptor %q must own exactly one operation and object type",
			descriptor.DescriptorID,
		)
	}
	return nil
}

func cloneBoundReader(reader BoundReader) BoundReader {
	reader.Descriptor = reader.Descriptor.Clone()
	surfaceTypes := make(map[string]string, len(reader.SurfaceObjectTypes))
	for surfaceKind, objectType := range reader.SurfaceObjectTypes {
		surfaceTypes[surfaceKind] = objectType
	}
	reader.SurfaceObjectTypes = surfaceTypes
	return reader
}
