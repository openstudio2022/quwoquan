package application

import (
	"net/url"
	"strings"

	"quwoquan_service/services/assistant-service/internal/domain/assistant"
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
			Kind: "external",
			URL:  normalizedURL,
		}, true
	}
	// Canonical object types are dotted metadata identifiers. The Dart
	// metadata-generated resolver rejects identifiers without a registered link
	// template, so unknown internal object types cannot degrade to a post route.
	if objectTypeRef == "" || objectID == "" || !strings.Contains(objectTypeRef, ".") {
		return assistant.CitationDestination{}, false
	}
	return assistant.CitationDestination{
		Kind:          "internal",
		ObjectTypeRef: objectTypeRef,
		ObjectID:      objectID,
	}, true
}

func normalizedHTTPSURL(raw string) (string, bool) {
	parsed, err := url.Parse(strings.TrimSpace(raw))
	if err != nil || !parsed.IsAbs() || !strings.EqualFold(parsed.Scheme, "https") ||
		strings.TrimSpace(parsed.Host) == "" {
		return "", false
	}
	parsed.Fragment = ""
	return parsed.String(), true
}
