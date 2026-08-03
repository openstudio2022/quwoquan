package model

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"sort"
	"strings"
	"time"
)

var ErrInvalidRevision = errors.New("invalid trip plan revision")

type Severity string

const (
	SeverityMinor     Severity = "minor"
	SeverityImportant Severity = "important"
	SeverityCritical  Severity = "critical"
)

type ChangeKind string

const (
	ChangeItemAdded        ChangeKind = "item_added"
	ChangeItemRemoved      ChangeKind = "item_removed"
	ChangeItemUpdated      ChangeKind = "item_updated"
	ChangeScheduleChanged  ChangeKind = "schedule_changed"
	ChangeLifecycleChanged ChangeKind = "lifecycle_changed"
)

type PlaceRef struct {
	ObjectTypeRef string `json:"objectTypeRef" bson:"objectTypeRef"`
	ObjectID      string `json:"objectId" bson:"objectId"`
}

type ItemSnapshot struct {
	ItemID     string     `json:"itemId" bson:"itemId"`
	DayIndex   int        `json:"dayIndex" bson:"dayIndex"`
	OrderInDay int        `json:"orderInDay" bson:"orderInDay"`
	Kind       string     `json:"kind" bson:"kind"`
	Title      string     `json:"title" bson:"title"`
	StartAt    *time.Time `json:"startAt,omitempty" bson:"startAt,omitempty"`
	EndAt      *time.Time `json:"endAt,omitempty" bson:"endAt,omitempty"`
	PlaceRef   *PlaceRef  `json:"placeRef,omitempty" bson:"placeRef,omitempty"`
	Note       string     `json:"note,omitempty" bson:"note,omitempty"`
}

type Change struct {
	Kind                ChangeKind `json:"changeKind" bson:"changeKind"`
	ItemID              string     `json:"itemId,omitempty" bson:"itemId,omitempty"`
	Field               string     `json:"field,omitempty" bson:"field,omitempty"`
	PreviousValueDigest string     `json:"previousValueDigest,omitempty" bson:"previousValueDigest,omitempty"`
	CurrentValueDigest  string     `json:"currentValueDigest,omitempty" bson:"currentValueDigest,omitempty"`
}

type Revision struct {
	RevisionID         string         `json:"id" bson:"_id"`
	TripID             string         `json:"tripId" bson:"tripId"`
	RevisionNumber     int64          `json:"revisionNumber" bson:"revisionNumber"`
	PreviousRevisionID string         `json:"previousRevisionId,omitempty" bson:"previousRevisionId,omitempty"`
	ChangeReason       string         `json:"changeReason" bson:"changeReason"`
	Severity           Severity       `json:"severity" bson:"severity"`
	Items              []ItemSnapshot `json:"items" bson:"items"`
	Changes            []Change       `json:"changes" bson:"changes"`
	AffectedPersonaIDs []string       `json:"affectedPersonaIds" bson:"affectedPersonaIds"`
	CreatedByPersonaID string         `json:"createdByPersonaId" bson:"createdByPersonaId"`
	CreatedAt          time.Time      `json:"createdAt" bson:"createdAt"`
}

type CreateInput struct {
	RevisionID         string
	TripID             string
	RevisionNumber     int64
	PreviousRevisionID string
	ChangeReason       string
	Severity           Severity
	Items              []ItemSnapshot
	Changes            []Change
	AffectedPersonaIDs []string
	CreatedByPersonaID string
	CreatedAt          time.Time
}

func Create(input CreateInput) (Revision, error) {
	input.RevisionID = strings.TrimSpace(input.RevisionID)
	input.TripID = strings.TrimSpace(input.TripID)
	input.PreviousRevisionID = strings.TrimSpace(input.PreviousRevisionID)
	input.ChangeReason = strings.TrimSpace(input.ChangeReason)
	input.CreatedByPersonaID = strings.TrimSpace(input.CreatedByPersonaID)
	items, err := normalizeItems(input.Items)
	if err != nil {
		return Revision{}, err
	}
	affected := normalizedIDs(input.AffectedPersonaIDs)
	revision := Revision{
		RevisionID: input.RevisionID, TripID: input.TripID,
		RevisionNumber: input.RevisionNumber, PreviousRevisionID: input.PreviousRevisionID,
		ChangeReason: input.ChangeReason, Severity: input.Severity, Items: items,
		Changes: append([]Change(nil), input.Changes...), AffectedPersonaIDs: affected,
		CreatedByPersonaID: input.CreatedByPersonaID, CreatedAt: input.CreatedAt.UTC(),
	}
	if err := revision.Validate(); err != nil {
		return Revision{}, err
	}
	return revision, nil
}

func (revision Revision) Validate() error {
	if strings.TrimSpace(revision.RevisionID) == "" || strings.TrimSpace(revision.TripID) == "" ||
		revision.RevisionNumber <= 0 || strings.TrimSpace(revision.ChangeReason) == "" ||
		!revision.Severity.Valid() || strings.TrimSpace(revision.CreatedByPersonaID) == "" ||
		revision.CreatedAt.IsZero() || len(revision.AffectedPersonaIDs) == 0 {
		return ErrInvalidRevision
	}
	if revision.RevisionNumber == 1 && strings.TrimSpace(revision.PreviousRevisionID) != "" {
		return ErrInvalidRevision
	}
	if revision.RevisionNumber > 1 && strings.TrimSpace(revision.PreviousRevisionID) == "" {
		return ErrInvalidRevision
	}
	if _, err := normalizeItems(revision.Items); err != nil {
		return err
	}
	for _, change := range revision.Changes {
		if !change.Kind.Valid() {
			return ErrInvalidRevision
		}
	}
	return nil
}

func (severity Severity) Valid() bool {
	return severity == SeverityMinor || severity == SeverityImportant || severity == SeverityCritical
}

func (kind ChangeKind) Valid() bool {
	switch kind {
	case ChangeItemAdded, ChangeItemRemoved, ChangeItemUpdated, ChangeScheduleChanged, ChangeLifecycleChanged:
		return true
	default:
		return false
	}
}

func InitialChanges(items []ItemSnapshot) []Change {
	changes := make([]Change, 0, len(items))
	for _, item := range items {
		changes = append(changes, Change{Kind: ChangeItemAdded, ItemID: item.ItemID, CurrentValueDigest: valueDigest(item)})
	}
	return changes
}

func DiffItems(previous, current []ItemSnapshot) []Change {
	previousByID := make(map[string]ItemSnapshot, len(previous))
	currentByID := make(map[string]ItemSnapshot, len(current))
	for _, item := range previous {
		previousByID[item.ItemID] = item
	}
	for _, item := range current {
		currentByID[item.ItemID] = item
	}
	changes := make([]Change, 0)
	for _, item := range current {
		old, found := previousByID[item.ItemID]
		if !found {
			changes = append(changes, Change{Kind: ChangeItemAdded, ItemID: item.ItemID, CurrentValueDigest: valueDigest(item)})
			continue
		}
		oldDigest, newDigest := valueDigest(old), valueDigest(item)
		if oldDigest != newDigest {
			changes = append(changes, Change{Kind: ChangeItemUpdated, ItemID: item.ItemID, PreviousValueDigest: oldDigest, CurrentValueDigest: newDigest})
		}
	}
	for _, item := range previous {
		if _, found := currentByID[item.ItemID]; !found {
			changes = append(changes, Change{Kind: ChangeItemRemoved, ItemID: item.ItemID, PreviousValueDigest: valueDigest(item)})
		}
	}
	return changes
}

func LifecycleChange(previous, current string) Change {
	return Change{
		Kind: ChangeLifecycleChanged, Field: "status",
		PreviousValueDigest: valueDigest(previous), CurrentValueDigest: valueDigest(current),
	}
}

func normalizeItems(items []ItemSnapshot) ([]ItemSnapshot, error) {
	if len(items) > 512 {
		return nil, ErrInvalidRevision
	}
	seenIDs := map[string]bool{}
	seenOrder := map[[2]int]bool{}
	result := make([]ItemSnapshot, 0, len(items))
	for _, item := range items {
		item.ItemID = strings.TrimSpace(item.ItemID)
		item.Kind = strings.TrimSpace(item.Kind)
		item.Title = strings.TrimSpace(item.Title)
		item.Note = strings.TrimSpace(item.Note)
		orderKey := [2]int{item.DayIndex, item.OrderInDay}
		if item.ItemID == "" || item.Kind == "" || item.Title == "" || item.DayIndex < 0 || item.OrderInDay < 0 ||
			seenIDs[item.ItemID] || seenOrder[orderKey] || invalidRange(item.StartAt, item.EndAt) {
			return nil, ErrInvalidRevision
		}
		if item.PlaceRef != nil {
			item.PlaceRef.ObjectTypeRef = strings.TrimSpace(item.PlaceRef.ObjectTypeRef)
			item.PlaceRef.ObjectID = strings.TrimSpace(item.PlaceRef.ObjectID)
			if item.PlaceRef.ObjectTypeRef == "" || item.PlaceRef.ObjectID == "" {
				return nil, ErrInvalidRevision
			}
		}
		item.StartAt = cloneTime(item.StartAt)
		item.EndAt = cloneTime(item.EndAt)
		seenIDs[item.ItemID], seenOrder[orderKey] = true, true
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

func valueDigest(value any) string {
	raw, _ := json.Marshal(value)
	digest := sha256.Sum256(raw)
	return "sha256:" + hex.EncodeToString(digest[:])
}
