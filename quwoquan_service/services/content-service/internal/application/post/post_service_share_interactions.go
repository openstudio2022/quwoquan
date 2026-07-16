package post

import (
	"context"
	"strings"
	"time"

	postdomain "quwoquan_service/services/content-service/internal/domain/post"
	postmodel "quwoquan_service/services/content-service/internal/domain/post/model"
	contentgenerated "quwoquan_service/services/content-service/internal/generated"
)

func (s *PostService) ListProfileShareInteractions(
	ctx context.Context,
	profileSubjectID string,
	direction string,
	cursor string,
	limit int,
) ([]postmodel.ProfileInteractionActivityView, string, bool, error) {
	if s.shareInteractionStore == nil {
		return nil, "", false, contentgenerated.AppErrorFromInteractionReadModelUnavailable(
			"share interaction store is not configured",
		)
	}
	profileSubjectID = strings.TrimSpace(profileSubjectID)
	direction = strings.TrimSpace(direction)
	if direction != "received" && direction != "sent" {
		return nil, "", false, contentgenerated.AppErrorFromInteractionTypeInvalid(
			"unsupported share direction",
		)
	}
	if limit <= 0 {
		limit = 20
	}
	if limit > profileInteractionActivityMaxLimit {
		limit = profileInteractionActivityMaxLimit
	}
	var cursorTime time.Time
	var cursorID string
	if strings.TrimSpace(cursor) != "" {
		var ok bool
		cursorTime, cursorID, ok = decodeProfileInteractionCursor(cursor)
		if !ok {
			return nil, "", false, contentgenerated.AppErrorFromInteractionCursorInvalid(
				"malformed profile share cursor",
			)
		}
	}
	occurrences, hasMore, err := s.shareInteractionStore.List(ctx, postdomain.ShareInteractionQuery{
		SubAccountID: profileSubjectID,
		Direction:    direction,
		CursorTime:   cursorTime,
		CursorID:     cursorID,
		Limit:        limit,
	})
	if err != nil {
		return nil, "", false, contentgenerated.AppErrorFromInteractionReadModelUnavailable(err.Error())
	}
	items := make([]postmodel.ProfileInteractionActivityView, 0, len(occurrences))
	for _, occurrence := range occurrences {
		items = append(items, projectShareInteractionOccurrence(occurrence, direction))
	}
	nextCursor := ""
	if hasMore && len(occurrences) > 0 {
		last := occurrences[len(occurrences)-1]
		nextCursor = encodeProfileInteractionCursor(last.OccurredAt, last.InteractionID)
	}
	return items, nextCursor, hasMore, nil
}

func (s *PostService) MarkProfileShareInteractionState(
	ctx context.Context,
	subAccountID string,
	interactionID string,
	state string,
) error {
	if s.shareInteractionStore == nil {
		return contentgenerated.AppErrorFromInteractionReadModelUnavailable(
			"share interaction store is not configured",
		)
	}
	state = strings.TrimSpace(state)
	if state != "seen" && state != "read" {
		return contentgenerated.AppErrorFromInteractionTypeInvalid("state must be seen or read")
	}
	if err := s.shareInteractionStore.MarkState(
		ctx,
		strings.TrimSpace(subAccountID),
		strings.TrimSpace(interactionID),
		state,
		time.Now().UTC(),
	); err != nil {
		return contentgenerated.AppErrorFromInteractionReadModelUnavailable(err.Error())
	}
	return nil
}

func projectShareInteractionOccurrence(
	item postdomain.ShareInteractionOccurrence,
	direction string,
) postmodel.ProfileInteractionActivityView {
	targetKind := strings.TrimSpace(item.TargetKind)
	if targetKind == "" {
		targetKind = "record"
	}
	availability := strings.TrimSpace(item.TargetAvailability)
	if availability == "" {
		availability = "active"
	}
	displayID := item.ActorSubAccountID
	displayName := defaultString(item.ActorDisplayName, item.ActorSubAccountID)
	displayAvatar := item.ActorAvatarURL
	primaryText := "转发了你的" + shareTargetLabel(targetKind)
	impactText := item.ImpactPrimaryText
	impactLink := item.ImpactDeepLink
	seenAt := item.SeenAt
	readAt := item.ReadAt
	if direction == "sent" {
		displayID = item.CounterpartSubAccountID
		displayName = defaultString(item.CounterpartDisplayName, item.CounterpartSubAccountID)
		displayAvatar = item.CounterpartAvatarURL
		primaryText = "你转发了 " + displayName + " 的" + shareTargetLabel(targetKind)
		impactText = ""
		impactLink = ""
		seenAt = time.Time{}
		readAt = time.Time{}
	}
	previewRouteID := ""
	if availability == "active" {
		previewRouteID = "workBrowser"
	}
	return postmodel.ProfileInteractionActivityView{
		ActivityId:              item.InteractionID,
		ActivityType:            "share",
		Direction:               direction,
		ActorSubAccountId:       item.ActorSubAccountID,
		ActorDisplayName:        defaultString(item.ActorDisplayName, item.ActorSubAccountID),
		ActorAvatarUrl:          item.ActorAvatarURL,
		CounterpartSubAccountId: item.CounterpartSubAccountID,
		CounterpartDisplayName:  defaultString(item.CounterpartDisplayName, item.CounterpartSubAccountID),
		CounterpartAvatarUrl:    item.CounterpartAvatarURL,
		TargetSubAccountId:      item.TargetSubAccountID,
		TargetContentId:         item.TargetContentID,
		TargetContentType:       item.TargetContentType,
		TargetContentSummary:    item.TargetContentSummary,
		TargetKind:              targetKind,
		TargetAvailability:      availability,
		TargetReplyCount:        item.TargetReplyCount,
		DisplaySubAccountId:     displayID,
		DisplayName:             displayName,
		DisplayAvatarUrl:        displayAvatar,
		DisplayUserRouteId:      "userProfile",
		PrimaryText:             primaryText,
		ContextText:             item.ShareText,
		PreviewMediaKind:        item.PreviewMediaKind,
		PreviewImageUrl:         item.PreviewImageURL,
		PreviewText:             item.PreviewText,
		PreviewUnavailable:      availability != "active",
		PreviewObjectId:         item.TargetContentID,
		PreviewRouteId:          previewRouteID,
		OutboundShareEventId:    item.OutboundShareEventID,
		ShareText:               item.ShareText,
		ImpactPrimaryText:       impactText,
		ImpactDeepLink:          impactLink,
		FilterKeys:              []string{"shares"},
		CreatedAt:               item.OccurredAt,
		OccurredAt:              item.OccurredAt,
		SeenAt:                  seenAt,
		ReadAt:                  readAt,
	}
}

func shareTargetLabel(targetKind string) string {
	if targetKind == "discussion" {
		return "讨论"
	}
	return "记录"
}
