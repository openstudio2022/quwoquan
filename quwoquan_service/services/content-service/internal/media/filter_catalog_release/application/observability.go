package filtercatalogrelease

import (
	"time"

	filtercatalogports "quwoquan_service/services/content-service/internal/media/filter_catalog_release/domain/ports"
)

const (
	OperationStage    = "stage"
	OperationActivate = "activate"
	OperationRollback = "rollback"
	OperationGet      = "get"
)

type Observer interface {
	Observe(
		operation string,
		outcome string,
		replayed bool,
		duration time.Duration,
	)
}

type noopObserver struct{}

func (noopObserver) Observe(string, string, bool, time.Duration) {}

type ServiceOption func(*Service)

func WithObserver(observer Observer) ServiceOption {
	return func(service *Service) {
		if observer != nil {
			service.observer = observer
		}
	}
}

func WithActiveFilterCatalogInvalidator(
	invalidator filtercatalogports.ActiveFilterCatalogInvalidator,
) ServiceOption {
	return func(service *Service) {
		if invalidator != nil {
			service.invalidator = invalidator
		}
	}
}
