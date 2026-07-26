package report

import (
	"context"
	"time"
)

type LifecycleObserver interface {
	ReportCreated(context.Context)
	ReportClosed(
		_ context.Context,
		status string,
		createdAt time.Time,
		closedAt time.Time,
	)
}

type ReportServiceOption func(*ReportService)

func WithLifecycleObserver(observer LifecycleObserver) ReportServiceOption {
	return func(service *ReportService) {
		service.observer = observer
	}
}
