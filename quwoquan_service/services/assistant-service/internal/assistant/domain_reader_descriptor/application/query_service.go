package application

import (
	"context"
	"errors"
	"strings"

	"go.opentelemetry.io/otel/attribute"

	rtobs "quwoquan_service/runtime/observability"
	descriptorerrors "quwoquan_service/services/assistant-service/generated/assistant/domain_reader_descriptor"
	"quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/domain/model"
	"quwoquan_service/services/assistant-service/internal/assistant/domain_reader_descriptor/domain/ports"
)

type GetDescriptorQuery struct {
	DescriptorID string
}

type ListDescriptorsQuery struct {
	Limit int
}

type QueryService struct {
	catalog ports.Catalog
}

func NewQueryService(catalog ports.Catalog) *QueryService {
	return &QueryService{catalog: catalog}
}

func (service *QueryService) GetDescriptor(
	ctx context.Context,
	query GetDescriptorQuery,
) (_ model.Descriptor, err error) {
	descriptorID := strings.TrimSpace(query.DescriptorID)
	ctx, span := rtobs.StartBusinessSpan(
		ctx,
		"assistant.domain_reader_descriptor.GetDomainReaderDescriptor",
		attribute.String("domain_reader.descriptor_id", descriptorID),
	)
	defer func() { rtobs.EndSpan(span, err) }()

	if descriptorID == "" {
		return model.Descriptor{},
			descriptorerrors.AppErrorFromDomainReaderInvalidArgument(
				"descriptorId is required",
			)
	}
	if service == nil || service.catalog == nil {
		return model.Descriptor{},
			descriptorerrors.AppErrorFromDomainReaderCatalogUnavailable(
				"domain reader catalog is not configured",
			)
	}
	descriptor, readErr := service.catalog.GetDescriptor(ctx, descriptorID)
	if errors.Is(readErr, model.ErrDescriptorNotFound) {
		return model.Descriptor{},
			descriptorerrors.AppErrorFromDomainReaderDescriptorNotFound(
				"domain reader descriptor was not found",
			)
	}
	if readErr != nil {
		return model.Descriptor{},
			descriptorerrors.AppErrorFromDomainReaderCatalogUnavailable(
				readErr.Error(),
			)
	}
	return descriptor, nil
}

func (service *QueryService) ListDescriptors(
	ctx context.Context,
	query ListDescriptorsQuery,
) (_ model.ListSlice, err error) {
	ctx, span := rtobs.StartBusinessSpan(
		ctx,
		"assistant.domain_reader_descriptor.ListDomainReaderDescriptors",
		attribute.Int("list.limit", query.Limit),
	)
	defer func() { rtobs.EndSpan(span, err) }()

	if query.Limit <= 0 || query.Limit > 100 {
		return model.ListSlice{},
			descriptorerrors.AppErrorFromDomainReaderInvalidArgument(
				"limit must be between 1 and 100",
			)
	}
	if service == nil || service.catalog == nil {
		return model.ListSlice{},
			descriptorerrors.AppErrorFromDomainReaderCatalogUnavailable(
				"domain reader catalog is not configured",
			)
	}
	items, readErr := service.catalog.ListDescriptors(ctx, query.Limit)
	if readErr != nil {
		return model.ListSlice{},
			descriptorerrors.AppErrorFromDomainReaderCatalogUnavailable(
				readErr.Error(),
			)
	}
	if items == nil {
		items = []model.Descriptor{}
	}
	span.SetAttributes(attribute.Int("domain_reader.item_count", len(items)))
	return model.ListSlice{Items: items}, nil
}
