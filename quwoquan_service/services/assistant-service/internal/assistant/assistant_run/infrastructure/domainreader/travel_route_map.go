package domainreader

import (
	"fmt"
	"math"
	"regexp"
	"strings"
	"time"
)

const (
	maxTravelRouteMapStops    = 128
	maxTravelRouteMapSegments = 127
	maxTravelRouteMapMarkers  = 128
)

var (
	travelRouteIdentifierPattern = regexp.MustCompile(`^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$`)
	travelRouteDigestPattern     = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)
	travelRouteRawHTMLPattern    = regexp.MustCompile(`(?i)<\s*/?\s*[a-z][^>]*>`)
	travelRouteUnsafeURIPattern  = regexp.MustCompile(`(?i)(?:javascript|data|file):`)
)

// projectTravelTripMap converts the authoritative TripMapView wire into the
// provider-neutral route_map semantic payload consumed by Presentation. This
// vertical anti-corruption adapter belongs beside the Travel reader; the
// generic Presentation registry only validates the canonical semantic shape.
func projectTravelTripMap(tripMap map[string]any) (map[string]any, error) {
	if !travelExactMapKeys(
		tripMap,
		[]string{
			"tripId", "currentRevisionId", "currentRevisionNumber",
			"stops", "routeSegments", "momentMarkers", "sourceMomentIds",
			"sourceContentLinkIds", "sourceDigest", "sourceEventId", "projectedAt",
		},
		[]string{
			"tripId", "currentRevisionId", "currentRevisionNumber",
			"stops", "routeSegments", "momentMarkers", "sourceMomentIds",
			"sourceContentLinkIds", "sourceDigest", "sourceEventId", "projectedAt",
		},
	) {
		return nil, fmt.Errorf("travel TripMapView fields are invalid")
	}
	tripID := travelStringValue(tripMap["tripId"])
	revisionID := travelStringValue(tripMap["currentRevisionId"])
	sourceDigest := travelStringValue(tripMap["sourceDigest"])
	revisionNumber, revisionNumberOK := travelBoundedInteger(
		tripMap["currentRevisionNumber"],
		1,
		1<<31-1,
	)
	sourceEventID := travelStringValue(tripMap["sourceEventId"])
	projectedAt := travelStringValue(tripMap["projectedAt"])
	_, projectedAtErr := time.Parse(time.RFC3339Nano, projectedAt)
	if !travelRouteIdentifierPattern.MatchString(tripID) ||
		!travelRouteIdentifierPattern.MatchString(revisionID) ||
		!revisionNumberOK || revisionNumber < 1 ||
		!travelRouteDigestPattern.MatchString(sourceDigest) ||
		!travelRouteIdentifierPattern.MatchString(sourceEventID) ||
		projectedAtErr != nil ||
		!travelIdentifierList(tripMap["sourceMomentIds"], maxTravelRouteMapMarkers) ||
		!travelIdentifierList(tripMap["sourceContentLinkIds"], maxTravelRouteMapMarkers) {
		return nil, fmt.Errorf("travel TripMapView identity or provenance is invalid")
	}
	rawStops, ok := travelObjectList(
		tripMap["stops"],
		1,
		maxTravelRouteMapStops,
	)
	if !ok {
		return nil, fmt.Errorf("travel TripMapView stops are invalid")
	}
	stops := make([]any, 0, len(rawStops))
	stopIDs := make(map[string]bool, len(rawStops))
	stopSequences := make(map[int]bool, len(rawStops))
	for _, stop := range rawStops {
		if !travelExactMapKeys(
			stop,
			[]string{
				"stopId", "sequence", "dayIndex", "itemId", "title",
				"placeRef", "momentIds", "contentLinkIds",
			},
			[]string{
				"stopId", "sequence", "dayIndex", "itemId", "title",
				"placeRef", "momentIds", "contentLinkIds",
			},
		) {
			return nil, fmt.Errorf("travel TripMapView stop fields are invalid")
		}
		stopID := travelStringValue(stop["stopId"])
		placeRef, placeOK := travelCanonicalPlaceRef(stop["placeRef"])
		dayIndex, dayOK := travelBoundedInteger(stop["dayIndex"], 0, 366)
		sequence, sequenceOK := travelBoundedInteger(
			stop["sequence"],
			0,
			maxTravelRouteMapStops-1,
		)
		if !travelRouteIdentifierPattern.MatchString(stopID) || stopIDs[stopID] ||
			stopSequences[sequence] || !placeOK || !dayOK || !sequenceOK ||
			!travelOptionalIdentifier(stop["itemId"]) ||
			!travelOptionalText(stop["title"], 512) ||
			!travelIdentifierList(stop["momentIds"], maxTravelRouteMapMarkers) ||
			!travelIdentifierList(stop["contentLinkIds"], maxTravelRouteMapMarkers) {
			return nil, fmt.Errorf("travel TripMapView stop is invalid")
		}
		stopIDs[stopID] = true
		stopSequences[sequence] = true
		stops = append(stops, map[string]any{
			"placeRef": placeRef,
			"dayIndex": dayIndex,
			"order":    sequence,
			"itemId":   travelStringValue(stop["itemId"]),
			"title":    travelStringValue(stop["title"]),
		})
	}
	routeSegments, ok := travelObjectList(
		tripMap["routeSegments"],
		0,
		maxTravelRouteMapSegments,
	)
	if !ok {
		return nil, fmt.Errorf("travel TripMapView route segments are invalid")
	}
	segmentOrders := make(map[int]bool, len(routeSegments))
	for _, segment := range routeSegments {
		if !travelExactMapKeys(
			segment,
			[]string{"segmentId", "sequence", "fromStopId", "toStopId"},
			[]string{"segmentId", "sequence", "fromStopId", "toStopId"},
		) {
			return nil, fmt.Errorf("travel TripMapView route segment fields are invalid")
		}
		segmentID := travelStringValue(segment["segmentId"])
		fromStopID := travelStringValue(segment["fromStopId"])
		toStopID := travelStringValue(segment["toStopId"])
		sequence, sequenceOK := travelBoundedInteger(
			segment["sequence"],
			0,
			maxTravelRouteMapSegments-1,
		)
		if !travelRouteIdentifierPattern.MatchString(segmentID) || !sequenceOK ||
			segmentOrders[sequence] || fromStopID == toStopID ||
			!stopIDs[fromStopID] || !stopIDs[toStopID] {
			return nil, fmt.Errorf("travel TripMapView route segment is invalid")
		}
		segmentOrders[sequence] = true
	}
	rawMarkers, ok := travelObjectList(
		tripMap["momentMarkers"],
		0,
		maxTravelRouteMapMarkers,
	)
	if !ok {
		return nil, fmt.Errorf("travel TripMapView moment markers are invalid")
	}
	markers := make([]any, 0, len(rawMarkers))
	markerIDs := make(map[string]bool, len(rawMarkers))
	for _, marker := range rawMarkers {
		if !travelExactMapKeys(
			marker,
			[]string{"momentId", "dayIndex", "itemId", "placeRef"},
			[]string{"momentId", "dayIndex", "placeRef"},
		) {
			return nil, fmt.Errorf("travel TripMapView marker fields are invalid")
		}
		momentID := travelStringValue(marker["momentId"])
		placeRef, placeOK := travelCanonicalPlaceRef(marker["placeRef"])
		dayIndex, dayOK := travelBoundedInteger(marker["dayIndex"], 0, 366)
		if !travelRouteIdentifierPattern.MatchString(momentID) || markerIDs[momentID] ||
			!placeOK || !dayOK || !travelOptionalIdentifier(marker["itemId"]) {
			return nil, fmt.Errorf("travel TripMapView marker is invalid")
		}
		markerIDs[momentID] = true
		markers = append(markers, map[string]any{
			"momentId": momentID,
			"placeRef": placeRef,
			"dayIndex": dayIndex,
			"itemId":   travelStringValue(marker["itemId"]),
		})
	}
	return map[string]any{
		"tripId":       tripID,
		"revisionId":   revisionID,
		"sourceDigest": sourceDigest,
		"stops":        stops,
		// TripMapView owns adjacency but has no canonical transport mode token;
		// never invent a provider-specific segment for the semantic document.
		"segments": []any{},
		"markers":  markers,
	}, nil
}

func travelExactMapKeys(value map[string]any, allowed, required []string) bool {
	if value == nil {
		return false
	}
	allowedSet := make(map[string]bool, len(allowed))
	for _, key := range allowed {
		allowedSet[key] = true
	}
	for key := range value {
		if !allowedSet[key] {
			return false
		}
	}
	for _, key := range required {
		if _, found := value[key]; !found {
			return false
		}
	}
	return true
}

func travelObjectList(value any, minimum, maximum int) ([]map[string]any, bool) {
	raw, ok := value.([]any)
	if !ok || len(raw) < minimum || len(raw) > maximum {
		return nil, false
	}
	result := make([]map[string]any, 0, len(raw))
	for _, item := range raw {
		object, ok := item.(map[string]any)
		if !ok {
			return nil, false
		}
		result = append(result, object)
	}
	return result, true
}

func travelCanonicalPlaceRef(value any) (map[string]any, bool) {
	placeRef, ok := value.(map[string]any)
	if !ok || !travelExactMapKeys(
		placeRef,
		[]string{"objectTypeRef", "objectId"},
		[]string{"objectTypeRef", "objectId"},
	) {
		return nil, false
	}
	objectTypeRef := travelStringValue(placeRef["objectTypeRef"])
	objectID := travelStringValue(placeRef["objectId"])
	if !travelRouteIdentifierPattern.MatchString(objectTypeRef) ||
		!strings.Contains(objectTypeRef, ".") ||
		!travelRouteIdentifierPattern.MatchString(objectID) ||
		travelRouteUnsafeURIPattern.MatchString(objectTypeRef) ||
		travelRouteUnsafeURIPattern.MatchString(objectID) {
		return nil, false
	}
	return map[string]any{
		"objectTypeRef": objectTypeRef,
		"objectId":      objectID,
	}, true
}

func travelBoundedInteger(value any, minimum, maximum int) (int, bool) {
	var number int
	switch typed := value.(type) {
	case int:
		number = typed
	case int32:
		number = int(typed)
	case int64:
		number = int(typed)
	case float64:
		if math.Trunc(typed) != typed {
			return 0, false
		}
		number = int(typed)
	default:
		return 0, false
	}
	return number, number >= minimum && number <= maximum
}

func travelStringValue(value any) string {
	text, _ := value.(string)
	return strings.TrimSpace(text)
}

func travelOptionalIdentifier(value any) bool {
	if value == nil || travelStringValue(value) == "" {
		return true
	}
	return travelRouteIdentifierPattern.MatchString(travelStringValue(value))
}

func travelOptionalText(value any, maximum int) bool {
	if value == nil {
		return true
	}
	text, ok := value.(string)
	return ok && len([]rune(strings.TrimSpace(text))) <= maximum &&
		!travelRouteRawHTMLPattern.MatchString(text) &&
		!travelRouteUnsafeURIPattern.MatchString(text)
}

func travelIdentifierList(value any, maximum int) bool {
	raw, ok := value.([]any)
	if !ok || len(raw) > maximum {
		return false
	}
	seen := make(map[string]bool, len(raw))
	for _, item := range raw {
		identifier := travelStringValue(item)
		if !travelRouteIdentifierPattern.MatchString(identifier) || seen[identifier] {
			return false
		}
		seen[identifier] = true
	}
	return true
}
