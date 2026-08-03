package eventing

import "strings"

const (
	TripPlanStream            = "events.travel.trip_plan"
	TripPlanRevisionStream    = "events.travel.trip_plan_revision"
	TripMembershipStream      = "events.travel.trip_membership"
	TripPlanPlacementStream   = "events.travel.trip_plan_placement"
	TripMomentStream          = "events.travel.trip_moment"
	TripPlanContentLinkStream = "events.travel.trip_plan_content_link"
	TripShareSnapshotStream   = "events.travel.trip_share_snapshot"
	TripPlanTemplateStream    = "events.travel.trip_plan_template"
	TripGuideAssignmentStream = "events.travel.trip_guide_assignment"
)

type EventRoute struct {
	Stream        string
	AggregateType string
}

var eventRoutes = map[string]EventRoute{
	"TripPlanCreated":            {Stream: TripPlanStream, AggregateType: "TripPlan"},
	"TripPlanRevised":            {Stream: TripPlanStream, AggregateType: "TripPlan"},
	"TripPlanLifecycleChanged":   {Stream: TripPlanStream, AggregateType: "TripPlan"},
	"TripPlanRevisionAppended":   {Stream: TripPlanRevisionStream, AggregateType: "TripPlanRevision"},
	"TripMembershipChanged":      {Stream: TripMembershipStream, AggregateType: "TripMembership"},
	"TripPlanPlacementChanged":   {Stream: TripPlanPlacementStream, AggregateType: "TripPlanPlacement"},
	"TripMomentChanged":          {Stream: TripMomentStream, AggregateType: "TripMoment"},
	"TripPlanContentLinkChanged": {Stream: TripPlanContentLinkStream, AggregateType: "TripPlanContentLink"},
	"TripShareSnapshotCreated":   {Stream: TripShareSnapshotStream, AggregateType: "TripShareSnapshot"},
	"TripPlanTemplateChanged":    {Stream: TripPlanTemplateStream, AggregateType: "TripPlanTemplate"},
	"TripGuideAssignmentChanged": {Stream: TripGuideAssignmentStream, AggregateType: "TripGuideAssignment"},
}

func RouteForEvent(eventType string) (EventRoute, bool) {
	route, found := eventRoutes[strings.TrimSpace(eventType)]
	return route, found
}

func ProjectionStreams() []string {
	return []string{
		TripPlanStream,
		TripPlanRevisionStream,
		TripMomentStream,
		TripPlanContentLinkStream,
	}
}
