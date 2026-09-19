package reaction

import (
	"context"
	"time"

	reactiondomain "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction"
	reactionports "quwoquan_service/services/content-service/internal/content/content_reaction/domain/reaction/ports"
)

type ContentReactionStatisticsState string

const (
	StatisticsAvailable   ContentReactionStatisticsState = "available"
	StatisticsStale       ContentReactionStatisticsState = "stale"
	StatisticsUnavailable ContentReactionStatisticsState = "unavailable"
)

type ContentReactionStatisticsSnapshot struct {
	Generation       string
	StatsVersion     int64
	LikeCount        int64
	DislikeCount     int64
	SourceCheckpoint string
	AsOf             time.Time
	ExpiresAt        time.Time
}

type ContentReactionStatisticsSlice struct {
	OwnerKind string
	OwnerID   string
	State     ContentReactionStatisticsState
	Snapshot  *ContentReactionStatisticsSnapshot
}

type ContentReactionViewerAttachment struct {
	State    string
	Reaction *reactiondomain.Value
	Version  *int64
}
type ContentReactionPresentationSlice struct {
	Target           reactiondomain.Target
	Statistics       ContentReactionStatisticsSlice
	ViewerAttachment ContentReactionViewerAttachment
}

type ContentReactionStatisticsReader interface {
	ReadStatistics(context.Context, reactiondomain.Target) (ContentReactionStatisticsSlice, error)
	ReadPersonaLikes(context.Context, string) (ContentReactionStatisticsSlice, error)
}

// StatisticsFact is the validated complete after-state consumed by the
// statistics ledger. The public alias avoids making persistence duplicate the
// event decoder or its identity validation.
type StatisticsFact struct {
	ReactionID     string
	Version        int64
	TargetKind     string
	TargetID       string
	ActorDimension string
	ActorID        string
	Reaction       string
	OccurredAt     time.Time
}

func DecodeStatisticsFact(fact reactionports.OutboxFact) (StatisticsFact, error) {
	payload, err := decodeReactionStateChangedFact(fact)
	if err != nil {
		return StatisticsFact{}, err
	}
	return StatisticsFact{
		ReactionID: payload.ReactionID, Version: payload.Version,
		TargetKind: payload.TargetKind, TargetID: payload.TargetID,
		ActorDimension: payload.ActorDimension, ActorID: payload.ActorID,
		Reaction: payload.Reaction, OccurredAt: payload.OccurredAt,
	}, nil
}
