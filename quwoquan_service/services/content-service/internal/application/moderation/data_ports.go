package moderation

import moderationports "quwoquan_service/services/content-service/internal/domain/moderation/ports"

type DataPorts struct {
	Aggregate   moderationports.AggregateStore
	Eligibility moderationports.PublicationEligibilityReader
}

func BindDataPorts(adapter interface {
	moderationports.AggregateStore
	moderationports.PublicationEligibilityReader
}) DataPorts {
	return DataPorts{
		Aggregate:   adapter,
		Eligibility: adapter,
	}
}
