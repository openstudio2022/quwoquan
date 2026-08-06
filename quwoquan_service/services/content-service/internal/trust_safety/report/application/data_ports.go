package report

import reportports "quwoquan_service/services/content-service/internal/trust_safety/report/domain/ports"

type DataPorts struct {
	Aggregate reportports.AggregateStore
	Detail    DetailReader
	Queue     QueueReader
	MyReports MyReportReader
	Safety    reportports.GatheringSafetyAuthorityStore
}

func BindDataPorts(adapter interface {
	reportports.AggregateStore
	DetailReader
	QueueReader
	MyReportReader
}) DataPorts {
	var safety reportports.GatheringSafetyAuthorityStore
	if candidate, ok := any(adapter).(reportports.GatheringSafetyAuthorityStore); ok {
		safety = candidate
	}
	return DataPorts{
		Aggregate: adapter,
		Detail:    adapter,
		Queue:     adapter,
		MyReports: adapter,
		Safety:    safety,
	}
}
