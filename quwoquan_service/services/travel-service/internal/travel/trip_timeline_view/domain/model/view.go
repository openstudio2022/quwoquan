package model

import (
	"errors"
	"sort"
	"strings"
	"time"

	momentmodel "quwoquan_service/services/travel-service/internal/travel/trip_moment/domain/model"
	planmodel "quwoquan_service/services/travel-service/internal/travel/trip_plan/domain/model"
	linkmodel "quwoquan_service/services/travel-service/internal/travel/trip_plan_content_link/domain/model"
	revisionmodel "quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/domain/model"
)

var ErrInvalidView = errors.New("invalid trip timeline view")

type PlaceRef struct {
	ObjectTypeRef string `json:"objectTypeRef" bson:"objectTypeRef"`
	ObjectID      string `json:"objectId" bson:"objectId"`
}

type ContentRef struct {
	ObjectTypeRef string `json:"objectTypeRef" bson:"objectTypeRef"`
	ObjectID      string `json:"objectId" bson:"objectId"`
}

type MomentSlice struct {
	MomentID             string                 `json:"momentId" bson:"momentId"`
	Kind                 momentmodel.Kind       `json:"kind" bson:"kind"`
	ContentRef           *ContentRef            `json:"contentRef,omitempty" bson:"contentRef,omitempty"`
	InlineText           string                 `json:"inlineText,omitempty" bson:"inlineText,omitempty"`
	CapturedAt           time.Time              `json:"capturedAt" bson:"capturedAt"`
	CoarsePlaceRef       *PlaceRef              `json:"coarsePlaceRef,omitempty" bson:"coarsePlaceRef,omitempty"`
	Visibility           momentmodel.Visibility `json:"visibility" bson:"visibility"`
	AttributionPersonaID string                 `json:"attributionPersonaId" bson:"attributionPersonaId"`
}

type ContentLinkSlice struct {
	LinkID            string               `json:"linkId" bson:"linkId"`
	PostID            string               `json:"postId" bson:"postId"`
	Visibility        linkmodel.Visibility `json:"visibility" bson:"visibility"`
	LinkedByPersonaID string               `json:"linkedByPersonaId" bson:"linkedByPersonaId"`
}

type ItemSlice struct {
	ItemID       string             `json:"itemId" bson:"itemId"`
	OrderInDay   int                `json:"orderInDay" bson:"orderInDay"`
	Kind         string             `json:"kind" bson:"kind"`
	Title        string             `json:"title" bson:"title"`
	StartAt      *time.Time         `json:"startAt,omitempty" bson:"startAt,omitempty"`
	EndAt        *time.Time         `json:"endAt,omitempty" bson:"endAt,omitempty"`
	PlaceRef     *PlaceRef          `json:"placeRef,omitempty" bson:"placeRef,omitempty"`
	Note         string             `json:"note,omitempty" bson:"note,omitempty"`
	Moments      []MomentSlice      `json:"moments" bson:"moments"`
	ContentLinks []ContentLinkSlice `json:"contentLinks" bson:"contentLinks"`
}

type DaySlice struct {
	DayIndex               int                `json:"dayIndex" bson:"dayIndex"`
	UnassignedMoments      []MomentSlice      `json:"unassignedMoments" bson:"unassignedMoments"`
	UnassignedContentLinks []ContentLinkSlice `json:"unassignedContentLinks" bson:"unassignedContentLinks"`
	Items                  []ItemSlice        `json:"items" bson:"items"`
}

type View struct {
	TripID                string                 `json:"tripId" bson:"_id"`
	TripVersion           int64                  `json:"tripVersion" bson:"tripVersion"`
	TripStatus            planmodel.Status       `json:"tripStatus" bson:"tripStatus"`
	CurrentRevisionID     string                 `json:"currentRevisionId" bson:"currentRevisionId"`
	CurrentRevisionNumber int64                  `json:"currentRevisionNumber" bson:"currentRevisionNumber"`
	RevisionChangeReason  string                 `json:"revisionChangeReason" bson:"revisionChangeReason"`
	RevisionSeverity      revisionmodel.Severity `json:"revisionSeverity" bson:"revisionSeverity"`
	TripContentLinks      []ContentLinkSlice     `json:"tripContentLinks" bson:"tripContentLinks"`
	Days                  []DaySlice             `json:"days" bson:"days"`
	SourceMomentIDs       []string               `json:"sourceMomentIds" bson:"sourceMomentIds"`
	SourceContentLinkIDs  []string               `json:"sourceContentLinkIds" bson:"sourceContentLinkIds"`
	SourceDigest          string                 `json:"sourceDigest" bson:"sourceDigest"`
	SourceEventID         string                 `json:"sourceEventId" bson:"sourceEventId"`
	ProjectedAt           time.Time              `json:"projectedAt" bson:"projectedAt"`
}

func (view View) Validate() error {
	if strings.TrimSpace(view.TripID) == "" || view.TripVersion <= 0 ||
		strings.TrimSpace(string(view.TripStatus)) == "" || strings.TrimSpace(view.CurrentRevisionID) == "" ||
		view.CurrentRevisionNumber <= 0 || strings.TrimSpace(view.RevisionChangeReason) == "" ||
		!view.RevisionSeverity.Valid() || strings.TrimSpace(view.SourceDigest) == "" ||
		strings.TrimSpace(view.SourceEventID) == "" || view.ProjectedAt.IsZero() ||
		view.TripContentLinks == nil || view.Days == nil || view.SourceMomentIDs == nil || view.SourceContentLinkIDs == nil {
		return ErrInvalidView
	}
	lastDay := -1
	seenItems := map[string]bool{}
	for _, day := range view.Days {
		if day.DayIndex < 0 || day.DayIndex <= lastDay || day.Items == nil ||
			day.UnassignedMoments == nil || day.UnassignedContentLinks == nil {
			return ErrInvalidView
		}
		lastDay = day.DayIndex
		lastOrder := -1
		for _, item := range day.Items {
			if strings.TrimSpace(item.ItemID) == "" || seenItems[item.ItemID] || item.OrderInDay <= lastOrder ||
				strings.TrimSpace(item.Kind) == "" || strings.TrimSpace(item.Title) == "" ||
				item.Moments == nil || item.ContentLinks == nil {
				return ErrInvalidView
			}
			seenItems[item.ItemID] = true
			lastOrder = item.OrderInDay
		}
	}
	return nil
}

func SortReferences(view *View) {
	if view == nil {
		return
	}
	sort.Strings(view.SourceMomentIDs)
	sort.Strings(view.SourceContentLinkIDs)
	sort.Slice(view.TripContentLinks, func(i, j int) bool {
		return view.TripContentLinks[i].LinkID < view.TripContentLinks[j].LinkID
	})
	for dayIndex := range view.Days {
		day := &view.Days[dayIndex]
		sort.Slice(day.UnassignedMoments, func(i, j int) bool {
			if !day.UnassignedMoments[i].CapturedAt.Equal(day.UnassignedMoments[j].CapturedAt) {
				return day.UnassignedMoments[i].CapturedAt.Before(day.UnassignedMoments[j].CapturedAt)
			}
			return day.UnassignedMoments[i].MomentID < day.UnassignedMoments[j].MomentID
		})
		sort.Slice(day.UnassignedContentLinks, func(i, j int) bool {
			return day.UnassignedContentLinks[i].LinkID < day.UnassignedContentLinks[j].LinkID
		})
		for itemIndex := range day.Items {
			item := &day.Items[itemIndex]
			sort.Slice(item.Moments, func(i, j int) bool {
				if !item.Moments[i].CapturedAt.Equal(item.Moments[j].CapturedAt) {
					return item.Moments[i].CapturedAt.Before(item.Moments[j].CapturedAt)
				}
				return item.Moments[i].MomentID < item.Moments[j].MomentID
			})
			sort.Slice(item.ContentLinks, func(i, j int) bool {
				return item.ContentLinks[i].LinkID < item.ContentLinks[j].LinkID
			})
		}
	}
}
