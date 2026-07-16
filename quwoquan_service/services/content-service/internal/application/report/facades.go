package report

import (
	"context"
)

// Facades 是 transport 可见的 Report 对象应用入口。
type Facades struct {
	ReportCommandFacade
	ReportQueryFacade
}

type ReportCommandFacade interface {
	CreateReport(context.Context, CreateReportCommand) (ReportCommandResult, error)
	BeginReview(context.Context, BeginReviewReportCommand) (ReportCommandResult, error)
	Resolve(context.Context, ResolveReportCommand) (ReportCommandResult, error)
	Dismiss(context.Context, DismissReportCommand) (ReportCommandResult, error)
}

type ReportQueryFacade interface {
	GetReport(context.Context, GetReportQuery) (ReportDetailSlice, error)
	ListReports(context.Context, ListReportsQuery) (ReportQueueSlice, error)
}

func BindFacades(service *ReportService) *Facades {
	if service == nil {
		return nil
	}
	return &Facades{
		ReportCommandFacade: service,
		ReportQueryFacade:   service,
	}
}
