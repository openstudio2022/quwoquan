package reaction

import reactionports "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction/ports"

type DataPorts struct {
	Aggregate     reactionports.AggregateStore
	State         ContentReactionStateReader
	Target        ReactionTargetReader
	CommentCounts CommentReactionCountReader
	Statistics    ContentReactionStatisticsReader
}

func BindDataPorts(adapter interface {
	reactionports.AggregateStore
	ContentReactionStateReader
	CommentReactionCountReader
}, target ReactionTargetReader, statistics ...ContentReactionStatisticsReader) DataPorts {
	return DataPorts{
		Aggregate:     adapter,
		State:         adapter,
		Target:        target,
		CommentCounts: adapter,
		Statistics: func() ContentReactionStatisticsReader {
			if len(statistics) > 0 {
				return statistics[0]
			}
			return nil
		}(),
	}
}
