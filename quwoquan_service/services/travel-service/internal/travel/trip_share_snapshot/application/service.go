package application

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"strings"
	"time"

	linkmodel "quwoquan_service/services/travel-service/internal/travel/trip_plan_content_link/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_share_snapshot/domain/model"
	"quwoquan_service/services/travel-service/internal/travel/trip_share_snapshot/domain/ports"
	timelinemodel "quwoquan_service/services/travel-service/internal/travel/trip_timeline_view/domain/model"
)

type Service struct {
	store  ports.Store
	source ports.SourceReader
	ids    ports.IDGenerator
	now    func() time.Time
}

func NewService(store ports.Store, source ports.SourceReader, ids ports.IDGenerator, now func() time.Time) *Service {
	if now == nil {
		now = func() time.Time { return time.Now().UTC() }
	}
	return &Service{store: store, source: source, ids: ids, now: now}
}

type CreateCommand struct {
	ActorPersonaID   string
	IdempotencyKey   string
	TripID           string
	SourceRevisionID string
	SourceDigest     string
	Scope            model.Scope
	DayIndex         *int
	ItemID           string
	MomentIDs        []string
	Visibility       model.Visibility
}

func (service *Service) Create(ctx context.Context, command CreateCommand) (ports.CommandResult, error) {
	if service == nil || service.store == nil || service.source == nil || service.ids == nil ||
		strings.TrimSpace(command.ActorPersonaID) == "" || strings.TrimSpace(command.IdempotencyKey) == "" ||
		strings.TrimSpace(command.TripID) == "" || strings.TrimSpace(command.SourceRevisionID) == "" ||
		strings.TrimSpace(command.SourceDigest) == "" || !command.Scope.Valid() || !command.Visibility.Valid() {
		return ports.CommandResult{}, model.ErrInvalidArgument
	}
	momentIDs, valid := model.NormalizeMomentIDs(command.MomentIDs)
	if !valid || !validCommandScope(command, momentIDs) {
		return ports.CommandResult{}, model.ErrInvalidArgument
	}
	command.MomentIDs = momentIDs
	digest := commandDigest(command)
	if result, handled, err := service.replay(ctx, command.IdempotencyKey, digest); handled || err != nil {
		return result, err
	}
	source, err := service.source.ReadShareSource(ctx, command.ActorPersonaID, command.TripID)
	if err != nil {
		return ports.CommandResult{}, err
	}
	if source.Timeline.CurrentRevisionID != command.SourceRevisionID ||
		source.Timeline.SourceDigest != command.SourceDigest ||
		source.Map.CurrentRevisionID != command.SourceRevisionID ||
		source.Map.SourceDigest != command.SourceDigest {
		return ports.CommandResult{}, model.ErrSourceConflict
	}
	snapshotID, err := service.ids.NewTripShareSnapshotID()
	if err != nil {
		return ports.CommandResult{}, err
	}
	snapshot, err := buildSnapshot(snapshotID, command, source, service.now().UTC())
	if err != nil {
		return ports.CommandResult{}, err
	}
	eventID, err := service.ids.NewEventID()
	if err != nil {
		return ports.CommandResult{}, err
	}
	result := ports.CommandResult{Snapshot: snapshot}
	commit := ports.Commit{
		Snapshot: snapshot,
		Receipt: ports.Receipt{
			IdempotencyKey: command.IdempotencyKey, CommandDigest: digest, Result: result,
			ExpiresAt: snapshot.CreatedAt.Add(7 * 24 * time.Hour),
		},
		Event: ports.OutboxEvent{
			EventID: eventID, EventType: "TripShareSnapshotCreated",
			AggregateID: snapshot.SnapshotID, AggregateVersion: snapshot.Version,
			OccurredAt: snapshot.CreatedAt,
			Payload: map[string]any{
				"snapshotId": snapshot.SnapshotID, "tripId": snapshot.TripID,
				"sourceRevisionId":     snapshot.SourceRevisionID,
				"sourceRevisionNumber": snapshot.SourceRevisionNumber,
				"sourceDigest":         snapshot.SourceDigest, "scope": snapshot.Scope,
				"visibility": snapshot.Visibility, "privacyPolicyDigest": snapshot.PrivacyPolicyDigest,
				"createdByPersonaId": snapshot.CreatedByPersonaID, "createdAt": snapshot.CreatedAt,
			},
		},
	}
	if err := service.store.Commit(ctx, commit); err != nil {
		if errors.Is(err, ports.ErrCommitConflict) {
			if replay, handled, replayErr := service.replay(ctx, command.IdempotencyKey, digest); handled || replayErr != nil {
				return replay, replayErr
			}
		}
		return ports.CommandResult{}, err
	}
	return result, nil
}

func (service *Service) Get(ctx context.Context, actorPersonaID, snapshotID string) (model.Snapshot, error) {
	if service == nil || service.store == nil || strings.TrimSpace(snapshotID) == "" {
		return model.Snapshot{}, model.ErrInvalidArgument
	}
	snapshot, err := service.store.Get(ctx, strings.TrimSpace(snapshotID))
	if err != nil {
		return model.Snapshot{}, err
	}
	if snapshot.Visibility == model.VisibilityPublic {
		return snapshot, nil
	}
	if strings.TrimSpace(actorPersonaID) == "" || service.source == nil {
		return model.Snapshot{}, model.ErrInvalidArgument
	}
	if _, err := service.source.ReadShareSource(ctx, actorPersonaID, snapshot.TripID); err != nil {
		return model.Snapshot{}, err
	}
	return snapshot, nil
}

func (service *Service) replay(ctx context.Context, key, digest string) (ports.CommandResult, bool, error) {
	receipt, found, err := service.store.FindReceipt(ctx, strings.TrimSpace(key))
	if err != nil || !found {
		return ports.CommandResult{}, false, err
	}
	if receipt.CommandDigest != digest {
		return ports.CommandResult{}, true, ports.ErrIdempotencyConflict
	}
	result := receipt.Result
	result.IdempotentReplay = true
	return result, true, nil
}

func validCommandScope(command CreateCommand, momentIDs []string) bool {
	switch command.Scope {
	case model.ScopeFull, model.ScopeRoute:
		return command.DayIndex == nil && strings.TrimSpace(command.ItemID) == "" && len(momentIDs) == 0
	case model.ScopeDay:
		return command.DayIndex != nil && *command.DayIndex >= 0 && strings.TrimSpace(command.ItemID) == "" && len(momentIDs) == 0
	case model.ScopeItem:
		return command.DayIndex == nil && strings.TrimSpace(command.ItemID) != "" && len(momentIDs) == 0
	case model.ScopeMomentCollection:
		return command.DayIndex == nil && strings.TrimSpace(command.ItemID) == "" && len(momentIDs) > 0
	default:
		return false
	}
}

func buildSnapshot(id string, command CreateCommand, source ports.Source, now time.Time) (model.Snapshot, error) {
	selectedMoments := make(map[string]bool, len(command.MomentIDs))
	for _, momentID := range command.MomentIDs {
		selectedMoments[momentID] = true
	}
	selectedItems := map[string]bool{}
	items := make([]model.Item, 0)
	moments := make([]model.Moment, 0)
	links := make([]model.ContentLink, 0)
	if command.Scope == model.ScopeFull {
		for _, link := range source.Timeline.TripContentLinks {
			if shareableContentLink(command.Visibility, string(link.Visibility)) {
				links = append(links, model.ContentLink{LinkID: link.LinkID, PostID: link.PostID})
			}
		}
	}
	for _, day := range source.Timeline.Days {
		for _, item := range day.Items {
			includeItem := includesItem(command, day.DayIndex, item.ItemID)
			for _, moment := range item.Moments {
				if command.Scope == model.ScopeMomentCollection && selectedMoments[moment.MomentID] {
					includeItem = true
				}
			}
			if includeItem {
				selectedItems[item.ItemID] = true
				items = append(items, snapshotItem(command.Visibility, day.DayIndex, item))
			}
			for _, moment := range item.Moments {
				if includeMoment(command, day.DayIndex, item.ItemID, moment.MomentID) &&
					shareableMoment(command.Visibility, string(moment.Visibility)) {
					moments = append(moments, snapshotMoment(day.DayIndex, item.ItemID, moment))
				}
			}
			for _, link := range item.ContentLinks {
				if includeItem && shareableContentLink(command.Visibility, string(link.Visibility)) {
					links = append(links, model.ContentLink{
						LinkID: link.LinkID, PostID: link.PostID, DayIndex: intPointer(day.DayIndex), ItemID: item.ItemID,
					})
				}
			}
		}
		for _, moment := range day.UnassignedMoments {
			if includeMoment(command, day.DayIndex, "", moment.MomentID) &&
				shareableMoment(command.Visibility, string(moment.Visibility)) {
				moments = append(moments, snapshotMoment(day.DayIndex, "", moment))
			}
		}
		for _, link := range day.UnassignedContentLinks {
			if includesDay(command, day.DayIndex) && shareableContentLink(command.Visibility, string(link.Visibility)) {
				links = append(links, model.ContentLink{LinkID: link.LinkID, PostID: link.PostID, DayIndex: intPointer(day.DayIndex)})
			}
		}
	}
	routeStops := make([]model.RouteStop, 0)
	for _, stop := range source.Map.Stops {
		if !selectedItems[stop.ItemID] || command.Visibility == model.VisibilityPublic && isStay(items, stop.ItemID) {
			continue
		}
		routeStops = append(routeStops, model.RouteStop{
			DayIndex: stop.DayIndex, ItemID: stop.ItemID, Sequence: stop.Sequence, Title: stop.Title,
			PlaceRef: model.PlaceRef{ObjectTypeRef: stop.PlaceRef.ObjectTypeRef, ObjectID: stop.PlaceRef.ObjectID},
		})
	}
	if command.Scope == model.ScopeMomentCollection && len(moments) == 0 {
		return model.Snapshot{}, model.ErrInvalidArgument
	}
	snapshot := model.Snapshot{
		SnapshotID: id, Version: 1, TripID: command.TripID,
		SourceRevisionID:     command.SourceRevisionID,
		SourceRevisionNumber: source.Timeline.CurrentRevisionNumber,
		SourceDigest:         command.SourceDigest, Scope: command.Scope, DayIndex: command.DayIndex,
		ItemID: strings.TrimSpace(command.ItemID), MomentIDs: append(make([]string, 0, len(command.MomentIDs)), command.MomentIDs...),
		Visibility: command.Visibility, PrivacyPolicyDigest: model.PrivacyPolicyDigestV1,
		Items: items, Moments: moments, ContentLinks: links, RouteStops: routeStops,
		CreatedByPersonaID: command.ActorPersonaID, Status: "active", CreatedAt: now.UTC(),
	}
	if err := snapshot.Validate(); err != nil {
		return model.Snapshot{}, err
	}
	return snapshot, nil
}

func includesDay(command CreateCommand, dayIndex int) bool {
	return command.Scope == model.ScopeFull || command.Scope == model.ScopeRoute ||
		command.Scope == model.ScopeDay && command.DayIndex != nil && *command.DayIndex == dayIndex
}

func includesItem(command CreateCommand, dayIndex int, itemID string) bool {
	return includesDay(command, dayIndex) || command.Scope == model.ScopeItem && command.ItemID == itemID
}

func includeMoment(command CreateCommand, dayIndex int, itemID, momentID string) bool {
	return command.Scope != model.ScopeRoute && (includesItem(command, dayIndex, itemID) ||
		command.Scope == model.ScopeMomentCollection && contains(command.MomentIDs, momentID))
}

func shareableMoment(visibility model.Visibility, source string) bool {
	if visibility == model.VisibilityPublic {
		return source == "public"
	}
	return source == "public" || source == "trip_members"
}

func shareableContentLink(visibility model.Visibility, source string) bool {
	return visibility != model.VisibilityPublic || source == string(linkmodel.VisibilityPublic)
}

func snapshotItem(visibility model.Visibility, dayIndex int, item timelinemodel.ItemSlice) model.Item {
	result := model.Item{
		DayIndex: dayIndex, ItemID: item.ItemID, OrderInDay: item.OrderInDay,
		Kind: item.Kind, Title: item.Title,
	}
	if visibility == model.VisibilityPublic && strings.EqualFold(item.Kind, "stay") {
		result.Title = ""
		return result
	}
	if item.PlaceRef != nil {
		result.PlaceRef = &model.PlaceRef{
			ObjectTypeRef: item.PlaceRef.ObjectTypeRef, ObjectID: item.PlaceRef.ObjectID,
		}
	}
	return result
}

func snapshotMoment(dayIndex int, itemID string, moment timelinemodel.MomentSlice) model.Moment {
	result := model.Moment{
		MomentID: moment.MomentID, DayIndex: dayIndex, ItemID: itemID, Kind: string(moment.Kind),
	}
	if moment.ContentRef != nil {
		result.ContentObjectTypeRef = moment.ContentRef.ObjectTypeRef
		result.ContentObjectID = moment.ContentRef.ObjectID
	}
	return result
}

func isStay(items []model.Item, itemID string) bool {
	for _, item := range items {
		if item.ItemID == itemID {
			return strings.EqualFold(item.Kind, "stay")
		}
	}
	return false
}

func commandDigest(command CreateCommand) string {
	raw, _ := json.Marshal(command)
	digest := sha256.Sum256(raw)
	return "sha256:" + hex.EncodeToString(digest[:])
}

func contains(values []string, wanted string) bool {
	for _, value := range values {
		if value == wanted {
			return true
		}
	}
	return false
}

func intPointer(value int) *int {
	return &value
}
