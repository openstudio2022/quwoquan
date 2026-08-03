package skillcontext

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	generated "quwoquan_service/services/assistant-service/generated/assistant/assistant_session"
	application "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/skillcontext"
	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/domainreader"
)

type TravelContextResolver struct {
	Runs   RunReader
	Travel domainreader.TravelContextReader
}

func (resolver TravelContextResolver) Resolve(
	ctx context.Context,
	request application.ResolveRequest,
) (application.ResolvedContext, error) {
	if resolver.Runs == nil || resolver.Travel == nil {
		return application.ResolvedContext{}, fmt.Errorf("travel context resolver is unavailable")
	}
	run, err := resolver.Runs.Load(ctx, strings.TrimSpace(request.RunID))
	if err != nil {
		return application.ResolvedContext{}, err
	}
	tripID := tripIDFromRun(run.ContextSnapshot, run.Trigger)
	if tripID == "" || strings.TrimSpace(run.PersonaID) == "" {
		return application.ResolvedContext{}, fmt.Errorf("travel context target is unavailable")
	}
	tripContext, err := resolver.Travel.ReadTripContext(ctx, run.PersonaID, tripID)
	if err != nil {
		return application.ResolvedContext{}, err
	}
	value := map[string]any{
		"tripId":                tripContext.TripID,
		"currentRevisionId":     tripContext.CurrentRevisionID,
		"currentRevisionNumber": tripContext.CurrentRevisionNumber,
		"sourceDigest":          tripContext.SourceDigest,
		"timeline":              tripContext.Timeline,
		"map":                   tripContext.Map,
		"guideAssignments":      tripContext.GuideAssignments,
	}
	raw, _ := json.Marshal(value)
	summary := fmt.Sprintf(
		"Trip %s revision %d; timelineDays=%d mapStops=%d sharedMoments=%d contentLinks=%d guideAssignments=%d",
		tripContext.TripID,
		tripContext.CurrentRevisionNumber,
		listLength(tripContext.Timeline, "days"),
		listLength(tripContext.Map, "stops"),
		listLength(tripContext.Timeline, "sourceMomentIds"),
		listLength(tripContext.Timeline, "sourceContentLinkIds"),
		listLength(tripContext.GuideAssignments, "assignments"),
	)
	return application.ResolvedContext{
		Kind:        "domain",
		SourceRef:   "travel.TripTimelineView:" + tripContext.TripID + "@" + tripContext.SourceDigest,
		Authority:   generated.AssistantContextAuthorityDomainCanonical,
		Sensitivity: generated.AssistantContextSensitivityInternal,
		CapturedAt:  tripContext.ProjectedAt,
		TokenCost:   (len(raw) + 3) / 4,
		Value:       value,
		ArtifactRef: "travel.TripTimelineView:" + tripContext.TripID + "@" + tripContext.SourceDigest,
		Summary:     summary,
	}, nil
}

func tripIDFromRun(contextSnapshot, trigger map[string]any) string {
	if tripID := tripIDFromPageObjects(contextSnapshot["pageObjects"]); tripID != "" {
		return tripID
	}
	for _, signalRef := range stringSliceValue(trigger, "signalRefs") {
		const prefix = "travel.TripPlan:"
		if strings.HasPrefix(signalRef, prefix) {
			if tripID := strings.TrimSpace(strings.TrimPrefix(signalRef, prefix)); tripID != "" {
				return tripID
			}
		}
	}
	return ""
}

func tripIDFromPageObjects(raw any) string {
	values, ok := raw.([]any)
	if !ok {
		return ""
	}
	for _, value := range values {
		object, ok := value.(map[string]any)
		if !ok {
			continue
		}
		objectType := stringMapValue(object, "objectTypeRef")
		if objectType != "travel.TripPlan" && objectType != "travel.TripTimelineView" &&
			objectType != "travel.TripMapView" {
			continue
		}
		if objectID := stringMapValue(object, "objectId"); objectID != "" {
			return objectID
		}
	}
	return ""
}

func stringMapValue(values map[string]any, key string) string {
	value, _ := values[key].(string)
	return strings.TrimSpace(value)
}

func listLength(values map[string]any, key string) int {
	items, _ := values[key].([]any)
	return len(items)
}

var _ application.Resolver = TravelContextResolver{}
