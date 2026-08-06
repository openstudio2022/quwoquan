// readiness_case: create-gathering-api
// readiness_case: publish-gathering-api
// readiness_case: join-gathering-api
// readiness_case: get-gathering-api
// readiness_case: approve-gathering-participant-api
// readiness_case: leave-gathering-api
// readiness_case: cancel-gathering-api
// readiness_case: complete-gathering-api
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-001
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-002
package gathering_test

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"

	"quwoquan_service/internal/platform/testinfra"
	"quwoquan_service/runtime/operation"
	gatheringevent "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/event"
	contract "quwoquan_service/services/circle-service/generated/circle_management/gathering/contract/model"
	gatheringhttp "quwoquan_service/services/circle-service/internal/circle_management/gathering/adapters/inbound/http"
	gatheringapp "quwoquan_service/services/circle-service/internal/circle_management/gathering/application"
	gatheringmodel "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/model"
	gatheringports "quwoquan_service/services/circle-service/internal/circle_management/gathering/domain/ports"
	gatheringpersistence "quwoquan_service/services/circle-service/internal/circle_management/gathering/infrastructure/persistence"
)

type targetReader struct{}

func (targetReader) RequireNavigable(
	context.Context,
	contract.GatheringSourceRef,
) error {
	return nil
}

type hostAuthorityReader struct{}

func (hostAuthorityReader) ReadHostAuthority(
	_ context.Context,
	query gatheringmodel.HostAuthorityQuery,
) (gatheringmodel.HostAuthorityEvidence, error) {
	return gatheringmodel.HostAuthorityEvidence{
		HostSubjectKind:      query.HostSubjectKind,
		HostSubjectID:        query.HostSubjectID,
		HostReference:        string(query.HostSubjectKind) + ":" + query.HostSubjectID,
		ActorPersonaID:       query.ActorPersonaID,
		OrganizerPersonaID:   query.OrganizerPersonaID,
		AuthorityEvidenceRef: query.AuthorityEvidenceRef,
		AuthorityVersion:     query.AuthorityVersion,
		AuthorityDigest:      "sha256:9aa880594bd115a7f265248a444d9eab4d86105e1ba6d46e6efd75620360ea4e",
		Action:               query.Action,
		Valid:                true,
		ExpiresAt:            query.EvaluatedAt.Add(time.Hour),
	}, nil
}

type safetyAuthorizer struct{}

func (safetyAuthorizer) AuthorizeSafetyTermination(
	context.Context,
	gatheringapp.GatheringSafetyTerminationAuthorizationRequest,
) error {
	return nil
}

type recordingAggregateStore struct {
	gatheringports.AggregateStore
	lastCommitError error
}

func (store *recordingAggregateStore) Commit(
	ctx context.Context,
	request gatheringports.CommitRequest,
) (gatheringports.CommitReceipt, error) {
	receipt, err := store.AggregateStore.Commit(ctx, request)
	store.lastCommitError = err
	return receipt, err
}

type gatheringVersionRequest struct {
	ExpectedGatheringVersion int64 `json:"expectedGatheringVersion"`
}

type gatheringAttendanceRequest struct {
	EvidenceRefs                 []contract.CanonicalObjectRef `json:"evidenceRefs"`
	ExpectedGatheringVersion     int64                         `json:"expectedGatheringVersion"`
	ExpectedParticipationVersion int64                         `json:"expectedParticipationVersion"`
}

type chatProjection struct {
	conversationIDs map[string]string
	ensureCalls     map[string]int
	roomCreations   map[string]int
}

func (projection *chatProjection) EnsureGatheringConversation(
	_ context.Context,
	command gatheringports.EnsureGatheringConversationCommand,
) (string, error) {
	if command.GatheringID == "" || command.SourceVersion <= 0 || command.SourceEventID == "" ||
		command.AccessMode == "" || command.PostingPolicy == "" {
		return "", errors.New("incomplete Gathering conversation projection")
	}
	if projection.conversationIDs == nil {
		projection.conversationIDs = make(map[string]string)
		projection.ensureCalls = make(map[string]int)
		projection.roomCreations = make(map[string]int)
	}
	projection.ensureCalls[command.GatheringID]++
	if conversationID, exists := projection.conversationIDs[command.GatheringID]; exists {
		return conversationID, nil
	}
	conversationID := "conversation-" + command.GatheringID
	projection.conversationIDs[command.GatheringID] = conversationID
	projection.roomCreations[command.GatheringID]++
	return conversationID, nil
}

func (*chatProjection) ProjectGatheringMembership(
	_ context.Context,
	command gatheringports.ProjectGatheringMembershipCommand,
) error {
	if command.PersonaID == "" || command.SourceType == "" ||
		command.SourceVersion <= 0 {
		return errors.New("incomplete Gathering membership projection")
	}
	return nil
}

func TestChatProjectionUsesStableUniqueConversationIDPerGathering(t *testing.T) {
	projection := &chatProjection{}
	command := gatheringports.EnsureGatheringConversationCommand{
		GatheringID:    "gathering-1",
		SourceEventID:  "gathering:gathering-1:room:v1",
		SourceVersion:  1,
		OwnerPersonaID: "persona-owner",
		Title:          "贡嘎同行",
		AccessMode:     "active",
		PostingPolicy:  "member_chat",
	}

	firstConversationID, err := projection.EnsureGatheringConversation(
		context.Background(),
		command,
	)
	if err != nil {
		t.Fatalf("ensure first Gathering room: %v", err)
	}
	replayedConversationID, err := projection.EnsureGatheringConversation(
		context.Background(),
		command,
	)
	if err != nil {
		t.Fatalf("replay first Gathering room: %v", err)
	}
	secondCommand := command
	secondCommand.GatheringID = "gathering-2"
	secondCommand.SourceEventID = "gathering:gathering-2:room:v1"
	secondConversationID, err := projection.EnsureGatheringConversation(
		context.Background(),
		secondCommand,
	)
	if err != nil {
		t.Fatalf("ensure second Gathering room: %v", err)
	}

	if firstConversationID != "conversation-gathering-1" ||
		replayedConversationID != firstConversationID ||
		secondConversationID != "conversation-gathering-2" ||
		secondConversationID == firstConversationID {
		t.Fatalf(
			"conversation identity drift: first=%q replay=%q second=%q",
			firstConversationID,
			replayedConversationID,
			secondConversationID,
		)
	}
	if projection.ensureCalls["gathering-1"] != 2 ||
		projection.roomCreations["gathering-1"] != 1 ||
		projection.roomCreations["gathering-2"] != 1 ||
		len(projection.conversationIDs) != 2 {
		t.Fatalf(
			"room creation idempotency drift: ensureCalls=%v roomCreations=%v conversations=%v",
			projection.ensureCalls,
			projection.roomCreations,
			projection.conversationIDs,
		)
	}
}

func TestGatheringHTTPPersistsCanonicalLifecycleParticipationAndQuery(
	t *testing.T,
) {
	ctx := context.Background()
	runtime, err := testinfra.StartRealMongo(
		ctx,
		"circle_gathering_api_integration",
	)
	if err != nil {
		t.Fatalf("start real Mongo replica set: %v", err)
	}
	t.Cleanup(func() {
		if closeErr := runtime.Close(context.Background()); closeErr != nil {
			t.Errorf("close real Mongo: %v", closeErr)
		}
	})

	store := gatheringpersistence.NewMongoAggregateStore(runtime.Database)
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatalf("ensure Gathering indexes: %v", err)
	}
	hostOutcome := gatheringapp.NewHostOutcomeFacade(store, hostAuthorityReader{})
	lifecycleStore := &recordingAggregateStore{AggregateStore: store}
	lifecycle := gatheringapp.NewLifecycleFacade(
		lifecycleStore,
		targetReader{},
		hostOutcome,
		hostOutcome,
		hostOutcome,
		safetyAuthorizer{},
	)
	participation := gatheringapp.NewCommandFacade(store)
	queries := gatheringapp.NewGatheringQueryFacade(
		gatheringpersistence.NewMongoGatheringQueryReader(runtime.Database),
		time.Now,
	)
	mux := http.NewServeMux()
	gatheringhttp.NewHandler(
		lifecycle,
		participation,
		hostOutcome,
		queries,
	).Register(mux)

	now := time.Now().UTC()
	createBody := map[string]any{
		"hostBinding": map[string]any{
			"hostSubjectKind": "persona", "hostSubjectId": "persona-owner",
			"authorityEvidenceRef": "authority/owner", "authorityVersion": 1,
			"authorityExpiresAt": now.Add(24 * time.Hour),
		},
		"creatorParticipates": true,
		"purpose": map[string]any{
			"title": "贡嘎日落同行", "summary": "一起完成公开、安全的徒步活动",
			"topicRefs": []string{}, "requirementRefs": []string{},
			"sourceObjectRefs": []any{}, "costNotice": "free",
		},
		"schedule": map[string]any{
			"timezone": "Asia/Shanghai", "startAt": now.Add(3 * time.Hour),
			"endAt":             now.Add(5 * time.Hour),
			"admissionClosesAt": now.Add(2 * time.Hour),
		},
		"place": map[string]any{
			"mode": "online", "onlineLocationRef": "room://gathering",
		},
		"policySet": map[string]any{
			"audiencePolicy": "public", "admissionPolicy": "open",
			"capacityPolicy": map[string]any{"maxParticipants": 4},
			"disclosurePolicy": map[string]any{
				"timeDisclosure": "exact", "placeDisclosure": "exact",
				"rosterDisclosure": "joined_members",
			},
			"applicationQuestions": []any{},
			"riskControlPolicyRef": "risk/default",
			"policyDecisionRef":    "policy/allow",
			"policyDigest":         "sha256:ca7acf0a841461bfd3e8d38fa0a80f7c7131dcc59c95d225f5c0987bfad35973",
			"obligationDigest":     "obligation-digest",
		},
	}
	created := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings",
		createBody,
		"persona-owner",
		"create-1",
	)
	if created.Code != http.StatusCreated {
		t.Fatalf("create status=%d body=%s storageErr=%v", created.Code, created.Body.String(), lifecycleStore.lastCommitError)
	}
	createdBody := decode(t, created)
	gatheringID, _ := createdBody["gatheringId"].(string)
	if gatheringID == "" || createdBody["roomBindingStatus"] != "pending" ||
		createdBody["conversationId"] != nil {
		t.Fatalf("draft bound a room synchronously: %#v", createdBody)
	}

	chat := &chatProjection{}
	reconciler := gatheringapp.NewReconciler(store, store, chat)
	if count, reconcileErr := reconciler.ReconcileOnce(ctx, 10); reconcileErr != nil ||
		count != 1 {
		t.Fatalf("reconcile room count=%d err=%v", count, reconcileErr)
	}
	current, found, err := store.Load(ctx, gatheringID)
	if err != nil || !found ||
		current.RoomBindingStatus != contract.GatheringRoomBindingStatusReady ||
		current.ConversationID != "conversation-"+gatheringID {
		t.Fatalf("load room-ready draft: found=%v value=%+v err=%v", found, current, err)
	}
	firstConversationID := current.ConversationID

	published := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+gatheringID+":publish",
		map[string]any{"expectedGatheringVersion": current.Version},
		"persona-owner",
		"publish-1",
	)
	if published.Code != http.StatusOK {
		t.Fatalf("publish status=%d body=%s", published.Code, published.Body.String())
	}
	current, _, _ = store.Load(ctx, gatheringID)
	joined := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+gatheringID+":join-open",
		map[string]any{
			"expectedGatheringVersion":     current.Version,
			"expectedParticipationVersion": 0,
		},
		"persona-member",
		"join-1",
	)
	if joined.Code != http.StatusOK {
		t.Fatalf("join status=%d body=%s", joined.Code, joined.Body.String())
	}
	current, _, _ = store.Load(ctx, gatheringID)
	invited := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+gatheringID+":invite",
		map[string]any{
			"participantPersonaId":         "persona-invitee",
			"expectedGatheringVersion":     current.Version,
			"expectedParticipationVersion": 0,
			"seatHoldUntil":                now.Add(time.Hour),
		},
		"persona-owner",
		"invite-1",
	)
	if invited.Code != http.StatusOK {
		t.Fatalf("invite status=%d body=%s", invited.Code, invited.Body.String())
	}
	invitedVersion, _ := decode(t, invited)["aggregateVersion"].(float64)
	for _, eventType := range []string{
		gatheringevent.GatheringParticipationChanged,
		gatheringevent.GatheringInvitationChanged,
	} {
		count, countErr := runtime.Database.Collection("gathering_outbox").CountDocuments(
			ctx,
			bson.M{
				"aggregateId":      gatheringID,
				"aggregateVersion": int64(invitedVersion),
				"eventType":        eventType,
			},
		)
		if countErr != nil || count != 1 {
			t.Fatalf(
				"invite outbox event=%s count=%d err=%v",
				eventType,
				count,
				countErr,
			)
		}
	}
	current, _, _ = store.Load(ctx, gatheringID)
	wrongRecipient := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+gatheringID+":accept-invitation",
		map[string]any{
			"expectedGatheringVersion":     current.Version,
			"expectedParticipationVersion": 0,
		},
		"persona-attacker",
		"accept-wrong-recipient-1",
	)
	if wrongRecipient.Code != http.StatusForbidden {
		t.Fatalf(
			"wrong recipient status=%d body=%s",
			wrongRecipient.Code,
			wrongRecipient.Body.String(),
		)
	}
	detail := execute(
		t,
		mux,
		http.MethodGet,
		"/gatherings/"+gatheringID,
		nil,
		"persona-member",
		"",
	)
	if detail.Code != http.StatusOK ||
		decode(t, detail)["gatheringId"] != gatheringID {
		t.Fatalf("detail status=%d body=%s", detail.Code, detail.Body.String())
	}

	current, _, _ = store.Load(ctx, gatheringID)
	left := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+gatheringID+":leave",
		map[string]any{
			"expectedGatheringVersion":     current.Version,
			"expectedParticipationVersion": participationVersion(t, current, "persona-member"),
		},
		"persona-member",
		"leave-1",
	)
	if left.Code != http.StatusOK {
		t.Fatalf("leave status=%d body=%s", left.Code, left.Body.String())
	}
	current, _, _ = store.Load(ctx, gatheringID)
	cancelled := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+gatheringID+":cancel",
		map[string]any{
			"expectedGatheringVersion": current.Version,
			"reasonRef":                "reason/organizer-cancelled",
			"evidenceRefs":             []any{},
		},
		"persona-owner",
		"cancel-1",
	)
	if cancelled.Code != http.StatusOK {
		t.Fatalf("cancel status=%d body=%s", cancelled.Code, cancelled.Body.String())
	}
	current, _, _ = store.Load(ctx, gatheringID)
	cancelledClick := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+gatheringID+":accept-invitation",
		map[string]any{
			"expectedGatheringVersion": current.Version,
			"expectedParticipationVersion": participationVersion(
				t,
				current,
				"persona-invitee",
			),
		},
		"persona-invitee",
		"accept-after-cancel-1",
	)
	if cancelledClick.Code != http.StatusConflict {
		t.Fatalf(
			"cancelled invitation click status=%d body=%s",
			cancelledClick.Code,
			cancelledClick.Body.String(),
		)
	}

	approvalBody := cloneJSONMap(t, createBody)
	approvalBody["purpose"].(map[string]any)["title"] = "贡嘎日落审核同行"
	approvalBody["policySet"].(map[string]any)["admissionPolicy"] = "approval"
	activityStart := time.Now().UTC().Add(15 * time.Second)
	activityEnd := activityStart.Add(5 * time.Second)
	approvalBody["schedule"] = gatheringScheduleBody(activityStart, activityEnd)
	approvalCreated := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings",
		approvalBody,
		"persona-owner",
		"create-approval-1",
	)
	if approvalCreated.Code != http.StatusCreated {
		t.Fatalf("create approval Gathering status=%d body=%s", approvalCreated.Code, approvalCreated.Body.String())
	}
	approvalID, _ := decode(t, approvalCreated)["gatheringId"].(string)
	if approvalID == "" {
		t.Fatal("approval Gathering id is empty")
	}
	if count, reconcileErr := reconciler.ReconcileOnce(ctx, 20); reconcileErr != nil || count < 1 {
		t.Fatalf("reconcile approval Gathering count=%d err=%v", count, reconcileErr)
	}
	approvalCurrent, found, loadErr := store.Load(ctx, approvalID)
	if loadErr != nil || !found ||
		approvalCurrent.RoomBindingStatus != contract.GatheringRoomBindingStatusReady {
		t.Fatalf(
			"load room-ready approval Gathering: found=%v value=%+v err=%v",
			found,
			approvalCurrent,
			loadErr,
		)
	}
	if approvalCurrent.ConversationID == firstConversationID {
		t.Fatalf(
			"different Gatherings shared conversationId %q: first=%s approval=%s",
			firstConversationID,
			gatheringID,
			approvalID,
		)
	}
	firstAfterRetry, firstFound, firstLoadErr := store.Load(ctx, gatheringID)
	if firstLoadErr != nil || !firstFound ||
		firstAfterRetry.ConversationID != firstConversationID {
		t.Fatalf(
			"Gathering retry rebound room: found=%v value=%+v wantConversationId=%q err=%v",
			firstFound,
			firstAfterRetry,
			firstConversationID,
			firstLoadErr,
		)
	}
	if chat.ensureCalls[gatheringID] < 2 ||
		chat.roomCreations[gatheringID] != 1 ||
		chat.roomCreations[approvalID] != 1 ||
		len(chat.conversationIDs) != 2 {
		t.Fatalf(
			"room ensure idempotency drift: ensureCalls=%v roomCreations=%v conversations=%v",
			chat.ensureCalls,
			chat.roomCreations,
			chat.conversationIDs,
		)
	}
	approvalPublished := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+approvalID+":publish",
		map[string]any{"expectedGatheringVersion": approvalCurrent.Version},
		"persona-owner",
		"publish-approval-1",
	)
	if approvalPublished.Code != http.StatusOK {
		t.Fatalf("publish approval Gathering status=%d body=%s", approvalPublished.Code, approvalPublished.Body.String())
	}
	approvalCurrent, _, _ = store.Load(ctx, approvalID)
	applied := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+approvalID+":apply",
		map[string]any{
			"expectedGatheringVersion":     approvalCurrent.Version,
			"expectedParticipationVersion": 0,
			"answers":                      []any{},
		},
		"persona-applicant",
		"apply-approval-1",
	)
	if applied.Code != http.StatusOK {
		t.Fatalf("apply status=%d body=%s", applied.Code, applied.Body.String())
	}
	approvalCurrent, _, _ = store.Load(ctx, approvalID)
	approved := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+approvalID+":review-application",
		map[string]any{
			"participantPersonaId":         "persona-applicant",
			"decision":                     "approve",
			"reasonRef":                    "review/approved",
			"expectedGatheringVersion":     approvalCurrent.Version,
			"expectedParticipationVersion": participationVersion(t, approvalCurrent, "persona-applicant"),
		},
		"persona-owner",
		"review-approval-1",
	)
	if approved.Code != http.StatusOK {
		t.Fatalf("approve status=%d body=%s", approved.Code, approved.Body.String())
	}

	unverifiedBody := cloneJSONMap(t, createBody)
	unverifiedBody["purpose"].(map[string]any)["title"] = "贡嘎日落待验证同行"
	unverifiedBody["schedule"] = gatheringScheduleBody(activityStart, activityEnd)
	unverifiedCreated := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings",
		unverifiedBody,
		"persona-owner",
		"create-unverified-1",
	)
	if unverifiedCreated.Code != http.StatusCreated {
		t.Fatalf(
			"create unverified Gathering status=%d body=%s",
			unverifiedCreated.Code,
			unverifiedCreated.Body.String(),
		)
	}
	unverifiedID, _ := decode(t, unverifiedCreated)["gatheringId"].(string)
	if unverifiedID == "" {
		t.Fatal("unverified Gathering id is empty")
	}
	if count, reconcileErr := reconciler.ReconcileOnce(ctx, 40); reconcileErr != nil || count < 1 {
		t.Fatalf("reconcile unverified Gathering count=%d err=%v", count, reconcileErr)
	}
	unverifiedCurrent, found, loadErr := store.Load(ctx, unverifiedID)
	if loadErr != nil || !found ||
		unverifiedCurrent.RoomBindingStatus != contract.GatheringRoomBindingStatusReady {
		t.Fatalf(
			"load room-ready unverified Gathering: found=%v value=%+v err=%v",
			found,
			unverifiedCurrent,
			loadErr,
		)
	}
	unverifiedPublished := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+unverifiedID+":publish",
		gatheringVersionRequest{ExpectedGatheringVersion: unverifiedCurrent.Version},
		"persona-owner",
		"publish-unverified-1",
	)
	if unverifiedPublished.Code != http.StatusOK {
		t.Fatalf(
			"publish unverified Gathering status=%d body=%s",
			unverifiedPublished.Code,
			unverifiedPublished.Body.String(),
		)
	}

	waitUntil(t, activityStart.Add(100*time.Millisecond))
	if !time.Now().UTC().Before(activityEnd) {
		t.Fatalf(
			"Gathering setup missed in-progress window: now=%s endAt=%s",
			time.Now().UTC(),
			activityEnd,
		)
	}
	approvalCurrent, _, _ = store.Load(ctx, approvalID)
	arrived := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+approvalID+":declare-arrival",
		gatheringAttendanceRequest{
			EvidenceRefs: []contract.CanonicalObjectRef{{
				ObjectTypeRef: "circle.check_in",
				ObjectID:      "arrival-persona-applicant",
			}},
			ExpectedGatheringVersion: approvalCurrent.Version,
			ExpectedParticipationVersion: participationVersion(
				t,
				approvalCurrent,
				"persona-applicant",
			),
		},
		"persona-applicant",
		"arrival-approval-1",
	)
	if arrived.Code != http.StatusOK {
		t.Fatalf("arrival status=%d body=%s", arrived.Code, arrived.Body.String())
	}
	approvalCurrent, _, _ = store.Load(ctx, approvalID)
	ownerArrived := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+approvalID+":declare-arrival",
		gatheringAttendanceRequest{
			EvidenceRefs: []contract.CanonicalObjectRef{{
				ObjectTypeRef: "circle.check_in",
				ObjectID:      "arrival-persona-owner",
			}},
			ExpectedGatheringVersion:     approvalCurrent.Version,
			ExpectedParticipationVersion: participationVersion(t, approvalCurrent, "persona-owner"),
		},
		"persona-owner",
		"arrival-owner-approval-1",
	)
	if ownerArrived.Code != http.StatusOK {
		t.Fatalf(
			"owner arrival status=%d body=%s",
			ownerArrived.Code,
			ownerArrived.Body.String(),
		)
	}

	waitUntil(t, activityEnd.Add(100*time.Millisecond))
	unverifiedCurrent, _, _ = store.Load(ctx, unverifiedID)
	unverifiedComplete := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+unverifiedID+":complete",
		gatheringVersionRequest{ExpectedGatheringVersion: unverifiedCurrent.Version},
		"persona-owner",
		"complete-unverified-1",
	)
	unverifiedError := decode(t, unverifiedComplete)
	if unverifiedComplete.Code != http.StatusConflict ||
		unverifiedError["code"] != "CIRCLE.USER.gathering_outcome_unverified" {
		t.Fatalf(
			"unverified complete status=%d body=%s",
			unverifiedComplete.Code,
			unverifiedComplete.Body.String(),
		)
	}
	unverifiedAfter, found, loadErr := store.Load(ctx, unverifiedID)
	if loadErr != nil || !found ||
		unverifiedAfter.Version != unverifiedCurrent.Version ||
		unverifiedAfter.LifecycleStatus != contract.GatheringLifecycleStatusPublished ||
		unverifiedAfter.Outcome.Status != "" {
		t.Fatalf(
			"unverified completion mutated state: found=%v before=%+v after=%+v err=%v",
			found,
			unverifiedCurrent,
			unverifiedAfter,
			loadErr,
		)
	}

	approvalCurrent, _, _ = store.Load(ctx, approvalID)
	selfCompleted := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+approvalID+":complete-self",
		gatheringAttendanceRequest{
			EvidenceRefs: []contract.CanonicalObjectRef{{
				ObjectTypeRef: "circle.completion",
				ObjectID:      "completion-persona-applicant",
			}},
			ExpectedGatheringVersion: approvalCurrent.Version,
			ExpectedParticipationVersion: participationVersion(
				t,
				approvalCurrent,
				"persona-applicant",
			),
		},
		"persona-applicant",
		"complete-self-approval-1",
	)
	if selfCompleted.Code != http.StatusOK {
		t.Fatalf(
			"complete self status=%d body=%s",
			selfCompleted.Code,
			selfCompleted.Body.String(),
		)
	}
	approvalCurrent, _, _ = store.Load(ctx, approvalID)
	ownerCompleted := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+approvalID+":complete-self",
		gatheringAttendanceRequest{
			EvidenceRefs: []contract.CanonicalObjectRef{{
				ObjectTypeRef: "circle.completion",
				ObjectID:      "completion-persona-owner",
			}},
			ExpectedGatheringVersion:     approvalCurrent.Version,
			ExpectedParticipationVersion: participationVersion(t, approvalCurrent, "persona-owner"),
		},
		"persona-owner",
		"complete-self-owner-approval-1",
	)
	if ownerCompleted.Code != http.StatusOK {
		t.Fatalf(
			"owner complete self status=%d body=%s",
			ownerCompleted.Code,
			ownerCompleted.Body.String(),
		)
	}
	approvalCurrent, _, _ = store.Load(ctx, approvalID)
	completed := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+approvalID+":complete",
		gatheringVersionRequest{ExpectedGatheringVersion: approvalCurrent.Version},
		"persona-owner",
		"complete-approval-1",
	)
	completedBody := decode(t, completed)
	if completed.Code != http.StatusOK ||
		completedBody["lifecycleStatus"] != "completed" ||
		completedBody["outcomeStatus"] != "occurred" {
		t.Fatalf("complete status=%d body=%s", completed.Code, completed.Body.String())
	}
	completedCurrent, found, loadErr := store.Load(ctx, approvalID)
	if loadErr != nil || !found ||
		completedCurrent.Outcome.Status != contract.GatheringOutcomeStatusOccurred ||
		completedCurrent.Outcome.IndependentEvidenceCount != 2 ||
		len(completedCurrent.Outcome.EvidenceRefs) != 4 ||
		completedCurrent.Outcome.CalculatedAt.IsZero() ||
		completedCurrent.Outcome.CalculationDigest == "" {
		t.Fatalf(
			"canonical occurred Outcome was not persisted: found=%v value=%+v err=%v",
			found,
			completedCurrent,
			loadErr,
		)
	}
}

func participationVersion(
	t *testing.T,
	value gatheringmodel.Gathering,
	personaID string,
) int64 {
	t.Helper()
	for _, participation := range value.Participations {
		if participation.PersonaID == personaID {
			return participation.Version
		}
	}
	t.Fatalf("participation for %s is missing", personaID)
	return 0
}

func cloneJSONMap(t *testing.T, source map[string]any) map[string]any {
	t.Helper()
	encoded, err := json.Marshal(source)
	if err != nil {
		t.Fatalf("clone JSON map marshal: %v", err)
	}
	var cloned map[string]any
	if err := json.Unmarshal(encoded, &cloned); err != nil {
		t.Fatalf("clone JSON map unmarshal: %v", err)
	}
	return cloned
}

func gatheringScheduleBody(startAt time.Time, endAt time.Time) map[string]any {
	return map[string]any{
		"timezone":          "Asia/Shanghai",
		"startAt":           startAt,
		"endAt":             endAt,
		"admissionClosesAt": startAt.Add(-time.Second),
	}
}

func waitUntil(t *testing.T, target time.Time) {
	t.Helper()
	if delay := time.Until(target); delay > 0 {
		timer := time.NewTimer(delay)
		defer timer.Stop()
		<-timer.C
	}
}

func execute(
	t *testing.T,
	handler http.Handler,
	method string,
	path string,
	body any,
	personaID string,
	idempotencyKey string,
) *httptest.ResponseRecorder {
	t.Helper()
	var encoded []byte
	if body != nil {
		var err error
		encoded, err = json.Marshal(body)
		if err != nil {
			t.Fatalf("marshal request: %v", err)
		}
	}
	request := httptest.NewRequest(method, path, bytes.NewReader(encoded))
	request.Header.Set("Content-Type", "application/json")
	request = request.WithContext(operation.WithContext(
		request.Context(),
		operation.Context{
			OperationID:    "GatheringApiIntegration",
			RequestID:      "request-" + personaID,
			TraceID:        "trace-" + personaID,
			IdempotencyKey: idempotencyKey,
			Actor:          operation.ActorContext{PersonaID: personaID},
		},
	))
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, request)
	return recorder
}

func decode(
	t *testing.T,
	recorder *httptest.ResponseRecorder,
) map[string]any {
	t.Helper()
	var value map[string]any
	if err := json.Unmarshal(recorder.Body.Bytes(), &value); err != nil {
		t.Fatalf("decode response: %v body=%s", err, recorder.Body.String())
	}
	return value
}
