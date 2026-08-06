package ast

import (
	"regexp"
	"strings"
)

var canonicalEventRefPattern = regexp.MustCompile(
	`^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*\.[A-Z][A-Za-z0-9]*$`,
)

// CanonicalEventRef returns the only stable event identity. ObjectID is already
// path-derived, so neither a service name nor a topic participates in identity.
func CanonicalEventRef(objectID string, eventName string) string {
	objectID = strings.TrimSpace(objectID)
	eventName = strings.TrimSpace(eventName)
	if objectID == "" || eventName == "" {
		return ""
	}
	return objectID + "." + eventName
}

// IsCanonicalEventRef rejects the old domain.EventName shorthand. Consumers
// must name the producing object explicitly; name-only inference is forbidden.
func IsCanonicalEventRef(value string) bool {
	return canonicalEventRefPattern.MatchString(strings.TrimSpace(value))
}

// CanonicalConsumerRef is the path-derived consuming object. Event delivery
// is an object lifecycle fact, not a synthetic operation/runtime entrypoint;
// handler names remain object-local implementation seams.
func CanonicalConsumerRef(object Object) string {
	return strings.TrimSpace(object.ID)
}
