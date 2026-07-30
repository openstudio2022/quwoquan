package orchestration

import (
	"net/url"
	"strings"

	assistantgenerated "quwoquan_service/services/assistant-service/generated/assistant/assistant_conversation"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/domain/assistant"
)

// citationDestinationFromSearch normalizes the search runtime's citation into
// the assistant wire contract. Raw deep links are intentionally discarded:
// App reconstructs internal locations only from canonical object type/id and
// metadata-generated link templates.
func citationDestinationFromSearch(
	objectTypeRef string,
	objectID string,
	rawURL string,
) (assistant.CitationDestination, bool) {
	objectTypeRef = strings.TrimSpace(objectTypeRef)
	objectID = strings.TrimSpace(objectID)
	if objectTypeRef == "web.document" {
		normalizedURL, ok := normalizedHTTPSURL(rawURL)
		if !ok {
			return assistant.CitationDestination{}, false
		}
		return assistant.CitationDestination{
			Kind: assistantgenerated.CitationDestinationKindExternal.WireName(),
			URL:  normalizedURL,
		}, true
	}
	if objectID == "" ||
		!assistantgenerated.IsRegisteredInternalCitationObjectType(objectTypeRef) {
		return assistant.CitationDestination{}, false
	}
	return assistant.CitationDestination{
		Kind:          assistantgenerated.CitationDestinationKindInternal.WireName(),
		ObjectTypeRef: objectTypeRef,
		ObjectID:      objectID,
	}, true
}

func citationDestinationFromMap(
	raw map[string]any,
) (assistant.CitationDestination, bool) {
	kind, err := assistantgenerated.ParseCitationDestinationKind(
		stringValue(raw["kind"]),
	)
	if err != nil {
		return assistant.CitationDestination{}, false
	}
	switch kind {
	case assistantgenerated.CitationDestinationKindInternal:
		if strings.TrimSpace(stringValue(raw["url"])) != "" {
			return assistant.CitationDestination{}, false
		}
		return citationDestinationFromSearch(
			stringValue(raw["objectTypeRef"]),
			stringValue(raw["objectId"]),
			"",
		)
	case assistantgenerated.CitationDestinationKindExternal:
		if strings.TrimSpace(stringValue(raw["objectTypeRef"])) != "" ||
			strings.TrimSpace(stringValue(raw["objectId"])) != "" {
			return assistant.CitationDestination{}, false
		}
		normalizedURL, ok := normalizedHTTPSURL(stringValue(raw["url"]))
		if !ok {
			return assistant.CitationDestination{}, false
		}
		return assistant.CitationDestination{
			Kind: assistantgenerated.CitationDestinationKindExternal.WireName(),
			URL:  normalizedURL,
		}, true
	default:
		return assistant.CitationDestination{}, false
	}
}

func citationDestinationMap(
	destination assistant.CitationDestination,
) map[string]any {
	result := map[string]any{"kind": destination.Kind}
	if destination.ObjectTypeRef != "" {
		result["objectTypeRef"] = destination.ObjectTypeRef
	}
	if destination.ObjectID != "" {
		result["objectId"] = destination.ObjectID
	}
	if destination.URL != "" {
		result["url"] = destination.URL
	}
	return result
}

func CanonicalToolReference(raw map[string]any) (map[string]any, bool) {
	var (
		destination assistant.CitationDestination
		ok          bool
	)
	if rawDestination, exists := raw["destination"].(map[string]any); exists {
		destination, ok = citationDestinationFromMap(rawDestination)
	} else {
		destination, ok = citationDestinationFromSearch(
			stringValue(raw["objectType"]),
			stringValue(raw["objectId"]),
			stringValue(raw["url"]),
		)
	}
	if !ok {
		return nil, false
	}
	source := stringValue(raw["source"])
	if source == "" {
		source = stringValue(raw["sourceDomain"])
	}
	return map[string]any{
		"title":       stringValue(raw["title"]),
		"source":      source,
		"snippet":     stringValue(raw["snippet"]),
		"destination": citationDestinationMap(destination),
	}, true
}

func canonicalModelReference(raw map[string]any) (map[string]any, bool) {
	rawDestination, ok := raw["destination"].(map[string]any)
	if !ok {
		return nil, false
	}
	destination, ok := citationDestinationFromMap(rawDestination)
	if !ok {
		return nil, false
	}
	return map[string]any{
		"title":       stringValue(raw["title"]),
		"source":      stringValue(raw["source"]),
		"snippet":     stringValue(raw["snippet"]),
		"destination": citationDestinationMap(destination),
	}, true
}

func normalizedHTTPSURL(raw string) (string, bool) {
	parsed, err := url.Parse(strings.TrimSpace(raw))
	if err != nil || !parsed.IsAbs() ||
		!assistantgenerated.IsAllowedExternalCitationScheme(parsed.Scheme) ||
		strings.TrimSpace(parsed.Host) == "" {
		return "", false
	}
	parsed.Fragment = ""
	return parsed.String(), true
}
