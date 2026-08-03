package identifier

import runtimeid "quwoquan_service/runtime/id"

type Generator struct{}

func (Generator) NewTripPlanID() (string, error) {
	return runtimeid.Generate(runtimeid.PrefixTripPlan)
}

func (Generator) NewRevisionID() (string, error) {
	return runtimeid.Generate(runtimeid.PrefixTripPlanRevision)
}

func (Generator) NewTripMembershipID() (string, error) {
	return runtimeid.Generate(runtimeid.PrefixTripMembership)
}

func (Generator) NewTripPlanPlacementID() (string, error) {
	return runtimeid.Generate(runtimeid.PrefixTripPlanPlacement)
}

func (Generator) NewTripMomentID() (string, error) {
	return runtimeid.Generate(runtimeid.PrefixTripMoment)
}

func (Generator) NewTripPlanContentLinkID() (string, error) {
	return runtimeid.Generate(runtimeid.PrefixTripPlanContentLink)
}

func (Generator) NewTripShareSnapshotID() (string, error) {
	return runtimeid.Generate(runtimeid.PrefixTripShareSnapshot)
}

func (Generator) NewTripPlanTemplateID() (string, error) {
	return runtimeid.Generate(runtimeid.PrefixTripPlanTemplate)
}

func (Generator) NewTripGuideAssignmentID() (string, error) {
	return runtimeid.Generate(runtimeid.PrefixTripGuideAssignment)
}

func (Generator) NewEventID() (string, error) {
	return runtimeid.Generate(runtimeid.PrefixTravelDomainEvent)
}
