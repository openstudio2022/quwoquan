package model

import (
	"errors"
	"sort"
	"strings"
	"time"

	revisionmodel "quwoquan_service/services/travel-service/internal/travel/trip_plan_revision/domain/model"
)

var (
	ErrInvalidInput      = errors.New("invalid trip input")
	ErrPermissionDenied  = errors.New("trip permission denied")
	ErrRevisionConflict  = errors.New("trip revision conflict")
	ErrInvalidTransition = errors.New("invalid trip state transition")
)

type Status string

const (
	StatusPlanning  Status = "planning"
	StatusActive    Status = "active"
	StatusCompleted Status = "completed"
	StatusArchived  Status = "archived"
)

type ItemKind string
type SourceAttributionKind string

const (
	ItemStay      ItemKind = "stay"
	ItemFood      ItemKind = "food"
	ItemSight     ItemKind = "sight"
	ItemActivity  ItemKind = "activity"
	ItemTransport ItemKind = "transport"
	ItemRest      ItemKind = "rest"
	ItemFreeTime  ItemKind = "free_time"

	SourceAttributionPublicSource           SourceAttributionKind = "public_source"
	SourceAttributionProfessionalCommentary SourceAttributionKind = "professional_commentary"
)

type PlaceRef struct {
	ObjectTypeRef string `json:"objectTypeRef" bson:"objectTypeRef"`
	ObjectID      string `json:"objectId" bson:"objectId"`
}

type Item struct {
	ItemID     string     `json:"itemId" bson:"itemId"`
	DayIndex   int        `json:"dayIndex" bson:"dayIndex"`
	OrderInDay int        `json:"orderInDay" bson:"orderInDay"`
	Kind       ItemKind   `json:"kind" bson:"kind"`
	Title      string     `json:"title" bson:"title"`
	StartAt    *time.Time `json:"startAt,omitempty" bson:"startAt,omitempty"`
	EndAt      *time.Time `json:"endAt,omitempty" bson:"endAt,omitempty"`
	PlaceRef   *PlaceRef  `json:"placeRef,omitempty" bson:"placeRef,omitempty"`
	Note       string     `json:"note,omitempty" bson:"note,omitempty"`
}

type SourceAttribution struct {
	AttributionID   string                `json:"attributionId" bson:"attributionId"`
	Kind            SourceAttributionKind `json:"kind" bson:"kind"`
	PostID          string                `json:"postId" bson:"postId"`
	AuthorPersonaID string                `json:"authorPersonaId,omitempty" bson:"authorPersonaId,omitempty"`
	Title           string                `json:"title" bson:"title"`
}

type Plan struct {
	TripID                      string              `json:"id" bson:"_id"`
	Version                     int64               `json:"version" bson:"version"`
	OrganizerPersonaID          string              `json:"organizerPersonaId" bson:"organizerPersonaId"`
	Title                       string              `json:"title" bson:"title"`
	Status                      Status              `json:"status" bson:"status"`
	StartAt                     *time.Time          `json:"startAt,omitempty" bson:"startAt,omitempty"`
	EndAt                       *time.Time          `json:"endAt,omitempty" bson:"endAt,omitempty"`
	SourceTemplateID            string              `json:"sourceTemplateId,omitempty" bson:"sourceTemplateId,omitempty"`
	SourceTemplateVersion       int64               `json:"sourceTemplateVersion,omitempty" bson:"sourceTemplateVersion,omitempty"`
	SourceAttributionIDs        []string            `json:"sourceAttributionIds" bson:"sourceAttributionIds"`
	SourceAttributionPersonaIDs []string            `json:"sourceAttributionPersonaIds" bson:"sourceAttributionPersonaIds"`
	SourcePostIDs               []string            `json:"sourcePostIds" bson:"sourcePostIds"`
	SourceAttributions          []SourceAttribution `json:"sourceAttributions" bson:"sourceAttributions"`
	CurrentRevisionID           string              `json:"currentRevisionId" bson:"currentRevisionId"`
	CurrentRevisionNumber       int64               `json:"currentRevisionNumber" bson:"currentRevisionNumber"`
	CurrentItemCount            int                 `json:"currentItemCount" bson:"currentItemCount"`
	CreatedAt                   time.Time           `json:"createdAt" bson:"createdAt"`
	UpdatedAt                   time.Time           `json:"updatedAt" bson:"updatedAt"`
}

type CreateInput struct {
	TripID                string
	RevisionID            string
	OrganizerPersonaID    string
	Title                 string
	StartAt               *time.Time
	EndAt                 *time.Time
	Items                 []Item
	SourceTemplateID      string
	SourceTemplateVersion int64
	SourceAttributions    []SourceAttribution
	Now                   time.Time
}

func Create(input CreateInput) (Plan, revisionmodel.Revision, error) {
	input.TripID = strings.TrimSpace(input.TripID)
	input.RevisionID = strings.TrimSpace(input.RevisionID)
	input.OrganizerPersonaID = strings.TrimSpace(input.OrganizerPersonaID)
	input.Title = strings.TrimSpace(input.Title)
	items, err := normalizeItems(input.Items)
	sourceAttributions, sourceAttributionIDs, sourcePersonaIDs, sourcePostIDs, sourceErr := normalizeSourceAttributions(input.SourceAttributions)
	input.SourceTemplateID = strings.TrimSpace(input.SourceTemplateID)
	if input.TripID == "" || input.RevisionID == "" || input.OrganizerPersonaID == "" ||
		input.Title == "" || input.Now.IsZero() || invalidRange(input.StartAt, input.EndAt) || err != nil || sourceErr != nil ||
		(input.SourceTemplateID == "") != (input.SourceTemplateVersion == 0) ||
		input.SourceTemplateVersion < 0 || input.SourceTemplateID == "" && len(sourceAttributions) != 0 {
		return Plan{}, revisionmodel.Revision{}, ErrInvalidInput
	}
	plan := Plan{
		TripID:                      input.TripID,
		Version:                     1,
		OrganizerPersonaID:          input.OrganizerPersonaID,
		Title:                       input.Title,
		Status:                      StatusPlanning,
		StartAt:                     cloneTime(input.StartAt),
		EndAt:                       cloneTime(input.EndAt),
		SourceTemplateID:            input.SourceTemplateID,
		SourceTemplateVersion:       input.SourceTemplateVersion,
		SourceAttributionIDs:        sourceAttributionIDs,
		SourceAttributionPersonaIDs: sourcePersonaIDs,
		SourcePostIDs:               sourcePostIDs,
		SourceAttributions:          sourceAttributions,
		CurrentRevisionID:           input.RevisionID,
		CurrentRevisionNumber:       1,
		CurrentItemCount:            len(items),
		CreatedAt:                   input.Now.UTC(),
		UpdatedAt:                   input.Now.UTC(),
	}
	revisionItems := itemSnapshots(items)
	revision, err := revisionmodel.Create(revisionmodel.CreateInput{
		RevisionID:         input.RevisionID,
		TripID:             input.TripID,
		RevisionNumber:     1,
		ChangeReason:       "initial_plan",
		Severity:           revisionmodel.SeverityImportant,
		Items:              revisionItems,
		Changes:            revisionmodel.InitialChanges(revisionItems),
		AffectedPersonaIDs: []string{input.OrganizerPersonaID},
		CreatedByPersonaID: input.OrganizerPersonaID,
		CreatedAt:          input.Now.UTC(),
	})
	if err != nil {
		return Plan{}, revisionmodel.Revision{}, ErrInvalidInput
	}
	return plan, revision, nil
}

func normalizeSourceAttributions(values []SourceAttribution) ([]SourceAttribution, []string, []string, []string, error) {
	if values == nil {
		values = []SourceAttribution{}
	}
	if len(values) > 256 {
		return nil, nil, nil, nil, ErrInvalidInput
	}
	result := make([]SourceAttribution, 0, len(values))
	attributionIDs := make([]string, 0, len(values))
	personaSet := map[string]bool{}
	postSet := map[string]bool{}
	seen := map[string]bool{}
	for _, value := range values {
		value.AttributionID = strings.TrimSpace(value.AttributionID)
		value.PostID = strings.TrimSpace(value.PostID)
		value.AuthorPersonaID = strings.TrimSpace(value.AuthorPersonaID)
		value.Title = strings.TrimSpace(value.Title)
		if value.AttributionID == "" || seen[value.AttributionID] || value.PostID == "" || value.Title == "" ||
			(value.Kind != SourceAttributionPublicSource && value.Kind != SourceAttributionProfessionalCommentary) ||
			value.Kind == SourceAttributionProfessionalCommentary && value.AuthorPersonaID == "" {
			return nil, nil, nil, nil, ErrInvalidInput
		}
		seen[value.AttributionID] = true
		attributionIDs = append(attributionIDs, value.AttributionID)
		postSet[value.PostID] = true
		if value.AuthorPersonaID != "" {
			personaSet[value.AuthorPersonaID] = true
		}
		result = append(result, value)
	}
	personas := sortedSet(personaSet)
	posts := sortedSet(postSet)
	sort.Slice(result, func(i, j int) bool { return result[i].AttributionID < result[j].AttributionID })
	sort.Strings(attributionIDs)
	return result, attributionIDs, personas, posts, nil
}

func sortedSet(values map[string]bool) []string {
	result := make([]string, 0, len(values))
	for value := range values {
		result = append(result, value)
	}
	sort.Strings(result)
	return result
}

func (plan Plan) Revise(
	actorPersonaID string,
	expectedRevisionNumber int64,
	revisionID string,
	reason string,
	severity revisionmodel.Severity,
	previousItems []revisionmodel.ItemSnapshot,
	nextItems []Item,
	affectedPersonaIDs []string,
	now time.Time,
) (Plan, revisionmodel.Revision, error) {
	if strings.TrimSpace(actorPersonaID) != plan.OrganizerPersonaID {
		return Plan{}, revisionmodel.Revision{}, ErrPermissionDenied
	}
	if expectedRevisionNumber != plan.CurrentRevisionNumber {
		return Plan{}, revisionmodel.Revision{}, ErrRevisionConflict
	}
	if plan.Status == StatusArchived || strings.TrimSpace(reason) == "" ||
		strings.TrimSpace(revisionID) == "" || !severity.Valid() || now.IsZero() {
		return Plan{}, revisionmodel.Revision{}, ErrInvalidInput
	}
	next, err := normalizeItems(nextItems)
	if err != nil {
		return Plan{}, revisionmodel.Revision{}, ErrInvalidInput
	}
	nextSnapshots := itemSnapshots(next)
	changes := revisionmodel.DiffItems(previousItems, nextSnapshots)
	if len(changes) == 0 {
		return Plan{}, revisionmodel.Revision{}, ErrInvalidInput
	}
	affected := normalizedIDs(affectedPersonaIDs)
	if len(affected) == 0 {
		affected = []string{plan.OrganizerPersonaID}
	}
	revision, err := revisionmodel.Create(revisionmodel.CreateInput{
		RevisionID:         strings.TrimSpace(revisionID),
		TripID:             plan.TripID,
		RevisionNumber:     plan.CurrentRevisionNumber + 1,
		PreviousRevisionID: plan.CurrentRevisionID,
		ChangeReason:       strings.TrimSpace(reason),
		Severity:           severity,
		Items:              nextSnapshots,
		Changes:            changes,
		AffectedPersonaIDs: affected,
		CreatedByPersonaID: strings.TrimSpace(actorPersonaID),
		CreatedAt:          now.UTC(),
	})
	if err != nil {
		return Plan{}, revisionmodel.Revision{}, ErrInvalidInput
	}
	nextPlan := plan
	nextPlan.Version++
	nextPlan.CurrentRevisionID = revision.RevisionID
	nextPlan.CurrentRevisionNumber = revision.RevisionNumber
	nextPlan.CurrentItemCount = len(nextSnapshots)
	nextPlan.UpdatedAt = now.UTC()
	return nextPlan, revision, nil
}

func (plan Plan) Transition(
	actorPersonaID string,
	expectedRevisionNumber int64,
	revisionID string,
	target Status,
	items []revisionmodel.ItemSnapshot,
	now time.Time,
) (Plan, revisionmodel.Revision, error) {
	if strings.TrimSpace(actorPersonaID) != plan.OrganizerPersonaID {
		return Plan{}, revisionmodel.Revision{}, ErrPermissionDenied
	}
	if expectedRevisionNumber != plan.CurrentRevisionNumber {
		return Plan{}, revisionmodel.Revision{}, ErrRevisionConflict
	}
	if !canTransition(plan.Status, target) {
		return Plan{}, revisionmodel.Revision{}, ErrInvalidTransition
	}
	if strings.TrimSpace(revisionID) == "" || now.IsZero() {
		return Plan{}, revisionmodel.Revision{}, ErrInvalidInput
	}
	revision, err := revisionmodel.Create(revisionmodel.CreateInput{
		RevisionID:         strings.TrimSpace(revisionID),
		TripID:             plan.TripID,
		RevisionNumber:     plan.CurrentRevisionNumber + 1,
		PreviousRevisionID: plan.CurrentRevisionID,
		ChangeReason:       "lifecycle_transition",
		Severity:           revisionmodel.SeverityImportant,
		Items:              items,
		Changes:            []revisionmodel.Change{revisionmodel.LifecycleChange(string(plan.Status), string(target))},
		AffectedPersonaIDs: []string{plan.OrganizerPersonaID},
		CreatedByPersonaID: plan.OrganizerPersonaID,
		CreatedAt:          now.UTC(),
	})
	if err != nil {
		return Plan{}, revisionmodel.Revision{}, ErrInvalidInput
	}
	nextPlan := plan
	nextPlan.Version++
	nextPlan.Status = target
	nextPlan.CurrentRevisionID = revision.RevisionID
	nextPlan.CurrentRevisionNumber = revision.RevisionNumber
	nextPlan.UpdatedAt = now.UTC()
	return nextPlan, revision, nil
}

func normalizeItems(items []Item) ([]Item, error) {
	if len(items) > 512 {
		return nil, ErrInvalidInput
	}
	seenIDs := map[string]bool{}
	seenOrder := map[[2]int]bool{}
	result := make([]Item, 0, len(items))
	for _, item := range items {
		item.ItemID = strings.TrimSpace(item.ItemID)
		item.Title = strings.TrimSpace(item.Title)
		item.Note = strings.TrimSpace(item.Note)
		orderKey := [2]int{item.DayIndex, item.OrderInDay}
		if item.ItemID == "" || item.Title == "" || item.DayIndex < 0 || item.OrderInDay < 0 ||
			seenIDs[item.ItemID] || seenOrder[orderKey] || !validKind(item.Kind) || invalidRange(item.StartAt, item.EndAt) {
			return nil, ErrInvalidInput
		}
		if item.PlaceRef != nil {
			item.PlaceRef.ObjectTypeRef = strings.TrimSpace(item.PlaceRef.ObjectTypeRef)
			item.PlaceRef.ObjectID = strings.TrimSpace(item.PlaceRef.ObjectID)
			if item.PlaceRef.ObjectTypeRef == "" || item.PlaceRef.ObjectID == "" {
				return nil, ErrInvalidInput
			}
		}
		item.StartAt = cloneTime(item.StartAt)
		item.EndAt = cloneTime(item.EndAt)
		seenIDs[item.ItemID] = true
		seenOrder[orderKey] = true
		result = append(result, item)
	}
	sort.Slice(result, func(i, j int) bool {
		if result[i].DayIndex != result[j].DayIndex {
			return result[i].DayIndex < result[j].DayIndex
		}
		return result[i].OrderInDay < result[j].OrderInDay
	})
	return result, nil
}

func validKind(kind ItemKind) bool {
	switch kind {
	case ItemStay, ItemFood, ItemSight, ItemActivity, ItemTransport, ItemRest, ItemFreeTime:
		return true
	default:
		return false
	}
}

func canTransition(current, target Status) bool {
	switch current {
	case StatusPlanning:
		return target == StatusActive || target == StatusArchived
	case StatusActive:
		return target == StatusCompleted || target == StatusArchived
	case StatusCompleted:
		return target == StatusArchived || target == StatusActive
	case StatusArchived:
		return target == StatusPlanning || target == StatusActive
	default:
		return false
	}
}

func invalidRange(startAt, endAt *time.Time) bool {
	return startAt != nil && endAt != nil && endAt.Before(*startAt)
}

func cloneTime(value *time.Time) *time.Time {
	if value == nil {
		return nil
	}
	copy := value.UTC()
	return &copy
}

func normalizedIDs(values []string) []string {
	seen := map[string]bool{}
	result := make([]string, 0, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" || seen[value] {
			continue
		}
		seen[value] = true
		result = append(result, value)
	}
	sort.Strings(result)
	return result
}

func itemSnapshots(items []Item) []revisionmodel.ItemSnapshot {
	result := make([]revisionmodel.ItemSnapshot, 0, len(items))
	for _, item := range items {
		var place *revisionmodel.PlaceRef
		if item.PlaceRef != nil {
			place = &revisionmodel.PlaceRef{
				ObjectTypeRef: item.PlaceRef.ObjectTypeRef,
				ObjectID:      item.PlaceRef.ObjectID,
			}
		}
		result = append(result, revisionmodel.ItemSnapshot{
			ItemID: item.ItemID, DayIndex: item.DayIndex, OrderInDay: item.OrderInDay,
			Kind: string(item.Kind), Title: item.Title, StartAt: item.StartAt,
			EndAt: item.EndAt, PlaceRef: place, Note: item.Note,
		})
	}
	return result
}
