package reaction

import reactionports "quwoquan_service/services/content-service/internal/domain/reaction/ports"

type DataPorts struct {
	Aggregate     reactionports.AggregateStore
	State         ContentReactionStateReader
	Target        ReactionTargetReader
	CommentCounts CommentReactionCountReader
}

func BindDataPorts(adapter interface {
	reactionports.AggregateStore
	ContentReactionStateReader
	CommentReactionCountReader
}, target ReactionTargetReader) DataPorts {
	return DataPorts{
		Aggregate:     adapter,
		State:         adapter,
		Target:        target,
		CommentCounts: adapter,
	}
}
