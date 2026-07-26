package moderation

import moderationports "quwoquan_service/services/content-service/internal/trust_safety/post_moderation_case/domain/ports"

type DataPorts struct {
	Aggregate   moderationports.AggregateStore
	Eligibility moderationports.PublicationEligibilityReader
	CurrentCase CurrentPostModerationCaseReader
}

func BindDataPorts(adapter interface {
	moderationports.AggregateStore
	moderationports.PublicationEligibilityReader
	CurrentPostModerationCaseReader
}) DataPorts {
	return DataPorts{
		Aggregate:   adapter,
		Eligibility: adapter,
		CurrentCase: adapter,
	}
}
