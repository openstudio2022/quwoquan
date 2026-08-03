package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"time"

	mapmodel "quwoquan_service/services/travel-service/internal/travel/trip_map_view/domain/model"
	momentmodel "quwoquan_service/services/travel-service/internal/travel/trip_moment/domain/model"
	planmodel "quwoquan_service/services/travel-service/internal/travel/trip_plan/domain/model"
	linkmodel "quwoquan_service/services/travel-service/internal/travel/trip_plan_content_link/domain/model"
	revisionmodel "quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_timeline_view/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_timeline_view/domain/ports"
)

var allowedSourceEvents = map[string]bool{
	"travel.TripPlanCreated":            true,
	"travel.TripPlanRevised":            true,
	"travel.TripPlanLifecycleChanged":   true,
	"travel.TripPlanRevisionAppended":   true,
	"travel.TripMomentChanged":          true,
	"travel.TripPlanContentLinkChanged": true,
}

type SourceEvent struct {
	EventID   string
	EventType string
	TripID    string
}

type Projector struct {
	store     ports.Store
	plans     ports.PlanReader
	revisions ports.RevisionReader
	moments   ports.MomentReader
	links     ports.ContentLinkReader
	now       func() time.Time
}

func NewProjector(
	store ports.Store,
	plans ports.PlanReader,
	revisions ports.RevisionReader,
	moments ports.MomentReader,
	links ports.ContentLinkReader,
	now func() time.Time,
) *Projector {
	if now == nil {
		now = func() time.Time { return time.Now().UTC() }
	}
	return &Projector{
		store: store, plans: plans, revisions: revisions, moments: moments, links: links, now: now,
	}
}

func (projector *Projector) Apply(ctx context.Context, event SourceEvent) error {
	event.EventID = strings.TrimSpace(event.EventID)
	event.EventType = strings.TrimSpace(event.EventType)
	event.TripID = strings.TrimSpace(event.TripID)
	if projector == nil || projector.store == nil || projector.plans == nil ||
		projector.revisions == nil || projector.moments == nil || projector.links == nil ||
		event.EventID == "" || event.TripID == "" || !allowedSourceEvents[event.EventType] {
		return model.ErrInvalidView
	}
	if receipt, found, err := projector.store.FindReceipt(ctx, event.EventID); err != nil {
		return err
	} else if found {
		if receipt.TripID != event.TripID {
			return ports.ErrReceiptConflict
		}
		return nil
	}
	plan, err := projector.plans.GetPlan(ctx, event.TripID)
	if err != nil {
		return err
	}
	revision, err := projector.revisions.Get(ctx, event.TripID, plan.CurrentRevisionNumber)
	if err != nil {
		return err
	}
	if revision.RevisionID != plan.CurrentRevisionID || revision.TripID != plan.TripID {
		return ports.ErrProjectionUnavailable
	}
	moments, err := projector.moments.ListActive(ctx, event.TripID)
	if err != nil {
		return err
	}
	links, err := projector.links.ListActive(ctx, event.TripID)
	if err != nil {
		return err
	}
	sharedMoments := filterSharedMoments(moments)
	activeLinks := filterActiveLinks(links)
	digest := sourceDigest(plan, revision, sharedMoments, activeLinks)
	now := projector.now().UTC()
	timeline := buildTimeline(plan, revision, sharedMoments, activeLinks, event.EventID, digest, now)
	tripMap := buildMap(plan, revision, sharedMoments, activeLinks, event.EventID, digest, now)
	if err := timeline.Validate(); err != nil {
		return err
	}
	if err := tripMap.Validate(); err != nil || timeline.SourceDigest != tripMap.SourceDigest {
		if err != nil {
			return err
		}
		return ports.ErrProjectionUnavailable
	}
	return projector.store.CommitProjection(ctx, ports.ProjectionCommit{
		Timeline: timeline,
		Map:      tripMap,
		Receipt: ports.ProjectionReceipt{
			SourceEventID: event.EventID, TripID: event.TripID, SourceDigest: digest, AppliedAt: now,
		},
	})
}

type dayBuilder struct {
	day       model.DaySlice
	itemIndex map[string]int
}

func buildTimeline(
	plan planmodel.Plan,
	revision revisionmodel.Revision,
	moments []momentmodel.Moment,
	links []linkmodel.Link,
	eventID string,
	digest string,
	now time.Time,
) model.View {
	days := map[int]*dayBuilder{}
	ensureDay := func(dayIndex int) *dayBuilder {
		if day, found := days[dayIndex]; found {
			return day
		}
		day := &dayBuilder{
			day: model.DaySlice{
				DayIndex: dayIndex, UnassignedMoments: []model.MomentSlice{},
				UnassignedContentLinks: []model.ContentLinkSlice{}, Items: []model.ItemSlice{},
			},
			itemIndex: map[string]int{},
		}
		days[dayIndex] = day
		return day
	}
	for _, item := range revision.Items {
		day := ensureDay(item.DayIndex)
		day.itemIndex[item.ItemID] = len(day.day.Items)
		day.day.Items = append(day.day.Items, model.ItemSlice{
			ItemID: item.ItemID, OrderInDay: item.OrderInDay, Kind: item.Kind, Title: item.Title,
			StartAt: cloneTime(item.StartAt), EndAt: cloneTime(item.EndAt),
			PlaceRef: timelinePlaceRef(item.PlaceRef), Note: item.Note,
			Moments: []model.MomentSlice{}, ContentLinks: []model.ContentLinkSlice{},
		})
	}
	sourceMomentIDs := make([]string, 0, len(moments))
	for _, moment := range moments {
		sourceMomentIDs = append(sourceMomentIDs, moment.MomentID)
		if moment.DayIndex == nil {
			continue
		}
		day := ensureDay(*moment.DayIndex)
		slice := timelineMoment(moment)
		if itemIndex, found := day.itemIndex[moment.ItemID]; found && moment.ItemID != "" {
			day.day.Items[itemIndex].Moments = append(day.day.Items[itemIndex].Moments, slice)
		} else {
			day.day.UnassignedMoments = append(day.day.UnassignedMoments, slice)
		}
	}
	sourceLinkIDs := make([]string, 0, len(links))
	tripContentLinks := make([]model.ContentLinkSlice, 0)
	for _, link := range links {
		sourceLinkIDs = append(sourceLinkIDs, link.LinkID)
		slice := model.ContentLinkSlice{
			LinkID: link.LinkID, PostID: link.PostID,
			Visibility: link.Visibility, LinkedByPersonaID: link.LinkedByPersonaID,
		}
		if link.TargetKind == linkmodel.TargetTrip || link.DayIndex == nil {
			tripContentLinks = append(tripContentLinks, slice)
			continue
		}
		day := ensureDay(*link.DayIndex)
		if itemIndex, found := day.itemIndex[link.ItemID]; found && link.ItemID != "" {
			day.day.Items[itemIndex].ContentLinks = append(day.day.Items[itemIndex].ContentLinks, slice)
		} else {
			day.day.UnassignedContentLinks = append(day.day.UnassignedContentLinks, slice)
		}
	}
	dayKeys := make([]int, 0, len(days))
	for dayIndex := range days {
		dayKeys = append(dayKeys, dayIndex)
	}
	sort.Ints(dayKeys)
	daySlices := make([]model.DaySlice, 0, len(dayKeys))
	for _, dayIndex := range dayKeys {
		daySlices = append(daySlices, days[dayIndex].day)
	}
	view := model.View{
		TripID: plan.TripID, TripVersion: plan.Version, TripStatus: plan.Status,
		CurrentRevisionID: revision.RevisionID, CurrentRevisionNumber: revision.RevisionNumber,
		RevisionChangeReason: revision.ChangeReason, RevisionSeverity: revision.Severity,
		TripContentLinks: tripContentLinks, Days: daySlices,
		SourceMomentIDs: sourceMomentIDs, SourceContentLinkIDs: sourceLinkIDs,
		SourceDigest: digest, SourceEventID: eventID, ProjectedAt: now,
	}
	model.SortReferences(&view)
	return view
}

func buildMap(
	plan planmodel.Plan,
	revision revisionmodel.Revision,
	moments []momentmodel.Moment,
	links []linkmodel.Link,
	eventID string,
	digest string,
	now time.Time,
) mapmodel.View {
	momentsByItem := map[string][]string{}
	linksByItem := map[string][]string{}
	sourceMomentIDs := make([]string, 0, len(moments))
	sourceLinkIDs := make([]string, 0, len(links))
	markers := make([]mapmodel.MomentMarker, 0)
	for _, moment := range moments {
		sourceMomentIDs = append(sourceMomentIDs, moment.MomentID)
		if moment.ItemID != "" {
			momentsByItem[moment.ItemID] = append(momentsByItem[moment.ItemID], moment.MomentID)
		}
		if moment.DayIndex != nil && moment.CoarsePlaceRef != nil {
			markers = append(markers, mapmodel.MomentMarker{
				MomentID: moment.MomentID, DayIndex: *moment.DayIndex, ItemID: moment.ItemID,
				PlaceRef: mapmodel.PlaceRef{
					ObjectTypeRef: moment.CoarsePlaceRef.ObjectTypeRef,
					ObjectID:      moment.CoarsePlaceRef.ObjectID,
				},
			})
		}
	}
	for _, link := range links {
		sourceLinkIDs = append(sourceLinkIDs, link.LinkID)
		if link.ItemID != "" {
			linksByItem[link.ItemID] = append(linksByItem[link.ItemID], link.LinkID)
		}
	}
	stops := make([]mapmodel.Stop, 0)
	for _, item := range revision.Items {
		if item.PlaceRef == nil {
			continue
		}
		stop := mapmodel.Stop{
			StopID: fmt.Sprintf("stop:%s", item.ItemID), Sequence: len(stops),
			DayIndex: item.DayIndex, ItemID: item.ItemID, Title: item.Title,
			PlaceRef: mapmodel.PlaceRef{
				ObjectTypeRef: item.PlaceRef.ObjectTypeRef, ObjectID: item.PlaceRef.ObjectID,
			},
			MomentIDs:      append([]string{}, momentsByItem[item.ItemID]...),
			ContentLinkIDs: append([]string{}, linksByItem[item.ItemID]...),
		}
		sort.Strings(stop.MomentIDs)
		sort.Strings(stop.ContentLinkIDs)
		stops = append(stops, stop)
	}
	segments := make([]mapmodel.RouteSegment, 0, max(0, len(stops)-1))
	for index := 1; index < len(stops); index++ {
		segments = append(segments, mapmodel.RouteSegment{
			SegmentID: fmt.Sprintf("segment:%s:%s", stops[index-1].ItemID, stops[index].ItemID),
			Sequence:  len(segments), FromStopID: stops[index-1].StopID, ToStopID: stops[index].StopID,
		})
	}
	sort.Strings(sourceMomentIDs)
	sort.Strings(sourceLinkIDs)
	sort.Slice(markers, func(i, j int) bool {
		if markers[i].DayIndex != markers[j].DayIndex {
			return markers[i].DayIndex < markers[j].DayIndex
		}
		return markers[i].MomentID < markers[j].MomentID
	})
	return mapmodel.View{
		TripID: plan.TripID, CurrentRevisionID: revision.RevisionID,
		CurrentRevisionNumber: revision.RevisionNumber, Stops: stops, RouteSegments: segments,
		MomentMarkers: markers, SourceMomentIDs: sourceMomentIDs, SourceContentLinkIDs: sourceLinkIDs,
		SourceDigest: digest, SourceEventID: eventID, ProjectedAt: now,
	}
}

func filterSharedMoments(values []momentmodel.Moment) []momentmodel.Moment {
	result := make([]momentmodel.Moment, 0, len(values))
	for _, moment := range values {
		if moment.Status != momentmodel.StatusActive ||
			moment.AssignmentStatus != momentmodel.AssignmentConfirmed ||
			moment.Visibility == momentmodel.VisibilityPersonal {
			continue
		}
		result = append(result, moment)
	}
	sort.Slice(result, func(i, j int) bool { return result[i].MomentID < result[j].MomentID })
	return result
}

func filterActiveLinks(values []linkmodel.Link) []linkmodel.Link {
	result := make([]linkmodel.Link, 0, len(values))
	for _, link := range values {
		if link.Status == linkmodel.StatusActive {
			result = append(result, link)
		}
	}
	sort.Slice(result, func(i, j int) bool { return result[i].LinkID < result[j].LinkID })
	return result
}

func sourceDigest(
	plan planmodel.Plan,
	revision revisionmodel.Revision,
	moments []momentmodel.Moment,
	links []linkmodel.Link,
) string {
	type sourceVersion struct {
		ID      string `json:"id"`
		Version int64  `json:"version"`
	}
	payload := struct {
		TripID         string           `json:"tripId"`
		TripVersion    int64            `json:"tripVersion"`
		TripStatus     planmodel.Status `json:"tripStatus"`
		RevisionID     string           `json:"revisionId"`
		RevisionNumber int64            `json:"revisionNumber"`
		Moments        []sourceVersion  `json:"moments"`
		Links          []sourceVersion  `json:"links"`
	}{
		TripID: plan.TripID, TripVersion: plan.Version, TripStatus: plan.Status,
		RevisionID: revision.RevisionID, RevisionNumber: revision.RevisionNumber,
		Moments: make([]sourceVersion, 0, len(moments)), Links: make([]sourceVersion, 0, len(links)),
	}
	for _, moment := range moments {
		payload.Moments = append(payload.Moments, sourceVersion{ID: moment.MomentID, Version: moment.Version})
	}
	for _, link := range links {
		payload.Links = append(payload.Links, sourceVersion{ID: link.LinkID, Version: link.Version})
	}
	raw, _ := json.Marshal(payload)
	digest := sha256.Sum256(raw)
	return "sha256:" + hex.EncodeToString(digest[:])
}

func timelineMoment(moment momentmodel.Moment) model.MomentSlice {
	return model.MomentSlice{
		MomentID: moment.MomentID, Kind: moment.Kind, ContentRef: timelineContentRef(moment.ContentRef),
		InlineText: moment.InlineText, CapturedAt: moment.CapturedAt,
		CoarsePlaceRef: timelineMomentPlaceRef(moment.CoarsePlaceRef), Visibility: moment.Visibility,
		AttributionPersonaID: moment.AttributionPersonaID,
	}
}

func timelinePlaceRef(ref *revisionmodel.PlaceRef) *model.PlaceRef {
	if ref == nil {
		return nil
	}
	return &model.PlaceRef{ObjectTypeRef: ref.ObjectTypeRef, ObjectID: ref.ObjectID}
}

func timelineMomentPlaceRef(ref *momentmodel.ObjectRef) *model.PlaceRef {
	if ref == nil {
		return nil
	}
	return &model.PlaceRef{ObjectTypeRef: ref.ObjectTypeRef, ObjectID: ref.ObjectID}
}

func timelineContentRef(ref *momentmodel.ObjectRef) *model.ContentRef {
	if ref == nil {
		return nil
	}
	return &model.ContentRef{ObjectTypeRef: ref.ObjectTypeRef, ObjectID: ref.ObjectID}
}

func cloneTime(value *time.Time) *time.Time {
	if value == nil {
		return nil
	}
	copyOfTime := value.UTC()
	return &copyOfTime
}

func max(left, right int) int {
	if left > right {
		return left
	}
	return right
}
