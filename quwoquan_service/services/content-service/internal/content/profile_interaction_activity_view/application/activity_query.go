package profileinteraction

import (
	"context"
	"encoding/base64"
	"fmt"
	"strconv"
	"strings"
	"time"

	contentgenerated "quwoquan_service/services/content-service/generated/content/post"
	activitymodel "quwoquan_service/services/content-service/internal/content/profile_interaction_activity_view/domain/model"
	activityports "quwoquan_service/services/content-service/internal/content/profile_interaction_activity_view/domain/ports"
)

const maxActivityPageSize = 50

type ActivityPageQuery struct {
	OwnerPersonaID  string
	ViewerPersonaID string
	Direction       string
	ActivityType    string
	Cursor          string
	Limit           int
}

type ActivityPage struct {
	Items      []activitymodel.Activity `json:"items"`
	NextCursor string                   `json:"nextCursor,omitempty"`
	HasMore    bool                     `json:"hasMore"`
}

type ActivityQueryFacade interface {
	ListActivities(context.Context, ActivityPageQuery) (ActivityPage, error)
}

type ActivityQueryService struct {
	reader activityports.ActivityReader
}

func NewActivityQueryService(reader activityports.ActivityReader) *ActivityQueryService {
	if reader == nil {
		panic("ProfileInteractionActivity query requires reader")
	}
	return &ActivityQueryService{reader: reader}
}

func (s *ActivityQueryService) ListActivities(
	ctx context.Context,
	query ActivityPageQuery,
) (ActivityPage, error) {
	query.OwnerPersonaID = strings.TrimSpace(query.OwnerPersonaID)
	query.ViewerPersonaID = strings.TrimSpace(query.ViewerPersonaID)
	query.Direction = strings.TrimSpace(query.Direction)
	query.ActivityType = strings.TrimSpace(query.ActivityType)
	if query.OwnerPersonaID == "" {
		return ActivityPage{}, contentgenerated.AppErrorFromInvalidArgument(
			"profile interaction owner persona is required",
		)
	}
	if query.Direction != activitymodel.DirectionReceived &&
		query.Direction != activitymodel.DirectionSent {
		return ActivityPage{}, contentgenerated.AppErrorFromInteractionTypeInvalid(
			"profile interaction direction must be received or sent",
		)
	}
	if query.ActivityType != activitymodel.TypeLike &&
		query.ActivityType != activitymodel.TypeComment &&
		query.ActivityType != activitymodel.TypeShare {
		return ActivityPage{}, contentgenerated.AppErrorFromInteractionTypeInvalid(
			"profile interaction type must be like, comment, or share",
		)
	}
	if query.ActivityType == activitymodel.TypeShare &&
		query.ViewerPersonaID != query.OwnerPersonaID {
		return ActivityPage{}, contentgenerated.AppErrorFromInteractionOwnerForbidden(
			"profile share interaction is private to the active owner persona",
		)
	}
	limit := query.Limit
	if limit <= 0 {
		limit = 20
	}
	if limit > maxActivityPageSize {
		limit = maxActivityPageSize
	}
	cursor, err := decodeActivityCursor(query.Cursor)
	if err != nil {
		return ActivityPage{}, contentgenerated.AppErrorFromInteractionCursorInvalid(
			err.Error(),
		)
	}
	page, err := s.reader.List(ctx, activityports.PageRequest{
		OwnerPersonaID: query.OwnerPersonaID,
		Direction:      query.Direction,
		ActivityType:   query.ActivityType,
		Cursor:         cursor,
		Limit:          limit,
	})
	if err != nil {
		return ActivityPage{}, contentgenerated.AppErrorFromInteractionReadModelUnavailable(
			"list ProfileInteractionActivityView: " + err.Error(),
		)
	}
	nextCursor := ""
	if page.HasMore && len(page.Items) > 0 {
		last := page.Items[len(page.Items)-1]
		nextCursor = encodeActivityCursor(last.OccurredAt, last.ActivityID)
	}
	return ActivityPage{
		Items:      page.Items,
		NextCursor: nextCursor,
		HasMore:    page.HasMore,
	}, nil
}

func encodeActivityCursor(occurredAt time.Time, activityID string) string {
	raw := fmt.Sprintf("%d|%s", occurredAt.UTC().UnixNano(), strings.TrimSpace(activityID))
	return base64.RawURLEncoding.EncodeToString([]byte(raw))
}

func decodeActivityCursor(raw string) (activityports.Cursor, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return activityports.Cursor{}, nil
	}
	if len(raw) > 2048 {
		return activityports.Cursor{}, fmt.Errorf("profile interaction cursor exceeds maximum length")
	}
	decoded, err := base64.RawURLEncoding.DecodeString(raw)
	if err != nil {
		return activityports.Cursor{}, fmt.Errorf("profile interaction cursor is malformed")
	}
	timePart, activityID, found := strings.Cut(string(decoded), "|")
	if !found || strings.TrimSpace(activityID) == "" {
		return activityports.Cursor{}, fmt.Errorf("profile interaction cursor has invalid shape")
	}
	nanos, err := strconv.ParseInt(timePart, 10, 64)
	if err != nil || nanos <= 0 {
		return activityports.Cursor{}, fmt.Errorf("profile interaction cursor has invalid timestamp")
	}
	return activityports.Cursor{
		OccurredAt: time.Unix(0, nanos).UTC(),
		ActivityID: strings.TrimSpace(activityID),
	}, nil
}
