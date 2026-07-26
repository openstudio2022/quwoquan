package provider

import (
	"net/http"
	"strings"

	serviceclients "quwoquan_service/generated/serviceclients"
)

// ObservedEndpoint returns the bounded route label used for external-provider
// telemetry without exposing device tokens, endpoint references or project IDs.
func ObservedEndpoint(request *http.Request) string {
	path := request.URL.Path
	switch {
	case strings.HasPrefix(path, "/3/device/"):
		return "/3/device/{token}"
	case matchesEndpointPathTemplate(path, serviceclients.UserPushEndpointSecretPathTemplate):
		return serviceclients.UserPushEndpointSecretPathTemplate
	case matchesEndpointPathTemplate(path, serviceclients.UserPushEndpointInvalidatePathTemplate):
		return serviceclients.UserPushEndpointInvalidatePathTemplate
	case strings.HasPrefix(path, "/v1/projects/") && strings.HasSuffix(path, "/messages:send"):
		return "/v1/projects/{projectId}/messages:send"
	default:
		return path
	}
}

func matchesEndpointPathTemplate(path string, template string) bool {
	parts := strings.Split(template, "{endpointRef}")
	return len(parts) == 2 && strings.HasPrefix(path, parts[0]) && strings.HasSuffix(path, parts[1])
}
