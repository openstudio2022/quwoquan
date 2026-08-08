// readiness_case: publish-gathering-api
// readiness_case: update-gathering-api
// readiness_case: apply-to-gathering-api
// readiness_case: withdraw-gathering-application-api
// readiness_case: invite-to-gathering-api
// readiness_case: accept-gathering-invitation-api
// readiness_case: decline-gathering-invitation-api
// readiness_case: revoke-gathering-invitation-api
// readiness_case: get-public-gathering-api
// readiness_case: list-gathering-applications-api
// readiness_case: list-gathering-roster-api
// readiness_case: remove-gathering-participant-api
// readiness_case: reinstate-gathering-participant-api
// readiness_case: pause-gathering-admission-api
// readiness_case: resume-gathering-admission-api
// readiness_case: change-gathering-capacity-api
// readiness_case: acknowledge-gathering-revision-api
// readiness_case: declare-gathering-arrival-api
// readiness_case: complete-gathering-self-api
// readiness_case: end-gathering-early-api
// readiness_case: safety-terminate-gathering-api
// readiness_case: assign-gathering-co-host-api
// readiness_case: watch-gathering-availability-api
// readiness_case: unwatch-gathering-availability-api
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-001
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-002
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-003
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-008
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-001
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-002
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-004
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-005
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-006
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-007
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-012
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-participant-roster/spec.md#gwt-013
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-conversation-binding/spec.md#gwt-001
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/spec.md#sit-002
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/spec.md#sit-003
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
	gatheringerrors "quwoquan_service/services/circle-service/generated/circle_management/gathering"
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
	_ context.Context,
	request gatheringapp.GatheringSafetyTerminationAuthorizationRequest,
) error {
	if request.ActorPersonaID != "persona-safety" ||
		request.Action != gatheringapp.GatheringSafetyTerminationAction ||
		request.EvidenceRef != "content.report/report-safety-1" ||
		request.DecisionRef != "safety/terminate" {
		return gatheringerrors.ErrGatheringSafetyTerminationDenied
	}
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
	createReplay := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings",
		createBody,
		"persona-owner",
		"create-1",
	)
	createReplayBody := decode(t, createReplay)
	if createReplay.Code != http.StatusCreated ||
		createReplayBody["idempotentReplay"] != true ||
		createReplayBody["gatheringId"] != gatheringID ||
		createReplayBody["aggregateVersion"] != createdBody["aggregateVersion"] {
		t.Fatalf(
			"create replay status=%d body=%s",
			createReplay.Code,
			createReplay.Body.String(),
		)
	}
	conflictingCreateBody := cloneJSONMap(t, createBody)
	conflictingCreateBody["purpose"].(map[string]any)["title"] = "冲突草稿不得创建"
	conflictingCreate := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings",
		conflictingCreateBody,
		"persona-owner",
		"create-1",
	)
	if conflictingCreate.Code != http.StatusConflict {
		t.Fatalf(
			"conflicting create replay status=%d body=%s",
			conflictingCreate.Code,
			conflictingCreate.Body.String(),
		)
	}
	createdAfterConflict, found, loadErr := store.Load(ctx, gatheringID)
	if loadErr != nil || !found || createdAfterConflict.Version != int64(createdBody["aggregateVersion"].(float64)) ||
		createdAfterConflict.Purpose.Title != "贡嘎日落同行" {
		t.Fatalf(
			"conflicting create mutated draft: found=%v value=%+v err=%v",
			found,
			createdAfterConflict,
			loadErr,
		)
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
	updatedPurpose := current.Purpose
	updatedPurpose.Title = "贡嘎日落同行（路线更新）"
	updateBody := map[string]any{
		"expectedGatheringVersion":  current.Version,
		"purpose":                   updatedPurpose,
		"schedule":                  current.Schedule,
		"place":                     current.Place,
		"policySet":                 current.PolicySet,
		"hostBinding":               current.HostBinding,
		"acknowledgementDeadlineAt": now.Add(90 * time.Minute),
	}
	updated := execute(
		t,
		mux,
		http.MethodPut,
		"/gatherings/"+gatheringID,
		updateBody,
		"persona-owner",
		"update-1",
	)
	updatedBody := decode(t, updated)
	if updated.Code != http.StatusOK ||
		updatedBody["currentGatheringRevisionNumber"] != float64(2) {
		t.Fatalf("update status=%d body=%s", updated.Code, updated.Body.String())
	}
	updatedVersion := updatedBody["aggregateVersion"]
	updateReplay := execute(
		t,
		mux,
		http.MethodPut,
		"/gatherings/"+gatheringID,
		updateBody,
		"persona-owner",
		"update-1",
	)
	updateReplayBody := decode(t, updateReplay)
	if updateReplay.Code != http.StatusOK ||
		updateReplayBody["idempotentReplay"] != true ||
		updateReplayBody["aggregateVersion"] != updatedVersion {
		t.Fatalf(
			"update replay status=%d body=%s",
			updateReplay.Code,
			updateReplay.Body.String(),
		)
	}
	staleUpdate := execute(
		t,
		mux,
		http.MethodPut,
		"/gatherings/"+gatheringID,
		updateBody,
		"persona-owner",
		"update-stale-1",
	)
	if staleUpdate.Code != http.StatusConflict {
		t.Fatalf(
			"stale update status=%d body=%s",
			staleUpdate.Code,
			staleUpdate.Body.String(),
		)
	}
	current, _, _ = store.Load(ctx, gatheringID)
	draftPublic := execute(
		t,
		mux,
		http.MethodGet,
		"/public/gatherings/"+gatheringID,
		nil,
		"",
		"",
	)
	if draftPublic.Code != http.StatusNotFound {
		t.Fatalf(
			"draft public detail status=%d body=%s",
			draftPublic.Code,
			draftPublic.Body.String(),
		)
	}

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
	publicDetail := execute(
		t,
		mux,
		http.MethodGet,
		"/public/gatherings/"+gatheringID,
		nil,
		"",
		"",
	)
	publicDetailBody := decode(t, publicDetail)
	publicCard, _ := publicDetailBody["card"].(map[string]any)
	publicPurpose, _ := publicCard["purpose"].(map[string]any)
	if publicDetail.Code != http.StatusOK ||
		publicCard["gatheringId"] != gatheringID ||
		publicCard["lifecycleStatus"] != "published" ||
		publicPurpose["title"] != "贡嘎日落同行（路线更新）" ||
		publicDetailBody["conversationId"] != nil {
		t.Fatalf(
			"public detail disclosure drift status=%d body=%s",
			publicDetail.Code,
			publicDetail.Body.String(),
		)
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
	joinedBody := decode(t, joined)
	joinReplay := execute(
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
	joinReplayBody := decode(t, joinReplay)
	if joinReplay.Code != http.StatusOK ||
		joinReplayBody["idempotentReplay"] != true ||
		joinReplayBody["aggregateVersion"] != joinedBody["aggregateVersion"] {
		t.Fatalf("join replay status=%d body=%s", joinReplay.Code, joinReplay.Body.String())
	}
	current, _, _ = store.Load(ctx, gatheringID)
	duplicateJoin := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+gatheringID+":join-open",
		map[string]any{
			"expectedGatheringVersion":     current.Version,
			"expectedParticipationVersion": participationVersion(t, current, "persona-member"),
		},
		"persona-member",
		"join-duplicate-1",
	)
	if duplicateJoin.Code != http.StatusConflict {
		t.Fatalf("duplicate join status=%d body=%s", duplicateJoin.Code, duplicateJoin.Body.String())
	}
	currentAfterDuplicateJoin, found, loadErr := store.Load(ctx, gatheringID)
	if loadErr != nil || !found || currentAfterDuplicateJoin.Version != current.Version ||
		countParticipations(currentAfterDuplicateJoin, "persona-member") != 1 {
		t.Fatalf(
			"duplicate join produced partial state: found=%v before=%+v after=%+v err=%v",
			found,
			current,
			currentAfterDuplicateJoin,
			loadErr,
		)
	}
	capacityBody := map[string]any{
		"maxParticipants":           6,
		"expectedGatheringVersion":  current.Version,
		"acknowledgementDeadlineAt": now.Add(90 * time.Minute),
	}
	unauthorizedCapacity := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+gatheringID+":change-capacity",
		capacityBody,
		"persona-attacker",
		"change-capacity-unauthorized-1",
	)
	if unauthorizedCapacity.Code != http.StatusForbidden {
		t.Fatalf(
			"unauthorized capacity status=%d body=%s",
			unauthorizedCapacity.Code,
			unauthorizedCapacity.Body.String(),
		)
	}
	staleCapacityBody := cloneJSONMap(t, capacityBody)
	staleCapacityBody["expectedGatheringVersion"] = current.Version - 1
	staleCapacity := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+gatheringID+":change-capacity",
		staleCapacityBody,
		"persona-owner",
		"change-capacity-stale-1",
	)
	if staleCapacity.Code != http.StatusConflict {
		t.Fatalf(
			"stale capacity status=%d body=%s",
			staleCapacity.Code,
			staleCapacity.Body.String(),
		)
	}
	belowOccupiedBody := cloneJSONMap(t, capacityBody)
	belowOccupiedBody["maxParticipants"] = 1
	belowOccupied := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+gatheringID+":change-capacity",
		belowOccupiedBody,
		"persona-owner",
		"change-capacity-below-occupied-1",
	)
	if belowOccupied.Code != http.StatusConflict ||
		decode(t, belowOccupied)["code"] != "CIRCLE.USER.gathering_capacity_below_occupied_seats" {
		t.Fatalf(
			"below occupied capacity status=%d body=%s",
			belowOccupied.Code,
			belowOccupied.Body.String(),
		)
	}
	capacityChanged := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+gatheringID+":change-capacity",
		capacityBody,
		"persona-owner",
		"change-capacity-1",
	)
	capacityChangedBody := decode(t, capacityChanged)
	if capacityChanged.Code != http.StatusOK ||
		capacityChangedBody["currentGatheringRevisionNumber"] != float64(3) {
		t.Fatalf(
			"change capacity status=%d body=%s",
			capacityChanged.Code,
			capacityChanged.Body.String(),
		)
	}
	capacityVersion := capacityChangedBody["aggregateVersion"]
	capacityReplay := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+gatheringID+":change-capacity",
		capacityBody,
		"persona-owner",
		"change-capacity-1",
	)
	capacityReplayBody := decode(t, capacityReplay)
	if capacityReplay.Code != http.StatusOK ||
		capacityReplayBody["idempotentReplay"] != true ||
		capacityReplayBody["aggregateVersion"] != capacityVersion {
		t.Fatalf(
			"change capacity replay status=%d body=%s",
			capacityReplay.Code,
			capacityReplay.Body.String(),
		)
	}
	current, _, _ = store.Load(ctx, gatheringID)
	if current.PolicySet.CapacityPolicy.MaxParticipants != 6 {
		t.Fatalf("capacity was not persisted: %+v", current.PolicySet.CapacityPolicy)
	}
	memberIndex := gatheringmodel.ParticipationIndex(current.Participations, "persona-member")
	if memberIndex < 0 {
		t.Fatal("member participation is missing after capacity change")
	}
	memberAcknowledgement := current.Participations[memberIndex].CurrentChangeAcknowledgement
	if memberAcknowledgement.Status != contract.GatheringRevisionAcknowledgementStatusPending ||
		memberAcknowledgement.RevisionID != current.CurrentGatheringRevisionID ||
		memberAcknowledgement.RevisionDigest == "" {
		t.Fatalf(
			"material capacity revision did not require exact acknowledgement: %+v",
			memberAcknowledgement,
		)
	}
	acknowledgementBody := map[string]any{
		"revisionId":                   memberAcknowledgement.RevisionID,
		"revisionDigest":               memberAcknowledgement.RevisionDigest,
		"decision":                     "accept",
		"expectedGatheringVersion":     current.Version,
		"expectedParticipationVersion": current.Participations[memberIndex].Version,
	}
	unauthorizedAcknowledgement := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+gatheringID+":acknowledge-revision",
		acknowledgementBody,
		"persona-attacker",
		"acknowledge-revision-unauthorized-1",
	)
	if unauthorizedAcknowledgement.Code != http.StatusForbidden {
		t.Fatalf(
			"unauthorized acknowledgement status=%d body=%s",
			unauthorizedAcknowledgement.Code,
			unauthorizedAcknowledgement.Body.String(),
		)
	}
	staleAcknowledgementBody := cloneJSONMap(t, acknowledgementBody)
	staleAcknowledgementBody["expectedGatheringVersion"] = current.Version - 1
	staleAcknowledgement := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+gatheringID+":acknowledge-revision",
		staleAcknowledgementBody,
		"persona-member",
		"acknowledge-revision-stale-1",
	)
	if staleAcknowledgement.Code != http.StatusConflict {
		t.Fatalf(
			"stale acknowledgement status=%d body=%s",
			staleAcknowledgement.Code,
			staleAcknowledgement.Body.String(),
		)
	}
	wrongDigestBody := cloneJSONMap(t, acknowledgementBody)
	wrongDigestBody["revisionDigest"] = "sha256:de8d20ade3cdd0ce9a2159929b3e60b124fe3989395216ab0640c14780c7b9e7"
	wrongDigestAcknowledgement := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+gatheringID+":acknowledge-revision",
		wrongDigestBody,
		"persona-member",
		"acknowledge-revision-wrong-digest-1",
	)
	if wrongDigestAcknowledgement.Code != http.StatusConflict ||
		decode(t, wrongDigestAcknowledgement)["code"] != "CIRCLE.USER.gathering_reconfirmation_required" {
		t.Fatalf(
			"wrong digest acknowledgement status=%d body=%s",
			wrongDigestAcknowledgement.Code,
			wrongDigestAcknowledgement.Body.String(),
		)
	}
	acknowledged := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+gatheringID+":acknowledge-revision",
		acknowledgementBody,
		"persona-member",
		"acknowledge-revision-1",
	)
	acknowledgedBody := decode(t, acknowledged)
	if acknowledged.Code != http.StatusOK ||
		acknowledgedBody["participationState"] != "active" {
		t.Fatalf(
			"acknowledge revision status=%d body=%s",
			acknowledged.Code,
			acknowledged.Body.String(),
		)
	}
	acknowledgedVersion := acknowledgedBody["aggregateVersion"]
	acknowledgementReplay := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+gatheringID+":acknowledge-revision",
		acknowledgementBody,
		"persona-member",
		"acknowledge-revision-1",
	)
	acknowledgementReplayBody := decode(t, acknowledgementReplay)
	if acknowledgementReplay.Code != http.StatusOK ||
		acknowledgementReplayBody["idempotentReplay"] != true ||
		acknowledgementReplayBody["aggregateVersion"] != acknowledgedVersion {
		t.Fatalf(
			"acknowledge revision replay status=%d body=%s",
			acknowledgementReplay.Code,
			acknowledgementReplay.Body.String(),
		)
	}
	current, _, _ = store.Load(ctx, gatheringID)
	memberIndex = gatheringmodel.ParticipationIndex(current.Participations, "persona-member")
	if memberIndex < 0 ||
		current.Participations[memberIndex].CurrentChangeAcknowledgement.Status !=
			contract.GatheringRevisionAcknowledgementStatusAccepted {
		t.Fatalf("accepted revision acknowledgement was not persisted: %+v", current.Participations)
	}
	unauthorizedRoster := execute(
		t,
		mux,
		http.MethodGet,
		"/gatherings/"+gatheringID+"/roster?limit=1",
		nil,
		"persona-attacker",
		"",
	)
	if unauthorizedRoster.Code != http.StatusForbidden {
		t.Fatalf(
			"unauthorized roster status=%d body=%s",
			unauthorizedRoster.Code,
			unauthorizedRoster.Body.String(),
		)
	}
	rosterFirst := execute(
		t,
		mux,
		http.MethodGet,
		"/gatherings/"+gatheringID+"/roster?limit=1",
		nil,
		"persona-member",
		"",
	)
	rosterFirstBody := decode(t, rosterFirst)
	rosterFirstItems, _ := rosterFirstBody["items"].([]any)
	rosterCursor, _ := rosterFirstBody["nextCursor"].(string)
	rosterCapacity, _ := rosterFirstBody["capacity"].(map[string]any)
	if rosterFirst.Code != http.StatusOK ||
		len(rosterFirstItems) != 1 ||
		rosterFirstBody["hasMore"] != true ||
		rosterCursor == "" ||
		rosterCapacity["activeSeatCount"] != float64(2) {
		t.Fatalf(
			"first roster page status=%d body=%s",
			rosterFirst.Code,
			rosterFirst.Body.String(),
		)
	}
	rosterFirstItem, _ := rosterFirstItems[0].(map[string]any)
	rosterSecond := execute(
		t,
		mux,
		http.MethodGet,
		"/gatherings/"+gatheringID+"/roster?limit=1&cursor="+rosterCursor,
		nil,
		"persona-member",
		"",
	)
	rosterSecondBody := decode(t, rosterSecond)
	rosterSecondItems, _ := rosterSecondBody["items"].([]any)
	if rosterSecond.Code != http.StatusOK ||
		len(rosterSecondItems) != 1 ||
		rosterSecondBody["hasMore"] != false {
		t.Fatalf(
			"second roster page status=%d body=%s",
			rosterSecond.Code,
			rosterSecond.Body.String(),
		)
	}
	rosterSecondItem, _ := rosterSecondItems[0].(map[string]any)
	if rosterFirstItem["personaId"] == "" ||
		rosterSecondItem["personaId"] == "" ||
		rosterFirstItem["personaId"] == rosterSecondItem["personaId"] ||
		rosterFirstItem["state"] != "active" ||
		rosterSecondItem["state"] != "active" {
		t.Fatalf(
			"roster keyset/state drift: first=%+v second=%+v",
			rosterFirstItem,
			rosterSecondItem,
		)
	}
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
	revokeInvite := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+gatheringID+":invite",
		map[string]any{
			"participantPersonaId":         "persona-revoke",
			"expectedGatheringVersion":     current.Version,
			"expectedParticipationVersion": 0,
			"seatHoldUntil":                now.Add(time.Hour),
		},
		"persona-owner",
		"invite-revoke-1",
	)
	if revokeInvite.Code != http.StatusOK {
		t.Fatalf(
			"invite for revoke status=%d body=%s",
			revokeInvite.Code,
			revokeInvite.Body.String(),
		)
	}
	current, _, _ = store.Load(ctx, gatheringID)
	revokeBody := map[string]any{
		"participantPersonaId":         "persona-revoke",
		"reasonRef":                    "invitation/host-revoked",
		"expectedGatheringVersion":     current.Version,
		"expectedParticipationVersion": participationVersion(t, current, "persona-revoke"),
	}
	revoked := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+gatheringID+":revoke-invitation",
		revokeBody,
		"persona-owner",
		"revoke-invitation-1",
	)
	if revoked.Code != http.StatusOK || decode(t, revoked)["participationState"] != "closed" {
		t.Fatalf("revoke status=%d body=%s", revoked.Code, revoked.Body.String())
	}
	revokedReplay := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+gatheringID+":revoke-invitation",
		revokeBody,
		"persona-owner",
		"revoke-invitation-1",
	)
	if revokedReplay.Code != http.StatusOK || decode(t, revokedReplay)["idempotentReplay"] != true {
		t.Fatalf(
			"revoke replay status=%d body=%s",
			revokedReplay.Code,
			revokedReplay.Body.String(),
		)
	}

	current, _, _ = store.Load(ctx, gatheringID)
	declineInvite := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+gatheringID+":invite",
		map[string]any{
			"participantPersonaId":         "persona-decline",
			"expectedGatheringVersion":     current.Version,
			"expectedParticipationVersion": 0,
			"seatHoldUntil":                now.Add(time.Hour),
		},
		"persona-owner",
		"invite-decline-1",
	)
	if declineInvite.Code != http.StatusOK {
		t.Fatalf(
			"invite for decline status=%d body=%s",
			declineInvite.Code,
			declineInvite.Body.String(),
		)
	}
	current, _, _ = store.Load(ctx, gatheringID)
	declineBody := map[string]any{
		"expectedGatheringVersion":     current.Version,
		"expectedParticipationVersion": participationVersion(t, current, "persona-decline"),
	}
	declined := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+gatheringID+":decline-invitation",
		declineBody,
		"persona-decline",
		"decline-invitation-1",
	)
	if declined.Code != http.StatusOK || decode(t, declined)["participationState"] != "closed" {
		t.Fatalf("decline status=%d body=%s", declined.Code, declined.Body.String())
	}
	declinedReplay := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+gatheringID+":decline-invitation",
		declineBody,
		"persona-decline",
		"decline-invitation-1",
	)
	if declinedReplay.Code != http.StatusOK || decode(t, declinedReplay)["idempotentReplay"] != true {
		t.Fatalf(
			"decline replay status=%d body=%s",
			declinedReplay.Code,
			declinedReplay.Body.String(),
		)
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
	current, _, _ = store.Load(ctx, gatheringID)
	removeBody := map[string]any{
		"participantPersonaId":         "persona-member",
		"reasonRef":                    "host/removed",
		"expectedGatheringVersion":     current.Version,
		"expectedParticipationVersion": participationVersion(t, current, "persona-member"),
	}
	removed := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+gatheringID+":remove",
		removeBody,
		"persona-owner",
		"remove-participant-1",
	)
	if removed.Code != http.StatusOK || decode(t, removed)["participationState"] != "closed" {
		t.Fatalf("remove status=%d body=%s", removed.Code, removed.Body.String())
	}
	removedReplay := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+gatheringID+":remove",
		removeBody,
		"persona-owner",
		"remove-participant-1",
	)
	if removedReplay.Code != http.StatusOK || decode(t, removedReplay)["idempotentReplay"] != true {
		t.Fatalf(
			"remove replay status=%d body=%s",
			removedReplay.Code,
			removedReplay.Body.String(),
		)
	}
	current, _, _ = store.Load(ctx, gatheringID)
	unauthorizedRemove := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+gatheringID+":remove",
		map[string]any{
			"participantPersonaId":         "persona-invitee",
			"reasonRef":                    "attacker/remove",
			"expectedGatheringVersion":     current.Version,
			"expectedParticipationVersion": participationVersion(t, current, "persona-invitee"),
		},
		"persona-attacker",
		"remove-unauthorized-1",
	)
	if unauthorizedRemove.Code != http.StatusForbidden {
		t.Fatalf(
			"unauthorized remove status=%d body=%s",
			unauthorizedRemove.Code,
			unauthorizedRemove.Body.String(),
		)
	}
	reinstateBody := map[string]any{
		"participantPersonaId":         "persona-member",
		"reasonRef":                    "host/reinstated",
		"expectedGatheringVersion":     current.Version,
		"expectedParticipationVersion": participationVersion(t, current, "persona-member"),
	}
	reinstated := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+gatheringID+":reinstate",
		reinstateBody,
		"persona-owner",
		"reinstate-participant-1",
	)
	if reinstated.Code != http.StatusOK || decode(t, reinstated)["participationState"] != "active" {
		t.Fatalf(
			"reinstate status=%d body=%s",
			reinstated.Code,
			reinstated.Body.String(),
		)
	}
	reinstatedReplay := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+gatheringID+":reinstate",
		reinstateBody,
		"persona-owner",
		"reinstate-participant-1",
	)
	if reinstatedReplay.Code != http.StatusOK || decode(t, reinstatedReplay)["idempotentReplay"] != true {
		t.Fatalf(
			"reinstate replay status=%d body=%s",
			reinstatedReplay.Code,
			reinstatedReplay.Body.String(),
		)
	}

	current, _, _ = store.Load(ctx, gatheringID)
	pauseBody := map[string]any{
		"reasonRef":                       "host/paused",
		"expectedGatheringVersion":        current.Version,
		"expectedAdmissionControlVersion": current.AdmissionControl.Version,
	}
	paused := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+gatheringID+":pause-admission",
		pauseBody,
		"persona-owner",
		"pause-admission-1",
	)
	if paused.Code != http.StatusOK {
		t.Fatalf("pause status=%d body=%s", paused.Code, paused.Body.String())
	}
	pausedReplay := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+gatheringID+":pause-admission",
		pauseBody,
		"persona-owner",
		"pause-admission-1",
	)
	if pausedReplay.Code != http.StatusOK || decode(t, pausedReplay)["idempotentReplay"] != true {
		t.Fatalf(
			"pause replay status=%d body=%s",
			pausedReplay.Code,
			pausedReplay.Body.String(),
		)
	}
	current, _, _ = store.Load(ctx, gatheringID)
	staleResume := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+gatheringID+":resume-admission",
		map[string]any{
			"reasonRef":                       "host/resumed",
			"expectedGatheringVersion":        current.Version,
			"expectedAdmissionControlVersion": current.AdmissionControl.Version - 1,
		},
		"persona-owner",
		"resume-admission-stale-1",
	)
	if staleResume.Code != http.StatusConflict {
		t.Fatalf(
			"stale resume status=%d body=%s",
			staleResume.Code,
			staleResume.Body.String(),
		)
	}
	resumeBody := map[string]any{
		"reasonRef":                       "host/resumed",
		"expectedGatheringVersion":        current.Version,
		"expectedAdmissionControlVersion": current.AdmissionControl.Version,
	}
	resumed := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+gatheringID+":resume-admission",
		resumeBody,
		"persona-owner",
		"resume-admission-1",
	)
	if resumed.Code != http.StatusOK {
		t.Fatalf("resume status=%d body=%s", resumed.Code, resumed.Body.String())
	}
	resumedReplay := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+gatheringID+":resume-admission",
		resumeBody,
		"persona-owner",
		"resume-admission-1",
	)
	if resumedReplay.Code != http.StatusOK || decode(t, resumedReplay)["idempotentReplay"] != true {
		t.Fatalf(
			"resume replay status=%d body=%s",
			resumedReplay.Code,
			resumedReplay.Body.String(),
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
	ownerDetail := execute(
		t,
		mux,
		http.MethodGet,
		"/gatherings/"+gatheringID,
		nil,
		"persona-owner",
		"",
	)
	ownerDetailBody := decode(t, ownerDetail)
	if ownerDetail.Code != http.StatusOK ||
		ownerDetailBody["gatheringId"] != gatheringID ||
		ownerDetailBody["aggregateVersion"] != decode(t, detail)["aggregateVersion"] {
		t.Fatalf("owner detail status=%d body=%s", ownerDetail.Code, ownerDetail.Body.String())
	}
	unrelatedDetail := execute(
		t,
		mux,
		http.MethodGet,
		"/gatherings/"+gatheringID,
		nil,
		"persona-attacker",
		"",
	)
	if unrelatedDetail.Code != http.StatusForbidden ||
		bytes.Contains(unrelatedDetail.Body.Bytes(), []byte("onlineLocationRef")) ||
		bytes.Contains(unrelatedDetail.Body.Bytes(), []byte("participations")) {
		t.Fatalf(
			"unrelated private detail status=%d body=%s",
			unrelatedDetail.Code,
			unrelatedDetail.Body.String(),
		)
	}

	current, _, _ = store.Load(ctx, gatheringID)
	staleLeave := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+gatheringID+":leave",
		map[string]any{
			"expectedGatheringVersion":     current.Version - 1,
			"expectedParticipationVersion": participationVersion(t, current, "persona-member"),
		},
		"persona-member",
		"leave-stale-1",
	)
	if staleLeave.Code != http.StatusConflict {
		t.Fatalf("stale leave status=%d body=%s", staleLeave.Code, staleLeave.Body.String())
	}
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
	leftBody := decode(t, left)
	leaveReplay := execute(
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
	leaveReplayBody := decode(t, leaveReplay)
	if leaveReplay.Code != http.StatusOK ||
		leaveReplayBody["idempotentReplay"] != true ||
		leaveReplayBody["aggregateVersion"] != leftBody["aggregateVersion"] {
		t.Fatalf("leave replay status=%d body=%s", leaveReplay.Code, leaveReplay.Body.String())
	}
	revokedDetail := execute(
		t,
		mux,
		http.MethodGet,
		"/gatherings/"+gatheringID,
		nil,
		"persona-member",
		"",
	)
	if revokedDetail.Code != http.StatusForbidden ||
		bytes.Contains(revokedDetail.Body.Bytes(), []byte("onlineLocationRef")) {
		t.Fatalf("revoked detail status=%d body=%s", revokedDetail.Code, revokedDetail.Body.String())
	}
	current, _, _ = store.Load(ctx, gatheringID)
	unauthorizedCancel := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+gatheringID+":cancel",
		map[string]any{
			"expectedGatheringVersion": current.Version,
			"reasonRef":                "reason/unauthorized",
			"evidenceRefs":             []any{},
		},
		"persona-attacker",
		"cancel-unauthorized-1",
	)
	if unauthorizedCancel.Code != http.StatusForbidden {
		t.Fatalf("unauthorized cancel status=%d body=%s", unauthorizedCancel.Code, unauthorizedCancel.Body.String())
	}
	staleCancel := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+gatheringID+":cancel",
		map[string]any{
			"expectedGatheringVersion": current.Version - 1,
			"reasonRef":                "reason/stale",
			"evidenceRefs":             []any{},
		},
		"persona-owner",
		"cancel-stale-1",
	)
	if staleCancel.Code != http.StatusConflict {
		t.Fatalf("stale cancel status=%d body=%s", staleCancel.Code, staleCancel.Body.String())
	}
	beforeCancelVersion := current.Version
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
	cancelledBody := decode(t, cancelled)
	cancelReplay := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+gatheringID+":cancel",
		map[string]any{
			"expectedGatheringVersion": beforeCancelVersion,
			"reasonRef":                "reason/organizer-cancelled",
			"evidenceRefs":             []any{},
		},
		"persona-owner",
		"cancel-1",
	)
	cancelReplayBody := decode(t, cancelReplay)
	if cancelReplay.Code != http.StatusOK ||
		cancelReplayBody["idempotentReplay"] != true ||
		cancelReplayBody["aggregateVersion"] != cancelledBody["aggregateVersion"] {
		t.Fatalf("cancel replay status=%d body=%s", cancelReplay.Code, cancelReplay.Body.String())
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
	withdrawApplied := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+approvalID+":apply",
		map[string]any{
			"expectedGatheringVersion":     approvalCurrent.Version,
			"expectedParticipationVersion": 0,
			"answers":                      []any{},
		},
		"persona-withdraw",
		"apply-withdraw-1",
	)
	if withdrawApplied.Code != http.StatusOK {
		t.Fatalf(
			"apply for withdraw status=%d body=%s",
			withdrawApplied.Code,
			withdrawApplied.Body.String(),
		)
	}
	approvalCurrent, _, _ = store.Load(ctx, approvalID)
	withdrawBody := map[string]any{
		"expectedGatheringVersion":     approvalCurrent.Version,
		"expectedParticipationVersion": participationVersion(t, approvalCurrent, "persona-withdraw"),
	}
	withdrawn := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+approvalID+":withdraw-application",
		withdrawBody,
		"persona-withdraw",
		"withdraw-application-1",
	)
	if withdrawn.Code != http.StatusOK || decode(t, withdrawn)["participationState"] != "closed" {
		t.Fatalf("withdraw status=%d body=%s", withdrawn.Code, withdrawn.Body.String())
	}
	withdrawnReplay := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+approvalID+":withdraw-application",
		withdrawBody,
		"persona-withdraw",
		"withdraw-application-1",
	)
	if withdrawnReplay.Code != http.StatusOK || decode(t, withdrawnReplay)["idempotentReplay"] != true {
		t.Fatalf(
			"withdraw replay status=%d body=%s",
			withdrawnReplay.Code,
			withdrawnReplay.Body.String(),
		)
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
	secondApplied := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+approvalID+":apply",
		map[string]any{
			"expectedGatheringVersion":     approvalCurrent.Version,
			"expectedParticipationVersion": 0,
			"answers":                      []any{},
		},
		"persona-applicant-2",
		"apply-approval-2",
	)
	if secondApplied.Code != http.StatusOK {
		t.Fatalf(
			"second apply status=%d body=%s",
			secondApplied.Code,
			secondApplied.Body.String(),
		)
	}
	unauthorizedApplications := execute(
		t,
		mux,
		http.MethodGet,
		"/gatherings/"+approvalID+"/applications?limit=1",
		nil,
		"persona-applicant",
		"",
	)
	if unauthorizedApplications.Code != http.StatusForbidden {
		t.Fatalf(
			"unauthorized applications status=%d body=%s",
			unauthorizedApplications.Code,
			unauthorizedApplications.Body.String(),
		)
	}
	applicationsFirst := execute(
		t,
		mux,
		http.MethodGet,
		"/gatherings/"+approvalID+"/applications?limit=1",
		nil,
		"persona-owner",
		"",
	)
	applicationsFirstBody := decode(t, applicationsFirst)
	applicationsFirstItems, _ := applicationsFirstBody["items"].([]any)
	applicationsCursor, _ := applicationsFirstBody["nextCursor"].(string)
	if applicationsFirst.Code != http.StatusOK ||
		len(applicationsFirstItems) != 1 ||
		applicationsFirstBody["hasMore"] != true ||
		applicationsCursor == "" {
		t.Fatalf(
			"first applications page status=%d body=%s",
			applicationsFirst.Code,
			applicationsFirst.Body.String(),
		)
	}
	applicationsFirstItem, _ := applicationsFirstItems[0].(map[string]any)
	applicationsSecond := execute(
		t,
		mux,
		http.MethodGet,
		"/gatherings/"+approvalID+"/applications?limit=1&cursor="+applicationsCursor,
		nil,
		"persona-owner",
		"",
	)
	applicationsSecondBody := decode(t, applicationsSecond)
	applicationsSecondItems, _ := applicationsSecondBody["items"].([]any)
	if applicationsSecond.Code != http.StatusOK ||
		len(applicationsSecondItems) != 1 ||
		applicationsSecondBody["hasMore"] != false {
		t.Fatalf(
			"second applications page status=%d body=%s",
			applicationsSecond.Code,
			applicationsSecond.Body.String(),
		)
	}
	applicationsSecondItem, _ := applicationsSecondItems[0].(map[string]any)
	if applicationsFirstItem["personaId"] == "" ||
		applicationsSecondItem["personaId"] == "" ||
		applicationsFirstItem["personaId"] == applicationsSecondItem["personaId"] ||
		applicationsFirstItem["participationVersion"] != float64(1) ||
		applicationsSecondItem["participationVersion"] != float64(1) {
		t.Fatalf(
			"application inbox keyset/state drift: first=%+v second=%+v",
			applicationsFirstItem,
			applicationsSecondItem,
		)
	}
	approvalCurrent, _, _ = store.Load(ctx, approvalID)
	reviewBody := map[string]any{
		"participantPersonaId":         "persona-applicant",
		"decision":                     "approve",
		"reasonRef":                    "review/approved",
		"expectedGatheringVersion":     approvalCurrent.Version,
		"expectedParticipationVersion": participationVersion(t, approvalCurrent, "persona-applicant"),
	}
	unauthorizedReview := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+approvalID+":review-application",
		reviewBody,
		"persona-attacker",
		"review-unauthorized-1",
	)
	if unauthorizedReview.Code != http.StatusForbidden {
		t.Fatalf(
			"unauthorized review status=%d body=%s",
			unauthorizedReview.Code,
			unauthorizedReview.Body.String(),
		)
	}
	staleReviewBody := cloneJSONMap(t, reviewBody)
	staleReviewBody["expectedGatheringVersion"] = approvalCurrent.Version - 1
	staleReview := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+approvalID+":review-application",
		staleReviewBody,
		"persona-owner",
		"review-stale-1",
	)
	if staleReview.Code != http.StatusConflict {
		t.Fatalf("stale review status=%d body=%s", staleReview.Code, staleReview.Body.String())
	}
	beforeReviewVersion := approvalCurrent.Version
	approved := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+approvalID+":review-application",
		reviewBody,
		"persona-owner",
		"review-approval-1",
	)
	if approved.Code != http.StatusOK {
		t.Fatalf("approve status=%d body=%s", approved.Code, approved.Body.String())
	}
	approvedBody := decode(t, approved)
	reviewReplay := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+approvalID+":review-application",
		reviewBody,
		"persona-owner",
		"review-approval-1",
	)
	reviewReplayBody := decode(t, reviewReplay)
	if reviewReplay.Code != http.StatusOK ||
		reviewReplayBody["idempotentReplay"] != true ||
		reviewReplayBody["aggregateVersion"] != approvedBody["aggregateVersion"] {
		t.Fatalf("review replay status=%d body=%s", reviewReplay.Code, reviewReplay.Body.String())
	}
	afterReview, found, loadErr := store.Load(ctx, approvalID)
	if loadErr != nil || !found || afterReview.Version <= beforeReviewVersion ||
		participationState(t, afterReview, "persona-applicant") != contract.GatheringParticipationStateActive ||
		participationState(t, afterReview, "persona-applicant-2") != contract.GatheringParticipationStateApplicationPending {
		t.Fatalf(
			"review mutated wrong application: found=%v value=%+v err=%v",
			found,
			afterReview,
			loadErr,
		)
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
	unauthorizedComplete := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+approvalID+":complete",
		gatheringVersionRequest{ExpectedGatheringVersion: approvalCurrent.Version},
		"persona-attacker",
		"complete-unauthorized-1",
	)
	if unauthorizedComplete.Code != http.StatusForbidden {
		t.Fatalf(
			"unauthorized complete status=%d body=%s",
			unauthorizedComplete.Code,
			unauthorizedComplete.Body.String(),
		)
	}
	staleComplete := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+approvalID+":complete",
		gatheringVersionRequest{ExpectedGatheringVersion: approvalCurrent.Version - 1},
		"persona-owner",
		"complete-stale-1",
	)
	if staleComplete.Code != http.StatusConflict {
		t.Fatalf("stale complete status=%d body=%s", staleComplete.Code, staleComplete.Body.String())
	}
	beforeCompleteVersion := approvalCurrent.Version
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
	completeReplay := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+approvalID+":complete",
		gatheringVersionRequest{ExpectedGatheringVersion: beforeCompleteVersion},
		"persona-owner",
		"complete-approval-1",
	)
	completeReplayBody := decode(t, completeReplay)
	if completeReplay.Code != http.StatusOK ||
		completeReplayBody["idempotentReplay"] != true ||
		completeReplayBody["aggregateVersion"] != completedBody["aggregateVersion"] ||
		completeReplayBody["outcomeStatus"] != "occurred" {
		t.Fatalf("complete replay status=%d body=%s", completeReplay.Code, completeReplay.Body.String())
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

func TestGatheringHTTPPersistsHostAuthorityAndAvailabilityWatchBoundaries(t *testing.T) {
	ctx := context.Background()
	runtime, err := testinfra.StartRealMongo(
		ctx,
		"circle_gathering_host_watch_api_integration",
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
	lifecycle := gatheringapp.NewLifecycleFacade(
		store,
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
	hostDraft := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings",
		gatheringDraftBody(
			now,
			now.Add(3*time.Hour),
			now.Add(5*time.Hour),
			"Host 权限原子边界",
		),
		"persona-owner",
		"create-host-boundary-1",
	)
	if hostDraft.Code != http.StatusCreated {
		t.Fatalf("create Host boundary Gathering status=%d body=%s", hostDraft.Code, hostDraft.Body.String())
	}
	hostID, _ := decode(t, hostDraft)["gatheringId"].(string)
	chat := &chatProjection{}
	reconciler := gatheringapp.NewReconciler(store, store, chat)
	if count, reconcileErr := reconciler.ReconcileOnce(ctx, 20); reconcileErr != nil || count < 1 {
		t.Fatalf("reconcile Host boundary Gathering count=%d err=%v", count, reconcileErr)
	}
	hostCurrent, found, loadErr := store.Load(ctx, hostID)
	if loadErr != nil || !found || hostCurrent.RoomBindingStatus != contract.GatheringRoomBindingStatusReady {
		t.Fatalf("load room-ready Host boundary Gathering found=%v value=%+v err=%v", found, hostCurrent, loadErr)
	}
	hostPublished := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+hostID+":publish",
		gatheringVersionRequest{ExpectedGatheringVersion: hostCurrent.Version},
		"persona-owner",
		"publish-host-boundary-1",
	)
	if hostPublished.Code != http.StatusOK {
		t.Fatalf("publish Host boundary Gathering status=%d body=%s", hostPublished.Code, hostPublished.Body.String())
	}
	hostCurrent, _, _ = store.Load(ctx, hostID)
	coHostJoined := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+hostID+":join-open",
		map[string]any{
			"expectedGatheringVersion":     hostCurrent.Version,
			"expectedParticipationVersion": 0,
		},
		"persona-cohost",
		"join-cohost-boundary-1",
	)
	if coHostJoined.Code != http.StatusOK {
		t.Fatalf("join co-host as participant status=%d body=%s", coHostJoined.Code, coHostJoined.Body.String())
	}
	hostCurrent, _, _ = store.Load(ctx, hostID)
	initialParticipations := canonicalJSON(t, hostCurrent.Participations)
	assignBody := map[string]any{
		"coHostPersonaId":          "persona-cohost",
		"authorityEvidenceRef":     hostCurrent.HostBinding.AuthorityEvidenceRef,
		"authorityVersion":         hostCurrent.HostBinding.AuthorityVersion,
		"expectedGatheringVersion": hostCurrent.Version,
	}
	unauthorizedAssign := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+hostID+":assign-co-host",
		assignBody,
		"persona-attacker",
		"assign-cohost-unauthorized-1",
	)
	if unauthorizedAssign.Code != http.StatusForbidden {
		t.Fatalf(
			"unauthorized co-host assign status=%d body=%s",
			unauthorizedAssign.Code,
			unauthorizedAssign.Body.String(),
		)
	}
	invalidAuthorityAssignBody := cloneJSONMap(t, assignBody)
	invalidAuthorityAssignBody["authorityEvidenceRef"] = "authority/invalid"
	invalidAuthorityAssign := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+hostID+":assign-co-host",
		invalidAuthorityAssignBody,
		"persona-owner",
		"assign-cohost-authority-invalid-1",
	)
	if invalidAuthorityAssign.Code != http.StatusForbidden {
		t.Fatalf(
			"invalid-authority co-host assign status=%d body=%s",
			invalidAuthorityAssign.Code,
			invalidAuthorityAssign.Body.String(),
		)
	}
	staleAssignBody := cloneJSONMap(t, assignBody)
	staleAssignBody["expectedGatheringVersion"] = hostCurrent.Version - 1
	staleAssign := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+hostID+":assign-co-host",
		staleAssignBody,
		"persona-owner",
		"assign-cohost-stale-1",
	)
	if staleAssign.Code != http.StatusConflict {
		t.Fatalf("stale co-host assign status=%d body=%s", staleAssign.Code, staleAssign.Body.String())
	}
	hostAfterAssignFailures, found, loadErr := store.Load(ctx, hostID)
	if loadErr != nil || !found || hostAfterAssignFailures.Version != hostCurrent.Version ||
		len(hostAfterAssignFailures.OrganizerAssignments) != len(hostCurrent.OrganizerAssignments) {
		t.Fatalf(
			"failed co-host assign produced partial state: found=%v before=%+v after=%+v err=%v",
			found,
			hostCurrent,
			hostAfterAssignFailures,
			loadErr,
		)
	}
	assigned := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+hostID+":assign-co-host",
		assignBody,
		"persona-owner",
		"assign-cohost-1",
	)
	assignedBody := decode(t, assigned)
	if assigned.Code != http.StatusOK {
		t.Fatalf("assign co-host status=%d body=%s", assigned.Code, assigned.Body.String())
	}
	assignReplay := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+hostID+":assign-co-host",
		assignBody,
		"persona-owner",
		"assign-cohost-1",
	)
	assignReplayBody := decode(t, assignReplay)
	if assignReplay.Code != http.StatusOK ||
		assignReplayBody["idempotentReplay"] != true ||
		assignReplayBody["aggregateVersion"] != assignedBody["aggregateVersion"] {
		t.Fatalf("assign co-host replay status=%d body=%s", assignReplay.Code, assignReplay.Body.String())
	}
	hostCurrent, found, loadErr = store.Load(ctx, hostID)
	coHostAssignment := organizerAssignment(t, hostCurrent, "persona-cohost")
	if loadErr != nil || !found || coHostAssignment.Role != contract.GatheringOrganizerRoleCoHost ||
		!coHostAssignment.RevokedAt.IsZero() ||
		canonicalJSON(t, hostCurrent.Participations) != initialParticipations ||
		countParticipations(hostCurrent, "persona-cohost") != 1 {
		t.Fatalf(
			"co-host assignment changed participation or was not persisted: found=%v assignment=%+v value=%+v err=%v",
			found,
			coHostAssignment,
			hostCurrent,
			loadErr,
		)
	}

	revokeBody := map[string]any{
		"participantPersonaId":         "persona-cohost",
		"reasonRef":                    "host/revoke-cohost",
		"expectedGatheringVersion":     hostCurrent.Version,
		"expectedParticipationVersion": 0,
	}
	unauthorizedRevoke := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+hostID+":revoke-co-host",
		revokeBody,
		"persona-attacker",
		"revoke-cohost-unauthorized-1",
	)
	if unauthorizedRevoke.Code != http.StatusForbidden {
		t.Fatalf(
			"unauthorized co-host revoke status=%d body=%s",
			unauthorizedRevoke.Code,
			unauthorizedRevoke.Body.String(),
		)
	}
	staleRevokeBody := cloneJSONMap(t, revokeBody)
	staleRevokeBody["expectedGatheringVersion"] = hostCurrent.Version - 1
	staleRevoke := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+hostID+":revoke-co-host",
		staleRevokeBody,
		"persona-owner",
		"revoke-cohost-stale-1",
	)
	if staleRevoke.Code != http.StatusConflict {
		t.Fatalf("stale co-host revoke status=%d body=%s", staleRevoke.Code, staleRevoke.Body.String())
	}
	revoked := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+hostID+":revoke-co-host",
		revokeBody,
		"persona-owner",
		"revoke-cohost-1",
	)
	revokedBody := decode(t, revoked)
	if revoked.Code != http.StatusOK {
		t.Fatalf("revoke co-host status=%d body=%s", revoked.Code, revoked.Body.String())
	}
	revokeReplay := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+hostID+":revoke-co-host",
		revokeBody,
		"persona-owner",
		"revoke-cohost-1",
	)
	revokeReplayBody := decode(t, revokeReplay)
	if revokeReplay.Code != http.StatusOK ||
		revokeReplayBody["idempotentReplay"] != true ||
		revokeReplayBody["aggregateVersion"] != revokedBody["aggregateVersion"] {
		t.Fatalf("revoke co-host replay status=%d body=%s", revokeReplay.Code, revokeReplay.Body.String())
	}
	hostCurrent, found, loadErr = store.Load(ctx, hostID)
	revokedAssignment := organizerAssignment(t, hostCurrent, "persona-cohost")
	if loadErr != nil || !found || revokedAssignment.RevokedAt.IsZero() ||
		activePrimaryOrganizerCount(hostCurrent) != 1 ||
		canonicalJSON(t, hostCurrent.Participations) != initialParticipations {
		t.Fatalf(
			"co-host revoke changed primary or participation: found=%v assignment=%+v value=%+v err=%v",
			found,
			revokedAssignment,
			hostCurrent,
			loadErr,
		)
	}

	reassignBody := map[string]any{
		"coHostPersonaId":          "persona-cohost",
		"authorityEvidenceRef":     hostCurrent.HostBinding.AuthorityEvidenceRef,
		"authorityVersion":         hostCurrent.HostBinding.AuthorityVersion,
		"expectedGatheringVersion": hostCurrent.Version,
	}
	reassigned := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+hostID+":assign-co-host",
		reassignBody,
		"persona-owner",
		"reassign-cohost-1",
	)
	if reassigned.Code != http.StatusOK {
		t.Fatalf("reassign co-host status=%d body=%s", reassigned.Code, reassigned.Body.String())
	}
	hostCurrent, _, _ = store.Load(ctx, hostID)
	transferBody := map[string]any{
		"newPrimaryOrganizerPersonaId": "persona-cohost",
		"authorityEvidenceRef":         hostCurrent.HostBinding.AuthorityEvidenceRef,
		"authorityVersion":             hostCurrent.HostBinding.AuthorityVersion,
		"expectedGatheringVersion":     hostCurrent.Version,
	}
	unauthorizedTransfer := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+hostID+":transfer-organizer",
		transferBody,
		"persona-attacker",
		"transfer-organizer-unauthorized-1",
	)
	if unauthorizedTransfer.Code != http.StatusForbidden {
		t.Fatalf(
			"unauthorized organizer transfer status=%d body=%s",
			unauthorizedTransfer.Code,
			unauthorizedTransfer.Body.String(),
		)
	}
	invalidTransferBody := cloneJSONMap(t, transferBody)
	invalidTransferBody["authorityEvidenceRef"] = "authority/invalid"
	invalidTransfer := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+hostID+":transfer-organizer",
		invalidTransferBody,
		"persona-owner",
		"transfer-organizer-authority-invalid-1",
	)
	if invalidTransfer.Code != http.StatusForbidden {
		t.Fatalf(
			"invalid-authority organizer transfer status=%d body=%s",
			invalidTransfer.Code,
			invalidTransfer.Body.String(),
		)
	}
	staleTransferBody := cloneJSONMap(t, transferBody)
	staleTransferBody["expectedGatheringVersion"] = hostCurrent.Version - 1
	staleTransfer := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+hostID+":transfer-organizer",
		staleTransferBody,
		"persona-owner",
		"transfer-organizer-stale-1",
	)
	if staleTransfer.Code != http.StatusConflict {
		t.Fatalf("stale organizer transfer status=%d body=%s", staleTransfer.Code, staleTransfer.Body.String())
	}
	transferred := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+hostID+":transfer-organizer",
		transferBody,
		"persona-owner",
		"transfer-organizer-1",
	)
	transferredBody := decode(t, transferred)
	if transferred.Code != http.StatusOK {
		t.Fatalf("transfer organizer status=%d body=%s", transferred.Code, transferred.Body.String())
	}
	transferReplay := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+hostID+":transfer-organizer",
		transferBody,
		"persona-owner",
		"transfer-organizer-1",
	)
	transferReplayBody := decode(t, transferReplay)
	if transferReplay.Code != http.StatusOK ||
		transferReplayBody["idempotentReplay"] != true ||
		transferReplayBody["aggregateVersion"] != transferredBody["aggregateVersion"] {
		t.Fatalf("transfer organizer replay status=%d body=%s", transferReplay.Code, transferReplay.Body.String())
	}
	hostCurrent, found, loadErr = store.Load(ctx, hostID)
	newPrimary := organizerAssignment(t, hostCurrent, "persona-cohost")
	oldPrimary := organizerAssignment(t, hostCurrent, "persona-owner")
	if loadErr != nil || !found || activePrimaryOrganizerCount(hostCurrent) != 1 ||
		newPrimary.Role != contract.GatheringOrganizerRolePrimaryOrganizer ||
		oldPrimary.Role != contract.GatheringOrganizerRoleCoHost ||
		hostCurrent.Revisions[len(hostCurrent.Revisions)-1].MaterialChange != true ||
		len(hostCurrent.Participations) != 2 ||
		participationState(t, hostCurrent, "persona-owner") != contract.GatheringParticipationStateActive ||
		participationState(t, hostCurrent, "persona-cohost") != contract.GatheringParticipationStateActive ||
		organizerRevisionAcknowledgementStatus(t, hostCurrent, "persona-owner") !=
			contract.GatheringRevisionAcknowledgementStatusPending ||
		organizerRevisionAcknowledgementStatus(t, hostCurrent, "persona-cohost") !=
			contract.GatheringRevisionAcknowledgementStatusPending {
		t.Fatalf(
			"organizer transfer identity/state boundary drift: found=%v new=%+v old=%+v value=%+v err=%v",
			found,
			newPrimary,
			oldPrimary,
			hostCurrent,
			loadErr,
		)
	}
	transferredOwnerDetail := execute(
		t,
		mux,
		http.MethodGet,
		"/gatherings/"+hostID,
		nil,
		"persona-cohost",
		"",
	)
	if transferredOwnerDetail.Code != http.StatusOK ||
		decode(t, transferredOwnerDetail)["aggregateVersion"] != float64(hostCurrent.Version) {
		t.Fatalf(
			"transferred owner readback status=%d body=%s",
			transferredOwnerDetail.Code,
			transferredOwnerDetail.Body.String(),
		)
	}

	watchBody := gatheringDraftBody(
		now,
		now.Add(4*time.Hour),
		now.Add(6*time.Hour),
		"满额名额提醒边界",
	)
	watchBody["policySet"].(map[string]any)["capacityPolicy"] = map[string]any{"maxParticipants": 2}
	watchCreated := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings",
		watchBody,
		"persona-owner",
		"create-watch-boundary-1",
	)
	if watchCreated.Code != http.StatusCreated {
		t.Fatalf("create watch Gathering status=%d body=%s", watchCreated.Code, watchCreated.Body.String())
	}
	watchID, _ := decode(t, watchCreated)["gatheringId"].(string)
	if count, reconcileErr := reconciler.ReconcileOnce(ctx, 20); reconcileErr != nil || count < 1 {
		t.Fatalf("reconcile watch Gathering count=%d err=%v", count, reconcileErr)
	}
	watchCurrent, found, loadErr := store.Load(ctx, watchID)
	if loadErr != nil || !found || watchCurrent.RoomBindingStatus != contract.GatheringRoomBindingStatusReady {
		t.Fatalf("load room-ready watch Gathering found=%v value=%+v err=%v", found, watchCurrent, loadErr)
	}
	watchPublished := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+watchID+":publish",
		gatheringVersionRequest{ExpectedGatheringVersion: watchCurrent.Version},
		"persona-owner",
		"publish-watch-boundary-1",
	)
	if watchPublished.Code != http.StatusOK {
		t.Fatalf("publish watch Gathering status=%d body=%s", watchPublished.Code, watchPublished.Body.String())
	}
	watchCurrent, _, _ = store.Load(ctx, watchID)
	secondSeat := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+watchID+":join-open",
		map[string]any{
			"expectedGatheringVersion":     watchCurrent.Version,
			"expectedParticipationVersion": 0,
		},
		"persona-seat-2",
		"join-watch-capacity-1",
	)
	if secondSeat.Code != http.StatusOK {
		t.Fatalf("fill watch Gathering status=%d body=%s", secondSeat.Code, secondSeat.Body.String())
	}
	watchCurrent, _, _ = store.Load(ctx, watchID)
	initialWatchParticipations := participationCoreJSON(t, watchCurrent)
	initialAdmission := canonicalJSON(t, watchCurrent.AdmissionControl)
	watchCommand := map[string]any{
		"expectedGatheringVersion": watchCurrent.Version,
		"expectedWatchVersion":     0,
	}
	staleWatchBody := cloneJSONMap(t, watchCommand)
	staleWatchBody["expectedGatheringVersion"] = watchCurrent.Version - 1
	staleWatch := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+watchID+":watch-availability",
		staleWatchBody,
		"persona-watcher",
		"watch-availability-stale-1",
	)
	if staleWatch.Code != http.StatusConflict {
		t.Fatalf("stale availability watch status=%d body=%s", staleWatch.Code, staleWatch.Body.String())
	}
	missingActorWatch := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+watchID+":watch-availability",
		watchCommand,
		"",
		"watch-availability-missing-actor-1",
	)
	if missingActorWatch.Code != http.StatusBadRequest {
		t.Fatalf(
			"missing-actor availability watch status=%d body=%s",
			missingActorWatch.Code,
			missingActorWatch.Body.String(),
		)
	}
	watched := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+watchID+":watch-availability",
		watchCommand,
		"persona-watcher",
		"watch-availability-1",
	)
	watchedBody := decode(t, watched)
	if watched.Code != http.StatusOK {
		t.Fatalf("watch availability status=%d body=%s", watched.Code, watched.Body.String())
	}
	watchReplay := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+watchID+":watch-availability",
		watchCommand,
		"persona-watcher",
		"watch-availability-1",
	)
	watchReplayBody := decode(t, watchReplay)
	if watchReplay.Code != http.StatusOK ||
		watchReplayBody["idempotentReplay"] != true ||
		watchReplayBody["aggregateVersion"] != watchedBody["aggregateVersion"] {
		t.Fatalf("watch availability replay status=%d body=%s", watchReplay.Code, watchReplay.Body.String())
	}
	watchCurrent, found, loadErr = store.Load(ctx, watchID)
	firstWatch := availabilityWatch(t, watchCurrent, "persona-watcher")
	if loadErr != nil || !found || firstWatch.Status != contract.GatheringAvailabilityWatchStatusActive ||
		countAvailabilityWatches(watchCurrent, "persona-watcher") != 1 ||
		countParticipations(watchCurrent, "persona-watcher") != 0 {
		t.Fatalf(
			"availability watch occupied a seat or changed admission: found=%v watch=%+v value=%+v err=%v",
			found,
			firstWatch,
			watchCurrent,
			loadErr,
		)
	}
	if got := participationCoreJSON(t, watchCurrent); got != initialWatchParticipations {
		t.Fatalf("availability watch changed participations: before=%s after=%s", initialWatchParticipations, got)
	}
	if got := canonicalJSON(t, watchCurrent.AdmissionControl); got != initialAdmission {
		t.Fatalf("availability watch changed admission: before=%s after=%s", initialAdmission, got)
	}
	secondWatchCommand := map[string]any{
		"expectedGatheringVersion": watchCurrent.Version,
		"expectedWatchVersion":     0,
	}
	secondWatched := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+watchID+":watch-availability",
		secondWatchCommand,
		"persona-watcher-2",
		"watch-availability-2",
	)
	if secondWatched.Code != http.StatusOK {
		t.Fatalf("second watch availability status=%d body=%s", secondWatched.Code, secondWatched.Body.String())
	}
	watchCurrent, _, _ = store.Load(ctx, watchID)
	unauthorizedUnwatch := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+watchID+":unwatch-availability",
		map[string]any{
			"expectedGatheringVersion": watchCurrent.Version,
			"expectedWatchVersion":     0,
		},
		"persona-attacker",
		"unwatch-availability-unauthorized-1",
	)
	if unauthorizedUnwatch.Code != http.StatusConflict {
		t.Fatalf(
			"unauthorized availability unwatch status=%d body=%s",
			unauthorizedUnwatch.Code,
			unauthorizedUnwatch.Body.String(),
		)
	}
	staleUnwatch := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+watchID+":unwatch-availability",
		map[string]any{
			"expectedGatheringVersion": watchCurrent.Version,
			"expectedWatchVersion":     firstWatch.Version - 1,
		},
		"persona-watcher",
		"unwatch-availability-stale-1",
	)
	if staleUnwatch.Code != http.StatusConflict {
		t.Fatalf("stale availability unwatch status=%d body=%s", staleUnwatch.Code, staleUnwatch.Body.String())
	}
	unwatchCommand := map[string]any{
		"expectedGatheringVersion": watchCurrent.Version,
		"expectedWatchVersion":     firstWatch.Version,
	}
	unwatched := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+watchID+":unwatch-availability",
		unwatchCommand,
		"persona-watcher",
		"unwatch-availability-1",
	)
	unwatchedBody := decode(t, unwatched)
	if unwatched.Code != http.StatusOK {
		t.Fatalf("unwatch availability status=%d body=%s", unwatched.Code, unwatched.Body.String())
	}
	unwatchReplay := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+watchID+":unwatch-availability",
		unwatchCommand,
		"persona-watcher",
		"unwatch-availability-1",
	)
	unwatchReplayBody := decode(t, unwatchReplay)
	if unwatchReplay.Code != http.StatusOK ||
		unwatchReplayBody["idempotentReplay"] != true ||
		unwatchReplayBody["aggregateVersion"] != unwatchedBody["aggregateVersion"] {
		t.Fatalf("unwatch availability replay status=%d body=%s", unwatchReplay.Code, unwatchReplay.Body.String())
	}
	watchCurrent, found, loadErr = store.Load(ctx, watchID)
	firstWatch = availabilityWatch(t, watchCurrent, "persona-watcher")
	secondWatch := availabilityWatch(t, watchCurrent, "persona-watcher-2")
	if loadErr != nil || !found || firstWatch.Status != contract.GatheringAvailabilityWatchStatusCancelled ||
		secondWatch.Status != contract.GatheringAvailabilityWatchStatusActive ||
		participationCoreJSON(t, watchCurrent) != initialWatchParticipations ||
		canonicalJSON(t, watchCurrent.AdmissionControl) != initialAdmission {
		t.Fatalf(
			"unwatch changed another owner slice: found=%v first=%+v second=%+v value=%+v err=%v",
			found,
			firstWatch,
			secondWatch,
			watchCurrent,
			loadErr,
		)
	}
}

func TestGatheringHTTPTerminalRoutesPersistCanonicalOutcomes(t *testing.T) {
	ctx := context.Background()
	runtime, err := testinfra.StartRealMongo(
		ctx,
		"circle_gathering_terminal_api_integration",
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
	lifecycle := gatheringapp.NewLifecycleFacade(
		store,
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
	chat := &chatProjection{}
	reconciler := gatheringapp.NewReconciler(store, store, chat)

	now := time.Now().UTC()
	activityStart := now.Add(5 * time.Second)
	activityEnd := activityStart.Add(20 * time.Second)
	createPublished := func(key string, title string) (string, gatheringmodel.Gathering) {
		t.Helper()
		created := execute(
			t,
			mux,
			http.MethodPost,
			"/gatherings",
			gatheringDraftBody(now, activityStart, activityEnd, title),
			"persona-owner",
			"create-"+key,
		)
		if created.Code != http.StatusCreated {
			t.Fatalf("create %s status=%d body=%s", key, created.Code, created.Body.String())
		}
		gatheringID, _ := decode(t, created)["gatheringId"].(string)
		if gatheringID == "" {
			t.Fatalf("create %s returned empty gatheringId", key)
		}
		if count, reconcileErr := reconciler.ReconcileOnce(ctx, 20); reconcileErr != nil || count < 1 {
			t.Fatalf("reconcile %s room count=%d err=%v", key, count, reconcileErr)
		}
		current, found, loadErr := store.Load(ctx, gatheringID)
		if loadErr != nil || !found ||
			current.RoomBindingStatus != contract.GatheringRoomBindingStatusReady {
			t.Fatalf(
				"load room-ready %s: found=%v value=%+v err=%v",
				key,
				found,
				current,
				loadErr,
			)
		}
		published := execute(
			t,
			mux,
			http.MethodPost,
			"/gatherings/"+gatheringID+":publish",
			gatheringVersionRequest{ExpectedGatheringVersion: current.Version},
			"persona-owner",
			"publish-"+key,
		)
		if published.Code != http.StatusOK {
			t.Fatalf("publish %s status=%d body=%s", key, published.Code, published.Body.String())
		}
		current, found, loadErr = store.Load(ctx, gatheringID)
		if loadErr != nil || !found ||
			current.LifecycleStatus != contract.GatheringLifecycleStatusPublished {
			t.Fatalf(
				"load published %s: found=%v value=%+v err=%v",
				key,
				found,
				current,
				loadErr,
			)
		}
		return gatheringID, current
	}

	earlyEndID, earlyEndCurrent := createPublished("end-early", "贡嘎同行提前结束")
	safetyID, safetyCurrent := createPublished("safety", "贡嘎同行安全终止")

	endEarlyBody := map[string]any{
		"expectedGatheringVersion": earlyEndCurrent.Version,
		"reasonRef":                "host/weather-ended-early",
		"evidenceRefs": []any{map[string]any{
			"objectTypeRef": "ops.weather_observation",
			"objectId":      "weather-end-early-1",
		}},
	}
	preStartEnd := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+earlyEndID+":end-early",
		endEarlyBody,
		"persona-owner",
		"end-early-before-start-1",
	)
	if preStartEnd.Code != http.StatusConflict ||
		decode(t, preStartEnd)["code"] != "CIRCLE.USER.gathering_operation_not_allowed_in_progress" {
		t.Fatalf(
			"pre-start end status=%d body=%s",
			preStartEnd.Code,
			preStartEnd.Body.String(),
		)
	}

	safetyBody := map[string]any{
		"expectedGatheringVersion": safetyCurrent.Version,
		"reasonRef":                "safety/terminate",
		"evidenceRefs": []any{map[string]any{
			"objectTypeRef": "content.report",
			"objectId":      "report-safety-1",
		}},
	}
	unauthorizedSafety := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+safetyID+":safety-terminate",
		safetyBody,
		"persona-owner",
		"safety-terminate-unauthorized-1",
	)
	if unauthorizedSafety.Code != http.StatusForbidden ||
		decode(t, unauthorizedSafety)["code"] != "CIRCLE.USER.gathering_safety_termination_denied" {
		t.Fatalf(
			"unauthorized safety termination status=%d body=%s",
			unauthorizedSafety.Code,
			unauthorizedSafety.Body.String(),
		)
	}
	staleSafetyBody := cloneJSONMap(t, safetyBody)
	staleSafetyBody["expectedGatheringVersion"] = safetyCurrent.Version - 1
	staleSafety := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+safetyID+":safety-terminate",
		staleSafetyBody,
		"persona-safety",
		"safety-terminate-stale-1",
	)
	if staleSafety.Code != http.StatusConflict {
		t.Fatalf(
			"stale safety termination status=%d body=%s",
			staleSafety.Code,
			staleSafety.Body.String(),
		)
	}
	safetyTerminated := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+safetyID+":safety-terminate",
		safetyBody,
		"persona-safety",
		"safety-terminate-1",
	)
	safetyTerminatedBody := decode(t, safetyTerminated)
	if safetyTerminated.Code != http.StatusOK ||
		safetyTerminatedBody["lifecycleStatus"] != "completed" ||
		safetyTerminatedBody["outcomeStatus"] != "safety_terminated" {
		t.Fatalf(
			"safety termination status=%d body=%s",
			safetyTerminated.Code,
			safetyTerminated.Body.String(),
		)
	}
	safetyVersion := safetyTerminatedBody["aggregateVersion"]
	safetyReplay := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+safetyID+":safety-terminate",
		safetyBody,
		"persona-safety",
		"safety-terminate-1",
	)
	safetyReplayBody := decode(t, safetyReplay)
	if safetyReplay.Code != http.StatusOK ||
		safetyReplayBody["idempotentReplay"] != true ||
		safetyReplayBody["aggregateVersion"] != safetyVersion {
		t.Fatalf(
			"safety termination replay status=%d body=%s",
			safetyReplay.Code,
			safetyReplay.Body.String(),
		)
	}
	safetyAfter, found, loadErr := store.Load(ctx, safetyID)
	if loadErr != nil || !found ||
		safetyAfter.LifecycleStatus != contract.GatheringLifecycleStatusCompleted ||
		safetyAfter.Outcome.Status != contract.GatheringOutcomeStatusSafetyTerminated ||
		len(safetyAfter.Outcome.EvidenceRefs) != 1 {
		t.Fatalf(
			"safety terminal outcome was not persisted: found=%v value=%+v err=%v",
			found,
			safetyAfter,
			loadErr,
		)
	}
	afterTerminalSafetyBody := cloneJSONMap(t, safetyBody)
	afterTerminalSafetyBody["expectedGatheringVersion"] = safetyAfter.Version
	afterTerminalSafety := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+safetyID+":safety-terminate",
		afterTerminalSafetyBody,
		"persona-safety",
		"safety-terminate-after-terminal-1",
	)
	if afterTerminalSafety.Code != http.StatusConflict {
		t.Fatalf(
			"post-terminal safety status=%d body=%s",
			afterTerminalSafety.Code,
			afterTerminalSafety.Body.String(),
		)
	}

	waitUntil(t, activityStart.Add(100*time.Millisecond))
	unauthorizedEnd := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+earlyEndID+":end-early",
		endEarlyBody,
		"persona-attacker",
		"end-early-unauthorized-1",
	)
	if unauthorizedEnd.Code != http.StatusForbidden {
		t.Fatalf(
			"unauthorized early end status=%d body=%s",
			unauthorizedEnd.Code,
			unauthorizedEnd.Body.String(),
		)
	}
	staleEndBody := cloneJSONMap(t, endEarlyBody)
	staleEndBody["expectedGatheringVersion"] = earlyEndCurrent.Version - 1
	staleEnd := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+earlyEndID+":end-early",
		staleEndBody,
		"persona-owner",
		"end-early-stale-1",
	)
	if staleEnd.Code != http.StatusConflict {
		t.Fatalf("stale early end status=%d body=%s", staleEnd.Code, staleEnd.Body.String())
	}
	endedEarly := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+earlyEndID+":end-early",
		endEarlyBody,
		"persona-owner",
		"end-early-1",
	)
	endedEarlyBody := decode(t, endedEarly)
	if endedEarly.Code != http.StatusOK ||
		endedEarlyBody["lifecycleStatus"] != "completed" ||
		endedEarlyBody["outcomeStatus"] != "ended_early" {
		t.Fatalf("early end status=%d body=%s", endedEarly.Code, endedEarly.Body.String())
	}
	endedVersion := endedEarlyBody["aggregateVersion"]
	endedReplay := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+earlyEndID+":end-early",
		endEarlyBody,
		"persona-owner",
		"end-early-1",
	)
	endedReplayBody := decode(t, endedReplay)
	if endedReplay.Code != http.StatusOK ||
		endedReplayBody["idempotentReplay"] != true ||
		endedReplayBody["aggregateVersion"] != endedVersion {
		t.Fatalf(
			"early end replay status=%d body=%s",
			endedReplay.Code,
			endedReplay.Body.String(),
		)
	}
	endedAfter, found, loadErr := store.Load(ctx, earlyEndID)
	if loadErr != nil || !found ||
		endedAfter.LifecycleStatus != contract.GatheringLifecycleStatusCompleted ||
		endedAfter.Outcome.Status != contract.GatheringOutcomeStatusEndedEarly ||
		len(endedAfter.Outcome.EvidenceRefs) != 1 {
		t.Fatalf(
			"early terminal outcome was not persisted: found=%v value=%+v err=%v",
			found,
			endedAfter,
			loadErr,
		)
	}
	afterTerminalEndBody := cloneJSONMap(t, endEarlyBody)
	afterTerminalEndBody["expectedGatheringVersion"] = endedAfter.Version
	afterTerminalEnd := execute(
		t,
		mux,
		http.MethodPost,
		"/gatherings/"+earlyEndID+":end-early",
		afterTerminalEndBody,
		"persona-owner",
		"end-early-after-terminal-1",
	)
	if afterTerminalEnd.Code != http.StatusConflict {
		t.Fatalf(
			"post-terminal early end status=%d body=%s",
			afterTerminalEnd.Code,
			afterTerminalEnd.Body.String(),
		)
	}
}

func gatheringDraftBody(
	now time.Time,
	startAt time.Time,
	endAt time.Time,
	title string,
) map[string]any {
	return map[string]any{
		"hostBinding": map[string]any{
			"hostSubjectKind": "persona", "hostSubjectId": "persona-owner",
			"authorityEvidenceRef": "authority/owner", "authorityVersion": 1,
			"authorityExpiresAt": now.Add(24 * time.Hour),
		},
		"creatorParticipates": true,
		"purpose": map[string]any{
			"title": title, "summary": "一起完成公开、安全的徒步活动",
			"topicRefs": []string{}, "requirementRefs": []string{},
			"sourceObjectRefs": []any{}, "costNotice": "free",
		},
		"schedule": gatheringScheduleBody(startAt, endAt),
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

func participationState(
	t *testing.T,
	value gatheringmodel.Gathering,
	personaID string,
) contract.GatheringParticipationState {
	t.Helper()
	for _, participation := range value.Participations {
		if participation.PersonaID == personaID {
			return participation.State
		}
	}
	t.Fatalf("participation for %s is missing", personaID)
	return ""
}

func organizerRevisionAcknowledgementStatus(
	t *testing.T,
	value gatheringmodel.Gathering,
	personaID string,
) contract.GatheringRevisionAcknowledgementStatus {
	t.Helper()
	for _, participation := range value.Participations {
		if participation.PersonaID == personaID {
			return participation.CurrentChangeAcknowledgement.Status
		}
	}
	t.Fatalf("participation for %s is missing", personaID)
	return ""
}

func countParticipations(value gatheringmodel.Gathering, personaID string) int {
	count := 0
	for _, participation := range value.Participations {
		if participation.PersonaID == personaID {
			count++
		}
	}
	return count
}

func organizerAssignment(
	t *testing.T,
	value gatheringmodel.Gathering,
	personaID string,
) contract.OrganizerAssignment {
	t.Helper()
	for _, assignment := range value.OrganizerAssignments {
		if assignment.PersonaID == personaID {
			return assignment
		}
	}
	t.Fatalf("organizer assignment for %s is missing", personaID)
	return contract.OrganizerAssignment{}
}

func activePrimaryOrganizerCount(value gatheringmodel.Gathering) int {
	count := 0
	for _, assignment := range value.OrganizerAssignments {
		if assignment.Role == contract.GatheringOrganizerRolePrimaryOrganizer &&
			assignment.RevokedAt.IsZero() {
			count++
		}
	}
	return count
}

func availabilityWatch(
	t *testing.T,
	value gatheringmodel.Gathering,
	personaID string,
) contract.GatheringAvailabilityWatch {
	t.Helper()
	for _, watch := range value.AvailabilityWatches {
		if watch.PersonaID == personaID {
			return watch
		}
	}
	t.Fatalf("availability watch for %s is missing", personaID)
	return contract.GatheringAvailabilityWatch{}
}

func countAvailabilityWatches(value gatheringmodel.Gathering, personaID string) int {
	count := 0
	for _, watch := range value.AvailabilityWatches {
		if watch.PersonaID == personaID {
			count++
		}
	}
	return count
}

func canonicalJSON(t *testing.T, value any) string {
	t.Helper()
	encoded, err := json.Marshal(value)
	if err != nil {
		t.Fatalf("marshal canonical JSON: %v", err)
	}
	return string(encoded)
}

func participationCoreJSON(t *testing.T, value gatheringmodel.Gathering) string {
	t.Helper()
	type participationCore struct {
		PersonaID    string `json:"personaId"`
		State        string `json:"state"`
		ClosedReason string `json:"closedReason"`
		Version      int64  `json:"version"`
		Attendance   string `json:"attendance"`
	}
	values := make([]participationCore, 0, len(value.Participations))
	for _, participation := range value.Participations {
		values = append(values, participationCore{
			PersonaID:    participation.PersonaID,
			State:        string(participation.State),
			ClosedReason: string(participation.ClosedReason),
			Version:      participation.Version,
			Attendance:   string(participation.Attendance.Status),
		})
	}
	return canonicalJSON(t, values)
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
