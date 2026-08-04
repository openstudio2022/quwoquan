package ports

import (
	"context"

	"quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/domain/model"
)

// Catalog is the only read boundary for canonical DomainReaderDescriptor
// resources. Both runtime binding and internal catalog queries must consume the
// same instance so the query surface cannot describe policy different from the
// executing registry.
type Catalog interface {
	GetDescriptor(context.Context, string) (model.Descriptor, error)
	GetDescriptorByResolverRef(context.Context, string) (model.Descriptor, error)
	ListDescriptors(context.Context, int) ([]model.Descriptor, error)
}
