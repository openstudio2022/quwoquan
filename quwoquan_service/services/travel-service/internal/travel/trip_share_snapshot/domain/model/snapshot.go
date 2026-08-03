package model

import (
	"errors"
	"sort"
	"strings"
	"time"
)

var (
	ErrInvalidArgument = errors.New("invalid trip share snapshot")
	ErrSourceConflict  = errors.New("trip share snapshot source conflict")
)

const PrivacyPolicyDigestV1 = "sha256:760672367557300130bdf88db43b01f07917475ae4f60ff0b9be95aa78d7e2f1"

type Scope string

const (
	ScopeFull             Scope = "full"
	ScopeDay              Scope = "day"
	ScopeItem             Scope = "item"
	ScopeRoute            Scope = "route"
	ScopeMomentCollection Scope = "moment_collection"
)

type Visibility string

const (
	VisibilityTripMembers Visibility = "trip_members"
	VisibilityPublic      Visibility = "public"
)

type PlaceRef struct {
	ObjectTypeRef string `json:"objectTypeRef" bson:"objectTypeRef"`
	ObjectID      string `json:"objectId" bson:"objectId"`
}

type Item struct {
	DayIndex   int       `json:"dayIndex" bson:"dayIndex"`
	ItemID     string    `json:"itemId" bson:"itemId"`
	OrderInDay int       `json:"orderInDay" bson:"orderInDay"`
	Kind       string    `json:"kind" bson:"kind"`
	Title      string    `json:"title,omitempty" bson:"title,omitempty"`
	PlaceRef   *PlaceRef `json:"placeRef,omitempty" bson:"placeRef,omitempty"`
}

type Moment struct {
	MomentID             string `json:"momentId" bson:"momentId"`
	DayIndex             int    `json:"dayIndex" bson:"dayIndex"`
	ItemID               string `json:"itemId,omitempty" bson:"itemId,omitempty"`
	Kind                 string `json:"kind" bson:"kind"`
	ContentObjectTypeRef string `json:"contentObjectTypeRef,omitempty" bson:"contentObjectTypeRef,omitempty"`
	ContentObjectID      string `json:"contentObjectId,omitempty" bson:"contentObjectId,omitempty"`
}

type ContentLink struct {
	LinkID   string `json:"linkId" bson:"linkId"`
	PostID   string `json:"postId" bson:"postId"`
	DayIndex *int   `json:"dayIndex,omitempty" bson:"dayIndex,omitempty"`
	ItemID   string `json:"itemId,omitempty" bson:"itemId,omitempty"`
}

type RouteStop struct {
	DayIndex int      `json:"dayIndex" bson:"dayIndex"`
	ItemID   string   `json:"itemId" bson:"itemId"`
	Sequence int      `json:"sequence" bson:"sequence"`
	Title    string   `json:"title,omitempty" bson:"title,omitempty"`
	PlaceRef PlaceRef `json:"placeRef" bson:"placeRef"`
}

type Snapshot struct {
	SnapshotID           string        `json:"id" bson:"_id"`
	Version              int64         `json:"version" bson:"version"`
	TripID               string        `json:"tripId" bson:"tripId"`
	SourceRevisionID     string        `json:"sourceRevisionId" bson:"sourceRevisionId"`
	SourceRevisionNumber int64         `json:"sourceRevisionNumber" bson:"sourceRevisionNumber"`
	SourceDigest         string        `json:"sourceDigest" bson:"sourceDigest"`
	Scope                Scope         `json:"scope" bson:"scope"`
	DayIndex             *int          `json:"dayIndex,omitempty" bson:"dayIndex,omitempty"`
	ItemID               string        `json:"itemId,omitempty" bson:"itemId,omitempty"`
	MomentIDs            []string      `json:"momentIds" bson:"momentIds"`
	Visibility           Visibility    `json:"visibility" bson:"visibility"`
	PrivacyPolicyDigest  string        `json:"privacyPolicyDigest" bson:"privacyPolicyDigest"`
	Items                []Item        `json:"items" bson:"items"`
	Moments              []Moment      `json:"moments" bson:"moments"`
	ContentLinks         []ContentLink `json:"contentLinks" bson:"contentLinks"`
	RouteStops           []RouteStop   `json:"routeStops" bson:"routeStops"`
	CreatedByPersonaID   string        `json:"createdByPersonaId" bson:"createdByPersonaId"`
	Status               string        `json:"status" bson:"status"`
	CreatedAt            time.Time     `json:"createdAt" bson:"createdAt"`
}

func (snapshot Snapshot) Validate() error {
	if strings.TrimSpace(snapshot.SnapshotID) == "" || snapshot.Version != 1 ||
		strings.TrimSpace(snapshot.TripID) == "" || strings.TrimSpace(snapshot.SourceRevisionID) == "" ||
		snapshot.SourceRevisionNumber <= 0 || strings.TrimSpace(snapshot.SourceDigest) == "" ||
		!snapshot.Scope.Valid() || !snapshot.Visibility.Valid() ||
		snapshot.PrivacyPolicyDigest != PrivacyPolicyDigestV1 ||
		snapshot.Items == nil || snapshot.Moments == nil || snapshot.ContentLinks == nil ||
		snapshot.RouteStops == nil || snapshot.MomentIDs == nil ||
		strings.TrimSpace(snapshot.CreatedByPersonaID) == "" || snapshot.Status != "active" ||
		snapshot.CreatedAt.IsZero() || !validScope(snapshot) {
		return ErrInvalidArgument
	}
	for _, item := range snapshot.Items {
		if item.DayIndex < 0 || item.OrderInDay < 0 || strings.TrimSpace(item.ItemID) == "" ||
			strings.TrimSpace(item.Kind) == "" || snapshot.Visibility == VisibilityPublic &&
			(strings.EqualFold(item.Kind, "stay") && (item.Title != "" || item.PlaceRef != nil)) {
			return ErrInvalidArgument
		}
	}
	for _, moment := range snapshot.Moments {
		if moment.DayIndex < 0 || strings.TrimSpace(moment.MomentID) == "" || strings.TrimSpace(moment.Kind) == "" {
			return ErrInvalidArgument
		}
	}
	for _, link := range snapshot.ContentLinks {
		if link.DayIndex != nil && *link.DayIndex < 0 || strings.TrimSpace(link.LinkID) == "" || strings.TrimSpace(link.PostID) == "" {
			return ErrInvalidArgument
		}
	}
	for _, stop := range snapshot.RouteStops {
		if stop.DayIndex < 0 || stop.Sequence < 0 || strings.TrimSpace(stop.ItemID) == "" ||
			strings.TrimSpace(stop.PlaceRef.ObjectTypeRef) == "" || strings.TrimSpace(stop.PlaceRef.ObjectID) == "" {
			return ErrInvalidArgument
		}
	}
	return nil
}

func validScope(snapshot Snapshot) bool {
	switch snapshot.Scope {
	case ScopeFull, ScopeRoute:
		return snapshot.DayIndex == nil && snapshot.ItemID == "" && len(snapshot.MomentIDs) == 0
	case ScopeDay:
		return snapshot.DayIndex != nil && *snapshot.DayIndex >= 0 && snapshot.ItemID == "" && len(snapshot.MomentIDs) == 0
	case ScopeItem:
		return snapshot.DayIndex == nil && strings.TrimSpace(snapshot.ItemID) != "" && len(snapshot.MomentIDs) == 0
	case ScopeMomentCollection:
		return snapshot.DayIndex == nil && snapshot.ItemID == "" && len(snapshot.MomentIDs) > 0
	default:
		return false
	}
}

func (scope Scope) Valid() bool {
	return scope == ScopeFull || scope == ScopeDay || scope == ScopeItem ||
		scope == ScopeRoute || scope == ScopeMomentCollection
}

func (visibility Visibility) Valid() bool {
	return visibility == VisibilityTripMembers || visibility == VisibilityPublic
}

func NormalizeMomentIDs(values []string) ([]string, bool) {
	seen := make(map[string]bool, len(values))
	result := make([]string, 0, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" || seen[value] {
			return nil, false
		}
		seen[value] = true
		result = append(result, value)
	}
	sort.Strings(result)
	return result, true
}
