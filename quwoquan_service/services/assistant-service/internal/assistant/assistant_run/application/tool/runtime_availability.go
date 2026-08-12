package tool

const locationBindingNotReadyReason = "integration_location_binding_not_ready"

// RuntimeAvailability is the composition-owned readiness input used to
// reconcile stable canonical tool identities with executable handlers.
// Readiness must be backed by the real binding and probe; false never creates
// a fallback handler and keeps the affected tools out of the model registry.
type RuntimeAvailability struct {
	LocationPublicProviderReady bool
}

// UnavailableCanonicalBindings returns the explicit unavailable side of the
// canonical runtime registry. Every omitted cloud handler still has to appear
// here or RegisterCanonical fails startup before mutating the registry.
func UnavailableCanonicalBindings(
	availability RuntimeAvailability,
) map[string]UnavailableBinding {
	if availability.LocationPublicProviderReady {
		return nil
	}
	return map[string]UnavailableBinding{
		"location_poi_search": {
			BindingKind: "public_provider",
			Reason:      locationBindingNotReadyReason,
		},
		"location_route_read": {
			BindingKind: "public_provider",
			Reason:      locationBindingNotReadyReason,
		},
	}
}
