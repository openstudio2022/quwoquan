package persistence

import (
	"context"

	reportmodel "quwoquan_service/services/content-service/internal/domain/report/model"
)

type ReportRepository interface {
	Create(ctx context.Context, report *reportmodel.Report) error
	FindByID(ctx context.Context, id string) (*reportmodel.Report, bool, error)
	Update(ctx context.Context, report *reportmodel.Report) error
	List(ctx context.Context, limit int) ([]*reportmodel.Report, error)
}
