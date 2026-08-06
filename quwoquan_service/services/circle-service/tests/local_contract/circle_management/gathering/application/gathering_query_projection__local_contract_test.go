// readiness_case: get-gathering-local
// readiness_case: get-public-gathering-local
// readiness_case: list-gatherings-by-host-local
// readiness_case: list-gatherings-by-source-local
// readiness_case: list-gathering-applications-local
// readiness_case: list-gathering-roster-local
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-001
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-002
package application_test

import (
	"context"
	"encoding/json"
	"sort"
	"strings"
	"testing"
	"time"

	"quwoquan_service/runtime/operation"
	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
	app "quwoquan_service/services/circle-service/internal/circle_management/gathering/application"
)

func TestGatheringPublicAndPrivateProjectionRedaction(t *testing.T) {
	now := time.Date(2026, 8, 6, 4, 0, 0, 0, time.UTC)
	value := gatheringQueryFixture(now)
	reader := &gatheringQueryReaderDouble{records: []app.GatheringReadModel{value}}
	facade := app.NewGatheringQueryFacade(reader, func() time.Time { return now })

	public, err := facade.GetPublicGathering(context.Background(), app.GatheringIDQuery{GatheringID: value.ID})
	if err != nil {
		t.Fatalf("GetPublicGathering: %v", err)
	}
	if !public.Card.Schedule.StartAt.IsZero() ||
		!public.Card.Schedule.EndAt.IsZero() {
		t.Fatalf("after_join schedule leaked exact instants: %+v", public.Card.Schedule)
	}
	if public.Card.Place.ExactMeetingPoint != "" {
		t.Fatalf("after_join place leaked private location: %+v", public.Card.Place)
	}
	assertJSONOmits(t, public,
		"secret exact meeting point",
		"secret online room",
		"secret application answer",
		"secret rejection reason",
		"secret attendance evidence",
	)

	memberPublic, err := facade.GetPublicGathering(
		personaContext("persona-member"),
		app.GatheringIDQuery{GatheringID: value.ID},
	)
	if err != nil {
		t.Fatalf("GetPublicGathering member: %v", err)
	}
	if memberPublic.Card.Schedule.StartAt.IsZero() ||
		memberPublic.Card.Place.ExactMeetingPoint == "" ||
		memberPublic.ConversationID == "" {
		t.Fatalf("after_join disclosure was not released to active member: %+v", memberPublic)
	}
	if memberPublic.Card.CardDigest != public.Card.CardDigest {
		t.Fatalf("card digest varied by viewer: anonymous=%s member=%s",
			public.Card.CardDigest, memberPublic.Card.CardDigest)
	}

	private, err := facade.GetGathering(
		personaContext("persona-member"),
		app.GatheringIDQuery{GatheringID: value.ID},
	)
	if err != nil {
		t.Fatalf("GetGathering: %v", err)
	}
	if private.Place.ExactMeetingPoint != "secret exact meeting point" {
		t.Fatalf("authorized participant did not receive exact place: %+v", private.Place)
	}
	if private.ConversationID != "conversation-g1" {
		t.Fatalf("authorized participant did not receive conversation: %+v", private)
	}
	assertJSONOmits(t, private, "secret application answer", "secret rejection reason")

	if _, err := facade.GetGathering(
		personaContext("persona-outsider"),
		app.GatheringIDQuery{GatheringID: value.ID},
	); err == nil {
		t.Fatal("private detail must reject a persona without organizer or active participation")
	}
}

func TestGatheringDiscoveryCardNeverBroadcastsExactMeetingPoint(t *testing.T) {
	now := time.Date(2026, 8, 6, 4, 0, 0, 0, time.UTC)
	value := gatheringQueryFixture(now)
	value.PolicySet.DisclosurePolicy.PlaceDisclosure = "exact"

	card := app.ProjectPublicCard(value, now)
	if card.Place.ExactMeetingPoint != "" {
		t.Fatalf("discovery card leaked exact meeting point: %+v", card.Place)
	}
	if card.Place.CoarsePlaceLabel == "" {
		t.Fatalf("discovery card lost disclosure-safe coarse place: %+v", card.Place)
	}

	memberDetail := app.ProjectPublicDetail(value, "persona-member", now)
	if memberDetail.Card.Place.ExactMeetingPoint == "" {
		t.Fatalf("authorized member detail lost exact meeting point: %+v", memberDetail)
	}
}

func TestGatheringCapacityOneToOneMultiPersonAndReopenAreClockDerived(t *testing.T) {
	now := time.Date(2026, 8, 6, 4, 0, 0, 0, time.UTC)
	tests := []struct {
		name     string
		max      int
		active   int
		invited  int
		wantFull bool
	}{
		{name: "one_to_one", max: 2, active: 1, invited: 1, wantFull: true},
		{name: "multi_person", max: 5, active: 3, invited: 1, wantFull: false},
	}
	for _, current := range tests {
		t.Run(current.name, func(t *testing.T) {
			value := gatheringQueryFixture(now)
			value.PolicySet.CapacityPolicy.MaxParticipants = int64(current.max)
			value.Participations = nil
			for index := 0; index < current.active; index++ {
				value.Participations = append(value.Participations, app.ParticipationRecord{
					PersonaID: "active-" + string(rune('a'+index)), State: "active",
				})
			}
			for index := 0; index < current.invited; index++ {
				hold := now.Add(time.Hour)
				value.Participations = append(value.Participations, app.ParticipationRecord{
					PersonaID: "invited-" + string(rune('a'+index)), State: "invited_pending",
					SeatHoldUntil: hold,
				})
			}

			card := app.ProjectPublicCard(value, now)
			if card.Capacity.Full != current.wantFull ||
				card.Capacity.ActiveSeatCount != int64(current.active) ||
				card.Capacity.InvitedSeatHoldCount != int64(current.invited) {
				t.Fatalf("capacity=%+v", card.Capacity)
			}
		})
	}

	value := gatheringQueryFixture(now)
	value.PolicySet.CapacityPolicy.MaxParticipants = 2
	hold := now.Add(time.Hour)
	value.Participations = []app.ParticipationRecord{
		{PersonaID: "persona-host", State: "active"},
		{PersonaID: "persona-invite", State: "invited_pending", SeatHoldUntil: hold},
	}
	full := app.ProjectPublicCard(value, now)
	reopened := app.ProjectPublicCard(value, now.Add(2*time.Hour))
	if !full.Capacity.Full ||
		full.Admission.AdmissionState != "full" {
		t.Fatalf("full projection=%+v admission=%+v",
			full.Capacity, full.Admission)
	}
	if !full.Temporal.EvaluatedAt.Equal(now) || !full.Admission.EvaluatedAt.Equal(now) {
		t.Fatalf("derived slices did not share one clock: temporal=%s admission=%s now=%s",
			full.Temporal.EvaluatedAt, full.Admission.EvaluatedAt, now)
	}
	if reopened.Capacity.Full ||
		reopened.Capacity.RemainingSeats != 1 ||
		reopened.Admission.AdmissionState != "accepting" {
		t.Fatalf("reopened projection=%+v admission=%+v",
			reopened.Capacity, reopened.Admission)
	}
	if value.Participations[1].State != "invited_pending" {
		t.Fatal("projection mutated persisted participation to model reopen")
	}
}

func TestGatheringMultiDayInviteOnlyAndTemporalCTA(t *testing.T) {
	now := time.Date(2026, 8, 6, 4, 0, 0, 0, time.UTC)
	value := gatheringQueryFixture(now)
	value.PolicySet.DisclosurePolicy.TimeDisclosure = "date_only"
	card := app.ProjectPublicCard(value, now)
	if card.Schedule.DateLabel != "2026-08-07/2026-08-09" {
		t.Fatalf("multi-day date label=%v", card.Schedule.DateLabel)
	}

	value.PolicySet.AudiencePolicy = "invite_only"
	value.PolicySet.AdmissionPolicy = "invite_only"
	outsider := app.ProjectPublicDetail(value, "", now)
	if outsider.AdmissionPolicy != "invite_only" ||
		outsider.ViewerParticipationState != "" {
		t.Fatalf("invite-only outsider projection=%+v", outsider)
	}
	hold := now.Add(4 * time.Hour)
	value.Participations = append(value.Participations, app.ParticipationRecord{
		PersonaID: "persona-invited", State: "invited_pending", SeatHoldUntil: hold,
	})
	invited := app.ProjectPublicDetail(value, "persona-invited", now)
	if invited.ViewerParticipationState != "invited_pending" {
		t.Fatalf("invite-only invited projection=%+v", invited)
	}

	inProgressAt := value.Schedule.StartAt.Add(time.Hour)
	inProgress := app.ProjectPublicDetail(value, "persona-member", inProgressAt)
	if inProgress.Card.Temporal.TemporalPhase != "in_progress" ||
		inProgress.ConversationID != "conversation-g1" {
		t.Fatalf(
			"in-progress conversation=%q phase=%s",
			inProgress.ConversationID,
			inProgress.Card.Temporal.TemporalPhase,
		)
	}

	value.LifecycleStatus = "completed"
	value.Outcome = contract.GatheringOutcome{Status: "occurred", CalculatedAt: now}
	completed := app.ProjectPublicCard(value, value.Schedule.EndAt.Add(time.Hour))
	if completed.Temporal.TemporalPhase != "ended" ||
		completed.OutcomeStatus != "occurred" {
		t.Fatalf(
			"completed outcome=%s phase=%s",
			completed.OutcomeStatus,
			completed.Temporal.TemporalPhase,
		)
	}
}

func TestGatheringHostAndSourceKeysetsRemainStableWhenEarlierRowAppears(t *testing.T) {
	now := time.Date(2026, 8, 6, 4, 0, 0, 0, time.UTC)
	reader := &gatheringQueryReaderDouble{}
	for index := 1; index <= 3; index++ {
		value := gatheringQueryFixture(now)
		value.ID = "g" + string(rune('0'+index))
		hour := index
		if index == 3 {
			hour = 2 // Exercise the gatheringId tie-breaker at an identical startAt.
		}
		start := now.Add(time.Duration(hour) * time.Hour)
		end := start.Add(time.Hour)
		value.Schedule.StartAt, value.Schedule.EndAt = start, end
		reader.records = append(reader.records, value)
	}
	facade := app.NewGatheringQueryFacade(reader, func() time.Time { return now })

	first, err := facade.ListByHost(context.Background(), app.ListByHostQuery{
		Host: app.HostRef{SubjectKind: "persona", SubjectID: "host-subject"}, Limit: 2,
	})
	if err != nil {
		t.Fatalf("ListByHost first: %v", err)
	}
	if !first.HasMore || first.NextCursor == "" || gatheringIDs(first.Items) != "g1,g2" {
		t.Fatalf("first page=%+v", first)
	}

	inserted := gatheringQueryFixture(now)
	inserted.ID = "g0"
	insertedStart := now.Add(30 * time.Minute)
	insertedEnd := insertedStart.Add(time.Hour)
	inserted.Schedule.StartAt, inserted.Schedule.EndAt = insertedStart, insertedEnd
	reader.records = append(reader.records, inserted)

	second, err := facade.ListByHost(context.Background(), app.ListByHostQuery{
		Host:   app.HostRef{SubjectKind: "persona", SubjectID: "host-subject"},
		Cursor: first.NextCursor, Limit: 2,
	})
	if err != nil {
		t.Fatalf("ListByHost second: %v", err)
	}
	if second.HasMore || gatheringIDs(second.Items) != "g3" {
		t.Fatalf("keyset duplicated or skipped rows after earlier insert: %+v", second)
	}

	sourcePage, err := facade.ListBySource(context.Background(), app.ListBySourceQuery{
		Source: app.CanonicalObjectRef{ObjectTypeRef: "content.post", ObjectID: "post-1"},
		Limit:  2,
	})
	if err != nil || len(sourcePage.Items) != 2 {
		t.Fatalf("typed source list page=%+v err=%v", sourcePage, err)
	}
	if reader.lastSource.ObjectTypeRef != "content.post" || reader.lastSource.ObjectID != "post-1" {
		t.Fatalf("source reference was flattened or lost: %+v", reader.lastSource)
	}
}

func TestGatheringPublicListsExcludeUnlistedAndInviteOnlyCards(t *testing.T) {
	now := time.Date(2026, 8, 6, 4, 0, 0, 0, time.UTC)
	public := gatheringQueryFixture(now)
	public.ID = "g-public"
	unlisted := gatheringQueryFixture(now)
	unlisted.ID = "g-unlisted"
	unlisted.PolicySet.AudiencePolicy = "unlisted"
	inviteOnly := gatheringQueryFixture(now)
	inviteOnly.ID = "g-invite-only"
	inviteOnly.PolicySet.AudiencePolicy = "invite_only"
	reader := &gatheringQueryReaderDouble{
		records: []app.GatheringReadModel{public, unlisted, inviteOnly},
	}
	facade := app.NewGatheringQueryFacade(reader, func() time.Time { return now })

	byHost, err := facade.ListByHost(context.Background(), app.ListByHostQuery{
		Host:  app.HostRef{SubjectKind: "persona", SubjectID: "host-subject"},
		Limit: 10,
	})
	if err != nil {
		t.Fatalf("ListByHost: %v", err)
	}
	if gatheringIDs(byHost.Items) != "g-public" {
		t.Fatalf("non-public Gathering leaked into host discovery: %+v", byHost.Items)
	}

	bySource, err := facade.ListBySource(context.Background(), app.ListBySourceQuery{
		Source: app.CanonicalObjectRef{
			ObjectTypeRef: "content.post",
			ObjectID:      "post-1",
		},
		Limit: 10,
	})
	if err != nil {
		t.Fatalf("ListBySource: %v", err)
	}
	if gatheringIDs(bySource.Items) != "g-public" {
		t.Fatalf("non-public Gathering leaked into source discovery: %+v", bySource.Items)
	}
}

func TestGatheringApplicationAndRosterDisclosure(t *testing.T) {
	now := time.Date(2026, 8, 6, 4, 0, 0, 0, time.UTC)
	value := gatheringQueryFixture(now)
	reader := &gatheringQueryReaderDouble{records: []app.GatheringReadModel{value}}
	facade := app.NewGatheringQueryFacade(reader, func() time.Time { return now })

	applications, err := facade.ListApplications(
		personaContext("persona-host"),
		app.GatheringPageQuery{GatheringID: value.ID, Limit: 10},
	)
	if err != nil {
		t.Fatalf("ListApplications: %v", err)
	}
	if len(applications.Items) != 1 ||
		len(applications.Items[0].Answers) != 1 ||
		applications.Items[0].Answers[0].AnswerText != "secret application answer" {
		t.Fatalf("organizer application inbox=%+v", applications)
	}
	if _, err := facade.ListApplications(
		personaContext("persona-member"),
		app.GatheringPageQuery{GatheringID: value.ID},
	); err == nil {
		t.Fatal("non-organizer must not read application answers")
	}

	roster, err := facade.ListRoster(
		personaContext("persona-member"),
		app.GatheringPageQuery{GatheringID: value.ID, Limit: 10},
	)
	if err != nil {
		t.Fatalf("ListRoster: %v", err)
	}
	if len(roster.Items) != 2 {
		t.Fatalf("joined_members roster must contain active participants only: %+v", roster.Items)
	}
	assertJSONOmits(t, roster, "secret application answer", "secret rejection reason", "secret attendance evidence")

	value.PolicySet.DisclosurePolicy.RosterDisclosure = "count_only"
	reader.records[0] = value
	countOnly, err := facade.ListRoster(
		personaContext("persona-member"),
		app.GatheringPageQuery{GatheringID: value.ID, Limit: 10},
	)
	if err != nil || len(countOnly.Items) != 0 || countOnly.Capacity.ActiveSeatCount != 2 {
		t.Fatalf("count-only roster=%+v err=%v", countOnly, err)
	}
}

type gatheringQueryReaderDouble struct {
	records    []app.GatheringReadModel
	lastSource app.CanonicalObjectRef
}

func (reader *gatheringQueryReaderDouble) ReadGathering(
	_ context.Context,
	gatheringID string,
) (app.GatheringReadModel, bool, error) {
	for _, value := range reader.records {
		if value.ID == gatheringID {
			return value, true, nil
		}
	}
	return app.GatheringReadModel{}, false, nil
}

func (reader *gatheringQueryReaderDouble) ListByHost(
	_ context.Context,
	host app.HostRef,
	after app.PublicListPosition,
	limit int,
) ([]app.GatheringReadModel, error) {
	values := make([]app.GatheringReadModel, 0)
	for _, value := range reader.records {
		if value.HostBinding.HostSubjectKind == host.SubjectKind &&
			value.HostBinding.HostSubjectID == host.SubjectID &&
			publicPositionAfter(value, after) {
			values = append(values, value)
		}
	}
	sortGatherings(values)
	return limitGatherings(values, limit), nil
}

func (reader *gatheringQueryReaderDouble) ListBySource(
	_ context.Context,
	source app.CanonicalObjectRef,
	after app.PublicListPosition,
	limit int,
) ([]app.GatheringReadModel, error) {
	reader.lastSource = source
	values := make([]app.GatheringReadModel, 0)
	for _, value := range reader.records {
		if hasSource(value, source) && publicPositionAfter(value, after) {
			values = append(values, value)
		}
	}
	sortGatherings(values)
	return limitGatherings(values, limit), nil
}

func (reader *gatheringQueryReaderDouble) ListApplications(
	_ context.Context,
	query app.ApplicationReadQuery,
) ([]app.ParticipationRecord, error) {
	value, found, _ := reader.ReadGathering(context.Background(), query.GatheringID)
	if !found {
		return []app.ParticipationRecord{}, nil
	}
	items := make([]app.ParticipationRecord, 0)
	for _, participation := range value.Participations {
		if participation.State != "application_pending" || participation.ReviewExpectedBy.IsZero() {
			continue
		}
		if query.After.ReviewExpectedBy != nil &&
			!applicationPositionAfter(participation, query.After) {
			continue
		}
		participation.GatheringID = value.ID
		items = append(items, participation)
	}
	sort.Slice(items, func(left, right int) bool {
		if !items[left].ReviewExpectedBy.Equal(items[right].ReviewExpectedBy) {
			return items[left].ReviewExpectedBy.Before(items[right].ReviewExpectedBy)
		}
		if items[left].PersonaID != items[right].PersonaID {
			return items[left].PersonaID < items[right].PersonaID
		}
		return items[left].AttemptNo < items[right].AttemptNo
	})
	if len(items) > query.Limit {
		items = items[:query.Limit]
	}
	return items, nil
}

func (reader *gatheringQueryReaderDouble) ListRoster(
	_ context.Context,
	query app.RosterReadQuery,
) ([]app.ParticipationRecord, error) {
	value, found, _ := reader.ReadGathering(context.Background(), query.GatheringID)
	if !found {
		return []app.ParticipationRecord{}, nil
	}
	items := make([]app.ParticipationRecord, 0)
	for _, participation := range value.Participations {
		if query.ActiveOnly && participation.State != "active" {
			continue
		}
		if participation.PersonaID <= query.After.PersonaID {
			continue
		}
		participation.GatheringID = value.ID
		items = append(items, participation)
	}
	sort.Slice(items, func(left, right int) bool {
		return items[left].PersonaID < items[right].PersonaID
	})
	if len(items) > query.Limit {
		items = items[:query.Limit]
	}
	return items, nil
}

func gatheringQueryFixture(now time.Time) app.GatheringReadModel {
	title := "Multi-day Gathering"
	summary := "public summary"
	timezone := "Asia/Shanghai"
	start := time.Date(2026, 8, 7, 10, 0, 0, 0, time.FixedZone("CST", 8*60*60))
	end := time.Date(2026, 8, 9, 17, 0, 0, 0, time.FixedZone("CST", 8*60*60))
	admissionCloses := start.Add(-time.Hour)
	coarse := "Shanghai"
	exact := "secret exact meeting point"
	online := "secret online room"
	conversationID := "conversation-g1"
	revisionID := "revision-1"
	answer := "secret application answer"
	reviewExpectedBy := now.Add(time.Hour)
	joinedAt := now.Add(-time.Hour)
	declaredAt := now.Add(3 * time.Hour)
	return app.GatheringReadModel{
		ID: "g1", Version: 7, CreatedByPersonaID: "persona-host",
		HostBinding: contract.HostBinding{
			HostSubjectKind: "persona", HostSubjectID: "host-subject", AuthorityVersion: 11,
		},
		OrganizerAssignments: []contract.OrganizerAssignment{{
			PersonaID: "persona-host", Role: "owner", AssignedAt: now.Add(-24 * time.Hour),
		}},
		Purpose: contract.GatheringPurpose{
			Title: title, Summary: summary, TopicRefs: []string{"topic-1"},
			RequirementRefs: []string{"adult"},
			SourceObjectRefs: []contract.GatheringSourceRef{{
				ObjectRef: app.CanonicalObjectRef{
					ObjectTypeRef: "content.post", ObjectID: "post-1",
				},
				RouteID: "content_post_detail", SourceDigest: "source-digest",
			}},
			CostNotice: "free",
		},
		Schedule: contract.GatheringSchedule{
			Timezone: timezone, StartAt: start, EndAt: end, AdmissionClosesAt: admissionCloses,
		},
		Place: contract.GatheringPlace{
			Mode: "hybrid", CoarsePlaceLabel: coarse,
			ExactMeetingPoint: exact, OnlineLocationRef: online,
		},
		PolicySet: contract.GatheringPolicySet{
			AudiencePolicy: "public", AdmissionPolicy: "open",
			CapacityPolicy: contract.GatheringCapacityPolicy{MaxParticipants: 8},
			DisclosurePolicy: contract.GatheringDisclosurePolicy{
				TimeDisclosure: "after_join", PlaceDisclosure: "after_join",
				RosterDisclosure: "joined_members",
			},
			ApplicationQuestions: []contract.GatheringApplicationQuestion{{
				QuestionID: "q1", Prompt: "why", Kind: "text", Required: true,
				Options: []contract.GatheringApplicationQuestionOption{},
			}},
		},
		AdmissionControl:               contract.GatheringAdmissionControl{Status: "open", Version: 1},
		LifecycleStatus:                "published",
		ConversationID:                 conversationID,
		RoomBindingStatus:              "ready",
		CurrentGatheringRevisionID:     revisionID,
		CurrentGatheringRevisionNumber: 1,
		Participations: []app.ParticipationRecord{
			{
				PersonaID: "persona-host", State: "active", AdmissionSource: "open",
				JoinedAt: joinedAt, Version: 2,
				Attendance:                   contract.GatheringAttendance{Status: "not_declared"},
				CurrentChangeAcknowledgement: contract.GatheringRevisionAcknowledgement{Status: "not_required"},
			},
			{
				PersonaID: "persona-member", State: "active", AdmissionSource: "open",
				JoinedAt: joinedAt, Version: 3,
				ApplicationAnswers: []contract.GatheringApplicationAnswer{{
					QuestionID: "q1", AnswerText: answer, SelectedOptionIds: []string{},
				}},
				Attendance: contract.GatheringAttendance{
					Status: "arrived", DeclaredAt: declaredAt,
					EvidenceRefs: []app.CanonicalObjectRef{{
						ObjectTypeRef: "secret attendance evidence", ObjectID: "evidence-1",
					}},
				},
				CurrentChangeAcknowledgement: contract.GatheringRevisionAcknowledgement{Status: "accepted"},
			},
			{
				PersonaID: "persona-applicant", State: "application_pending",
				AdmissionSource: "application", AttemptNo: 1, ReviewExpectedBy: reviewExpectedBy,
				Version: 4, ClosedReason: "rejected",
				ApplicationAnswers: []contract.GatheringApplicationAnswer{{
					QuestionID: "q1", AnswerText: answer, SelectedOptionIds: []string{},
				}},
				Attendance:                   contract.GatheringAttendance{Status: "not_declared"},
				CurrentChangeAcknowledgement: contract.GatheringRevisionAcknowledgement{Status: "not_required"},
			},
		},
		Revisions: []contract.GatheringRevision{{
			RevisionID: revisionID, RevisionNumber: 1, Digest: "revision-digest", CreatedAt: now,
		}},
		CreatedAt: now.Add(-48 * time.Hour), UpdatedAt: now,
	}
}

func personaContext(personaID string) context.Context {
	return operation.WithContext(context.Background(), operation.Context{
		OperationID: "operation-query", RequestID: "request-query", TraceID: "trace-query",
		Actor: operation.ActorContext{PersonaID: personaID},
	})
}

func publicPositionAfter(value app.GatheringReadModel, after app.PublicListPosition) bool {
	if after.StartAt == nil {
		return true
	}
	if value.Schedule.StartAt.After(*after.StartAt) {
		return true
	}
	return value.Schedule.StartAt.Equal(*after.StartAt) && value.ID > after.GatheringID
}

func applicationPositionAfter(
	value app.ParticipationRecord,
	after app.ApplicationListPosition,
) bool {
	if value.ReviewExpectedBy.After(*after.ReviewExpectedBy) {
		return true
	}
	if !value.ReviewExpectedBy.Equal(*after.ReviewExpectedBy) {
		return false
	}
	if value.PersonaID != after.PersonaID {
		return value.PersonaID > after.PersonaID
	}
	return value.AttemptNo > after.AttemptNo
}

func sortGatherings(values []app.GatheringReadModel) {
	sort.Slice(values, func(left, right int) bool {
		if !values[left].Schedule.StartAt.Equal(values[right].Schedule.StartAt) {
			return values[left].Schedule.StartAt.Before(values[right].Schedule.StartAt)
		}
		return values[left].ID < values[right].ID
	})
}

func limitGatherings(values []app.GatheringReadModel, limit int) []app.GatheringReadModel {
	if len(values) > limit {
		return values[:limit]
	}
	return values
}

func hasSource(value app.GatheringReadModel, source app.CanonicalObjectRef) bool {
	for _, current := range value.Purpose.SourceObjectRefs {
		if current.ObjectRef == source {
			return true
		}
	}
	return false
}

func gatheringIDs(values []app.PublicCard) string {
	ids := make([]string, 0, len(values))
	for _, value := range values {
		ids = append(ids, value.GatheringID)
	}
	return strings.Join(ids, ",")
}

func assertJSONOmits(t *testing.T, value any, forbidden ...string) {
	t.Helper()
	encoded, err := json.Marshal(value)
	if err != nil {
		t.Fatalf("marshal projection: %v", err)
	}
	for _, secret := range forbidden {
		if strings.Contains(string(encoded), secret) {
			t.Fatalf("projection leaked %q: %s", secret, encoded)
		}
	}
}

var _ app.GatheringQueryReader = (*gatheringQueryReaderDouble)(nil)
