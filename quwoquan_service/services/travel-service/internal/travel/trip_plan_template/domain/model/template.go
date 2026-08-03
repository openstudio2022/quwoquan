package model

import (
	"errors"
	"sort"
	"strings"
	"time"
)

var (
	ErrInvalidArgument  = errors.New("invalid trip plan template")
	ErrPermissionDenied = errors.New("trip plan template permission denied")
	ErrRevisionConflict = errors.New("trip plan template revision conflict")
)

type Status string
type AttributionKind string

const (
	StatusActive   Status = "active"
	StatusArchived Status = "archived"

	AttributionPublicSource           AttributionKind = "public_source"
	AttributionProfessionalCommentary AttributionKind = "professional_commentary"
)

type PlaceRef struct {
	ObjectTypeRef string `json:"objectTypeRef" bson:"objectTypeRef"`
	ObjectID      string `json:"objectId" bson:"objectId"`
}

type Item struct {
	TemplateItemID string    `json:"templateItemId" bson:"templateItemId"`
	DayOffset      int       `json:"dayOffset" bson:"dayOffset"`
	OrderInDay     int       `json:"orderInDay" bson:"orderInDay"`
	Kind           string    `json:"kind" bson:"kind"`
	Title          string    `json:"title,omitempty" bson:"title,omitempty"`
	PublicPlaceRef *PlaceRef `json:"publicPlaceRef,omitempty" bson:"publicPlaceRef,omitempty"`
	Note           string    `json:"note,omitempty" bson:"note,omitempty"`
	AttributionIDs []string  `json:"attributionIds" bson:"attributionIds"`
}

type Attribution struct {
	AttributionID          string          `json:"attributionId" bson:"attributionId"`
	Kind                   AttributionKind `json:"kind" bson:"kind"`
	ReferenceObjectTypeRef string          `json:"referenceObjectTypeRef" bson:"referenceObjectTypeRef"`
	ReferenceObjectID      string          `json:"referenceObjectId" bson:"referenceObjectId"`
	AuthorPersonaID        string          `json:"authorPersonaId,omitempty" bson:"authorPersonaId,omitempty"`
	Title                  string          `json:"title" bson:"title"`
}

type Template struct {
	TemplateID            string        `json:"id" bson:"_id"`
	Version               int64         `json:"version" bson:"version"`
	OwnerPersonaID        string        `json:"ownerPersonaId" bson:"ownerPersonaId"`
	Title                 string        `json:"title" bson:"title"`
	Summary               string        `json:"summary,omitempty" bson:"summary,omitempty"`
	DayCount              int           `json:"dayCount" bson:"dayCount"`
	TemplateItemIDs       []string      `json:"templateItemIds" bson:"templateItemIds"`
	Items                 []Item        `json:"items" bson:"items"`
	AttributionIDs        []string      `json:"attributionIds" bson:"attributionIds"`
	AttributionPersonaIDs []string      `json:"attributionPersonaIds" bson:"attributionPersonaIds"`
	Attributions          []Attribution `json:"attributions" bson:"attributions"`
	Status                Status        `json:"status" bson:"status"`
	CreatedAt             time.Time     `json:"createdAt" bson:"createdAt"`
	UpdatedAt             time.Time     `json:"updatedAt" bson:"updatedAt"`
}

type PutInput struct {
	Title        string
	Summary      string
	DayCount     int
	Items        []Item
	Attributions []Attribution
}

func Create(id, ownerPersonaID string, input PutInput, now time.Time) (Template, error) {
	template := Template{
		TemplateID: strings.TrimSpace(id), Version: 1,
		OwnerPersonaID: strings.TrimSpace(ownerPersonaID), Status: StatusActive,
		CreatedAt: now.UTC(), UpdatedAt: now.UTC(),
	}
	apply(&template, input)
	if err := template.Validate(); err != nil {
		return Template{}, err
	}
	return template, nil
}

func (template Template) Revise(actorPersonaID string, expectedVersion int64, input PutInput, now time.Time) (Template, error) {
	if strings.TrimSpace(actorPersonaID) != template.OwnerPersonaID {
		return Template{}, ErrPermissionDenied
	}
	if expectedVersion != template.Version {
		return Template{}, ErrRevisionConflict
	}
	next := template
	next.Version++
	next.UpdatedAt = now.UTC()
	apply(&next, input)
	if err := next.Validate(); err != nil {
		return Template{}, err
	}
	return next, nil
}

func apply(template *Template, input PutInput) {
	template.Title = strings.TrimSpace(input.Title)
	template.Summary = strings.TrimSpace(input.Summary)
	template.DayCount = input.DayCount
	template.Items = append([]Item{}, input.Items...)
	template.Attributions = append([]Attribution{}, input.Attributions...)
	template.TemplateItemIDs = make([]string, 0, len(template.Items))
	template.AttributionIDs = make([]string, 0, len(template.Attributions))
	personas := map[string]bool{}
	for index := range template.Items {
		template.Items[index].TemplateItemID = strings.TrimSpace(template.Items[index].TemplateItemID)
		template.Items[index].Kind = strings.TrimSpace(template.Items[index].Kind)
		template.Items[index].Title = strings.TrimSpace(template.Items[index].Title)
		template.Items[index].Note = strings.TrimSpace(template.Items[index].Note)
		template.Items[index].AttributionIDs = normalizeStrings(template.Items[index].AttributionIDs)
		template.TemplateItemIDs = append(template.TemplateItemIDs, template.Items[index].TemplateItemID)
	}
	for index := range template.Attributions {
		attribution := &template.Attributions[index]
		attribution.AttributionID = strings.TrimSpace(attribution.AttributionID)
		attribution.ReferenceObjectTypeRef = strings.TrimSpace(attribution.ReferenceObjectTypeRef)
		attribution.ReferenceObjectID = strings.TrimSpace(attribution.ReferenceObjectID)
		attribution.AuthorPersonaID = strings.TrimSpace(attribution.AuthorPersonaID)
		attribution.Title = strings.TrimSpace(attribution.Title)
		template.AttributionIDs = append(template.AttributionIDs, attribution.AttributionID)
		if attribution.AuthorPersonaID != "" {
			personas[attribution.AuthorPersonaID] = true
		}
	}
	template.AttributionPersonaIDs = make([]string, 0, len(personas))
	for personaID := range personas {
		template.AttributionPersonaIDs = append(template.AttributionPersonaIDs, personaID)
	}
	sort.Strings(template.AttributionPersonaIDs)
}

func (template Template) Validate() error {
	if template.TemplateID == "" || template.Version <= 0 || template.OwnerPersonaID == "" ||
		template.Title == "" || len([]rune(template.Title)) > 120 || template.DayCount <= 0 || template.DayCount > 30 ||
		template.TemplateItemIDs == nil || template.Items == nil || template.AttributionIDs == nil ||
		template.AttributionPersonaIDs == nil || template.Attributions == nil || template.Status != StatusActive ||
		template.CreatedAt.IsZero() || template.UpdatedAt.IsZero() || len(template.Items) == 0 || len(template.Items) > 200 {
		return ErrInvalidArgument
	}
	knownAttributions := map[string]bool{}
	for _, attribution := range template.Attributions {
		if attribution.AttributionID == "" || knownAttributions[attribution.AttributionID] ||
			!attribution.Kind.Valid() || attribution.ReferenceObjectTypeRef == "" ||
			attribution.ReferenceObjectID == "" || attribution.Title == "" ||
			attribution.Kind == AttributionProfessionalCommentary && attribution.AuthorPersonaID == "" {
			return ErrInvalidArgument
		}
		knownAttributions[attribution.AttributionID] = true
	}
	seenItems := map[string]bool{}
	orders := map[int]map[int]bool{}
	for _, item := range template.Items {
		if item.TemplateItemID == "" || seenItems[item.TemplateItemID] || item.DayOffset < 0 ||
			item.DayOffset >= template.DayCount || item.OrderInDay < 0 || !validItemKind(item.Kind) ||
			strings.EqualFold(item.Kind, "stay") && (item.Title != "" || item.Note != "" || item.PublicPlaceRef != nil) {
			return ErrInvalidArgument
		}
		if orders[item.DayOffset] == nil {
			orders[item.DayOffset] = map[int]bool{}
		}
		if orders[item.DayOffset][item.OrderInDay] {
			return ErrInvalidArgument
		}
		orders[item.DayOffset][item.OrderInDay] = true
		seenItems[item.TemplateItemID] = true
		if item.PublicPlaceRef != nil && (strings.TrimSpace(item.PublicPlaceRef.ObjectTypeRef) != "entity.Place" || strings.TrimSpace(item.PublicPlaceRef.ObjectID) == "") {
			return ErrInvalidArgument
		}
		for _, attributionID := range item.AttributionIDs {
			if !knownAttributions[attributionID] {
				return ErrInvalidArgument
			}
		}
	}
	return nil
}

func (kind AttributionKind) Valid() bool {
	return kind == AttributionPublicSource || kind == AttributionProfessionalCommentary
}

func validItemKind(kind string) bool {
	switch kind {
	case "stay", "food", "sight", "activity", "transport", "rest", "free_time":
		return true
	default:
		return false
	}
}

func normalizeStrings(values []string) []string {
	result := make([]string, 0, len(values))
	seen := map[string]bool{}
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value != "" && !seen[value] {
			seen[value] = true
			result = append(result, value)
		}
	}
	sort.Strings(result)
	return result
}
