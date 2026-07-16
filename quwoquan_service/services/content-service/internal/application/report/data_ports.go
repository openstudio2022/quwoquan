package report

import reportports "quwoquan_service/services/content-service/internal/domain/report/ports"

type DataPorts struct {
	Aggregate reportports.AggregateStore
	Detail    DetailReader
	Queue     QueueReader
}

func BindDataPorts(adapter interface {
	reportports.AggregateStore
	DetailReader
	QueueReader
}) DataPorts {
	return DataPorts{
		Aggregate: adapter,
		Detail:    adapter,
		Queue:     adapter,
	}
}
