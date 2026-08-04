package presentation

import (
	"fmt"
	"math"
	"strings"
)

const (
	maxRouteMapStops    = 128
	maxRouteMapSegments = 127
	maxRouteMapMarkers  = 128
)

var allowedRouteModeTokens = map[string]bool{
	"walk": true, "bicycle": true, "transit": true, "drive": true,
	"rail": true, "flight": true, "ferry": true,
}

func validateRouteMapData(data map[string]any) error {
	if !exactMapKeys(
		data,
		[]string{"tripId", "revisionId", "sourceDigest", "stops", "segments", "markers"},
		[]string{"tripId", "revisionId", "sourceDigest", "stops"},
	) || !identifierPattern.MatchString(stringValue(data["tripId"])) ||
		!identifierPattern.MatchString(stringValue(data["revisionId"])) ||
		!digestPattern.MatchString(stringValue(data["sourceDigest"])) {
		return fmt.Errorf("%w: route_map identity is invalid", ErrInvalidData)
	}
	stops, ok := objectList(data["stops"], 1, maxRouteMapStops)
	if !ok {
		return fmt.Errorf("%w: route_map stops are invalid", ErrInvalidData)
	}
	placeRefs := make(map[string]bool, len(stops))
	stopOrders := make(map[[2]int]bool, len(stops))
	for _, stop := range stops {
		if !exactMapKeys(
			stop,
			[]string{"placeRef", "dayIndex", "order", "itemId", "title"},
			[]string{"placeRef", "dayIndex", "order"},
		) {
			return fmt.Errorf("%w: route_map stop fields are invalid", ErrInvalidData)
		}
		placeRef, key, valid := canonicalPlaceRef(stop["placeRef"])
		dayIndex, dayOK := boundedInteger(stop["dayIndex"], 0, 366)
		order, orderOK := boundedInteger(stop["order"], 0, maxRouteMapStops-1)
		if !valid || !dayOK || !orderOK || stopOrders[[2]int{dayIndex, order}] ||
			!optionalIdentifier(stop["itemId"]) || !optionalText(stop["title"], 512) {
			return fmt.Errorf("%w: route_map stop is invalid", ErrInvalidData)
		}
		_ = placeRef
		placeRefs[key] = true
		stopOrders[[2]int{dayIndex, order}] = true
	}
	segments, ok := optionalObjectList(data["segments"], maxRouteMapSegments)
	if !ok || len(segments) > max(0, len(stops)-1) {
		return fmt.Errorf("%w: route_map segments are invalid", ErrInvalidData)
	}
	segmentOrders := make(map[int]bool, len(segments))
	for _, segment := range segments {
		if !exactMapKeys(
			segment,
			[]string{"fromPlaceRef", "toPlaceRef", "modeToken", "order"},
			[]string{"fromPlaceRef", "toPlaceRef", "modeToken", "order"},
		) {
			return fmt.Errorf("%w: route_map segment fields are invalid", ErrInvalidData)
		}
		_, fromKey, fromOK := canonicalPlaceRef(segment["fromPlaceRef"])
		_, toKey, toOK := canonicalPlaceRef(segment["toPlaceRef"])
		order, orderOK := boundedInteger(segment["order"], 0, maxRouteMapSegments-1)
		mode := stringValue(segment["modeToken"])
		if !fromOK || !toOK || fromKey == toKey || !placeRefs[fromKey] || !placeRefs[toKey] ||
			!orderOK || segmentOrders[order] || !allowedRouteModeTokens[mode] {
			return fmt.Errorf("%w: route_map segment is invalid", ErrInvalidData)
		}
		segmentOrders[order] = true
	}
	markers, ok := optionalObjectList(data["markers"], maxRouteMapMarkers)
	if !ok {
		return fmt.Errorf("%w: route_map markers are invalid", ErrInvalidData)
	}
	markerIDs := make(map[string]bool, len(markers))
	for _, marker := range markers {
		if !exactMapKeys(
			marker,
			[]string{"momentId", "placeRef", "dayIndex", "itemId"},
			[]string{"momentId", "placeRef", "dayIndex"},
		) {
			return fmt.Errorf("%w: route_map marker fields are invalid", ErrInvalidData)
		}
		momentID := stringValue(marker["momentId"])
		_, _, placeOK := canonicalPlaceRef(marker["placeRef"])
		_, dayOK := boundedInteger(marker["dayIndex"], 0, 366)
		if !identifierPattern.MatchString(momentID) || markerIDs[momentID] || !placeOK || !dayOK ||
			!optionalIdentifier(marker["itemId"]) {
			return fmt.Errorf("%w: route_map marker is invalid", ErrInvalidData)
		}
		markerIDs[momentID] = true
	}
	return nil
}

func exactMapKeys(value map[string]any, allowed, required []string) bool {
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

func objectList(value any, minimum, maximum int) ([]map[string]any, bool) {
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

func optionalObjectList(value any, maximum int) ([]map[string]any, bool) {
	if value == nil {
		return []map[string]any{}, true
	}
	return objectList(value, 0, maximum)
}

func canonicalPlaceRef(value any) (map[string]any, string, bool) {
	placeRef, ok := value.(map[string]any)
	if !ok || !exactMapKeys(
		placeRef,
		[]string{"objectTypeRef", "objectId"},
		[]string{"objectTypeRef", "objectId"},
	) {
		return nil, "", false
	}
	objectTypeRef := stringValue(placeRef["objectTypeRef"])
	objectID := stringValue(placeRef["objectId"])
	if !identifierPattern.MatchString(objectTypeRef) || !strings.Contains(objectTypeRef, ".") ||
		!identifierPattern.MatchString(objectID) || unsafeURIPattern.MatchString(objectTypeRef) ||
		unsafeURIPattern.MatchString(objectID) {
		return nil, "", false
	}
	return placeRef, objectTypeRef + ":" + objectID, true
}

func boundedInteger(value any, minimum, maximum int) (int, bool) {
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

func stringValue(value any) string {
	text, _ := value.(string)
	return strings.TrimSpace(text)
}

func optionalIdentifier(value any) bool {
	if value == nil || stringValue(value) == "" {
		return true
	}
	return identifierPattern.MatchString(stringValue(value))
}

func optionalText(value any, maximum int) bool {
	if value == nil {
		return true
	}
	text, ok := value.(string)
	return ok && len([]rune(strings.TrimSpace(text))) <= maximum &&
		!rawHTMLPattern.MatchString(text) && !unsafeURIPattern.MatchString(text)
}
