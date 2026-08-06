package assistant_run

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"testing"

	"quwoquan_service/generated/serviceclients"
	gatheringclient "quwoquan_service/generated/serviceclients/circlegathering"
	gatheringplanclient "quwoquan_service/generated/serviceclients/circlegatheringplan"
	runtimeauth "quwoquan_service/runtime/auth"
	tooling "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/application/tooling"
	gatheringinfrastructure "quwoquan_service/services/assistant-service/internal/assistant/assistant_run/infrastructure/gathering"
)

func TestCircleGatheringGeneratedPacketsCoverCreateSearchReadAndWatch(t *testing.T) {
	create, err := gatheringclient.EncodeCreateGatheringDraft(
		gatheringclient.CreateGatheringDraftCommand{
			Purpose: gatheringclient.GatheringPurpose{Title: "测试聚会"},
		},
	)
	if err != nil {
		t.Fatalf("encode create: %v", err)
	}
	if create.Operation.OperationID !=
		serviceclients.CircleGatheringCreateGatheringDraftOperationID ||
		create.Operation.Method != "POST" ||
		create.Path != serviceclients.CircleGatheringCreateGatheringDraftPath() ||
		!bytes.Equal(create.Body, create.CanonicalRequest) {
		t.Fatalf("create packet=%+v body=%s", create, create.Body)
	}
	assertGeneratedDigest(t, create)

	search, err := gatheringclient.EncodeListGatheringsBySource(
		gatheringclient.GatheringListBySourceQuery{
			SourceObjectTypeRef: "circle.post",
			SourceObjectID:      "post-1",
			Cursor:              "next/token",
			Limit:               20,
		},
	)
	if err != nil {
		t.Fatalf("encode search: %v", err)
	}
	if search.Path != serviceclients.CircleGatheringListGatheringsBySourcePath() ||
		search.Query.Get("sourceObjectTypeRef") != "circle.post" ||
		search.Query.Get("sourceObjectId") != "post-1" ||
		search.Query.Get("cursor") != "next/token" ||
		search.Query.Get("limit") != "20" ||
		len(search.Body) != 0 {
		t.Fatalf("search packet=%+v", search)
	}
	assertGeneratedDigest(t, search)

	read, err := gatheringclient.EncodeGetPublicGathering(
		gatheringclient.GatheringIDQuery{
			GatheringID: "gathering/with space?",
		},
	)
	if err != nil {
		t.Fatalf("encode read: %v", err)
	}
	if read.Path != "/public/gatherings/gathering%2Fwith%20space%3F" ||
		len(read.Query) != 0 ||
		len(read.Body) != 0 {
		t.Fatalf("read packet=%+v", read)
	}
	assertGeneratedDigest(t, read)

	watch, err := gatheringclient.EncodeWatchGatheringAvailability(
		gatheringclient.GatheringAvailabilityWatchCommand{
			GatheringID:              "gathering/with space?",
			ExpectedGatheringVersion: 11,
			ExpectedWatchVersion:     3,
		},
	)
	if err != nil {
		t.Fatalf("encode watch: %v", err)
	}
	if watch.Path !=
		"/gatherings/gathering%2Fwith%20space%3F:watch-availability" ||
		string(watch.Body) !=
			`{"expectedGatheringVersion":11,"expectedWatchVersion":3}` {
		t.Fatalf("watch packet=%+v body=%s", watch, watch.Body)
	}
	assertGeneratedDigest(t, watch)

	plan, err := gatheringplanclient.EncodeProposeGatheringPlan(
		gatheringPlanCommand(),
	)
	if err != nil {
		t.Fatalf("encode plan proposal: %v", err)
	}
	if plan.Operation.OperationID !=
		serviceclients.CircleGatheringPlanProposeGatheringPlanOperationID ||
		plan.Path != "/gathering-plans/plan-1/proposals" ||
		bytes.Contains(plan.Body, []byte(`"planId"`)) {
		t.Fatalf("plan proposal packet=%+v body=%s", plan, plan.Body)
	}
	assertGeneratedPlanDigest(t, plan)
}

func TestCircleGatheringBindingBlockedOperationsHaveZeroNetworkImpact(
	t *testing.T,
) {
	transport := &recordingCircleGatheringTransport{}
	planTransport := &recordingCircleGatheringPlanTransport{}
	binding := gatheringinfrastructure.NewCircleGatheringDomainOperationBinding(
		gatheringinfrastructure.WithCircleGatheringDelegatedGrantTransport(
			transport,
		),
		gatheringinfrastructure.WithCircleGatheringPlanDelegatedGrantTransport(
			planTransport,
		),
	)

	_, searchErr := binding.SearchPublic(
		t.Context(),
		tooling.VerifiedGatheringQueryCall{},
		tooling.GatheringSearchPublicRequest{
			SourceObjectTypeRef: "circle.post",
			SourceObjectID:      "post-1",
			Limit:               20,
		},
	)
	_, publicErr := binding.ReadPublic(
		t.Context(),
		tooling.VerifiedGatheringQueryCall{},
		tooling.GatheringIDQuery{GatheringID: "gathering-1"},
	)
	_, privateErr := binding.ReadPrivate(
		t.Context(),
		tooling.VerifiedGatheringQueryCall{},
		tooling.GatheringIDQuery{GatheringID: "gathering-1"},
	)
	_, watchErr := binding.WatchAvailability(
		t.Context(),
		tooling.VerifiedGatheringCommandCall{},
		tooling.GatheringAvailabilityWatchCommand{
			GatheringID: "gathering-1",
		},
		"idempotency-1",
	)
	_, planErr := binding.ProposeGatheringPlan(
		t.Context(),
		tooling.VerifiedGatheringCommandCall{},
		gatheringPlanCommand(),
		"idempotency-1",
	)

	for name, err := range map[string]error{
		"search":  searchErr,
		"public":  publicErr,
		"private": privateErr,
		"watch":   watchErr,
		"plan":    planErr,
	} {
		if !errors.Is(
			err,
			gatheringinfrastructure.ErrCircleGatheringGeneratedClientUnavailable,
		) {
			t.Errorf("%s error=%v", name, err)
		}
		var unavailable gatheringinfrastructure.CircleGatheringUnavailableError
		if !errors.As(err, &unavailable) ||
			unavailable.CommercialState != "blocked" ||
			unavailable.OperationID == "" {
			t.Errorf("%s unavailable evidence=%+v", name, unavailable)
		}
	}
	if len(transport.requests) != 0 {
		t.Fatalf("blocked operations reached transport: %+v", transport.requests)
	}
	if len(planTransport.requests) != 0 {
		t.Fatalf("blocked plan operation reached transport: %+v", planTransport.requests)
	}
}

func TestCircleGatheringBindingUsesTypedTransportAndRejectsWrongGrant(
	t *testing.T,
) {
	transport := &recordingCircleGatheringTransport{
		response: func(
			request gatheringinfrastructure.CircleGatheringDelegatedGrantRequest,
		) gatheringclient.ResponsePacket {
			body := []byte(`{"items":[],"nextCursor":"cursor-2","hasMore":false}`)
			if request.Packet.Operation.OperationID ==
				serviceclients.CircleGatheringGetPublicGatheringOperationID {
				body = []byte(
					`{"card":{"gatheringId":"gathering/with space?","purpose":{"title":"公开聚会"},"schedule":{},"place":{},"capacity":{"remainingSeats":2},"admission":{},"lifecycleStatus":"published"}}`,
				)
			}
			return gatheringclient.ResponsePacket{
				StatusCode: request.Packet.Operation.SuccessStatus,
				Body:       body,
			}
		},
	}
	binding := gatheringinfrastructure.NewCircleGatheringDomainOperationBinding(
		gatheringinfrastructure.WithCircleGatheringCommercialProfile(
			explicitTestCommercialProfile{},
		),
		gatheringinfrastructure.WithCircleGatheringDelegatedGrantTransport(
			transport,
		),
	)

	searchRequest := tooling.GatheringSearchPublicRequest{
		SourceObjectTypeRef: "circle.post",
		SourceObjectID:      "post-1",
		Cursor:              "cursor-1",
		Limit:               20,
	}
	searchPacket, err := gatheringclient.EncodeListGatheringsBySource(
		gatheringclient.GatheringListBySourceQuery{
			SourceObjectTypeRef: searchRequest.SourceObjectTypeRef,
			SourceObjectID:      searchRequest.SourceObjectID,
			Cursor:              searchRequest.Cursor,
			Limit:               int64(searchRequest.Limit),
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	searchTarget := runtimeauth.DelegatedResourceConstraint{
		Type: "circle.gathering.source",
		ID:   "circle.post:post-1",
	}
	page, err := binding.SearchPublic(
		t.Context(),
		queryCall(searchPacket, searchTarget),
		searchRequest,
	)
	if err != nil {
		t.Fatalf("search binding: %v", err)
	}
	if page.NextCursor != "cursor-2" || len(transport.requests) != 1 {
		t.Fatalf("search result=%+v requests=%+v", page, transport.requests)
	}
	searchTransport := transport.requests[0]
	if searchTransport.Packet.Path != "/gatherings/by-source" ||
		searchTransport.Packet.Query.Get("sourceObjectId") != "post-1" ||
		searchTransport.SerializedGrant != "delegated-grant" ||
		searchTransport.Claims.RequestDigest !=
			gatheringclient.CanonicalRequestDigest(
				searchTransport.Packet.CanonicalRequest,
			) {
		t.Fatalf("search transport request=%+v", searchTransport)
	}

	readRequest := tooling.GatheringIDQuery{
		GatheringID: "gathering/with space?",
	}
	readPacket, err := gatheringclient.EncodeGetPublicGathering(
		gatheringclient.GatheringIDQuery{
			GatheringID: readRequest.GatheringID,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	readTarget := runtimeauth.DelegatedResourceConstraint{
		Type: "circle.gathering",
		ID:   readRequest.GatheringID,
	}
	detail, err := binding.ReadPublic(
		t.Context(),
		queryCall(readPacket, readTarget),
		readRequest,
	)
	if err != nil {
		t.Fatalf("read binding: %v", err)
	}
	if detail.Title != "公开聚会" ||
		transport.requests[1].Packet.Path !=
			"/public/gatherings/gathering%2Fwith%20space%3F" {
		t.Fatalf(
			"read detail=%+v request=%+v",
			detail,
			transport.requests[1],
		)
	}

	wrong := queryCall(readPacket, readTarget)
	wrong.Grant.Claims.OperationID =
		serviceclients.CircleGatheringGetGatheringOperationID
	if _, err := binding.ReadPublic(
		t.Context(),
		wrong,
		readRequest,
	); !errors.Is(err, tooling.ErrGatheringBindingInvalid) {
		t.Fatalf("wrong grant error=%v", err)
	}
	if len(transport.requests) != 2 {
		t.Fatalf("wrong grant reached transport: %+v", transport.requests)
	}
}

func TestCircleGatheringBindingWatchUsesCanonicalBodyAndDigest(t *testing.T) {
	transport := &recordingCircleGatheringTransport{
		response: func(
			request gatheringinfrastructure.CircleGatheringDelegatedGrantRequest,
		) gatheringclient.ResponsePacket {
			return gatheringclient.ResponsePacket{
				StatusCode: request.Packet.Operation.SuccessStatus,
				Body: []byte(
					`{"gatheringId":"gathering-1","aggregateVersion":12,"lifecycleStatus":"published","currentGatheringRevisionNumber":2,"roomBindingStatus":"ready","idempotentReplay":false}`,
				),
			}
		},
	}
	binding := gatheringinfrastructure.NewCircleGatheringDomainOperationBinding(
		gatheringinfrastructure.WithCircleGatheringCommercialProfile(
			explicitTestCommercialProfile{},
		),
		gatheringinfrastructure.WithCircleGatheringDelegatedGrantTransport(
			transport,
		),
	)
	request := tooling.GatheringAvailabilityWatchCommand{
		GatheringID:              "gathering-1",
		ExpectedGatheringVersion: 11,
		ExpectedWatchVersion:     3,
	}
	packet, err := gatheringclient.EncodeWatchGatheringAvailability(
		gatheringclient.GatheringAvailabilityWatchCommand{
			GatheringID:              request.GatheringID,
			ExpectedGatheringVersion: request.ExpectedGatheringVersion,
			ExpectedWatchVersion:     request.ExpectedWatchVersion,
		},
	)
	if err != nil {
		t.Fatal(err)
	}
	target := runtimeauth.DelegatedResourceConstraint{
		Type: "circle.gathering",
		ID:   request.GatheringID,
	}
	call := commandCall(packet, target, "watch-idempotency")
	result, err := binding.WatchAvailability(
		t.Context(),
		call,
		request,
		"watch-idempotency",
	)
	if err != nil {
		t.Fatalf("watch binding: %v", err)
	}
	if result.AggregateVersion != 12 || len(transport.requests) != 1 {
		t.Fatalf("watch result=%+v requests=%+v", result, transport.requests)
	}
	sent := transport.requests[0]
	if sent.Packet.Path != "/gatherings/gathering-1:watch-availability" ||
		string(sent.Packet.Body) !=
			`{"expectedGatheringVersion":11,"expectedWatchVersion":3}` ||
		sent.Claims.RequestDigest !=
			gatheringclient.CanonicalRequestDigest(sent.Packet.CanonicalRequest) {
		t.Fatalf("watch transport request=%+v body=%s", sent, sent.Packet.Body)
	}
}

func TestCircleGatheringBindingPlanUsesCanonicalGeneratedTransport(t *testing.T) {
	transport := &recordingCircleGatheringPlanTransport{
		response: func(
			request gatheringinfrastructure.CircleGatheringPlanDelegatedGrantRequest,
		) gatheringplanclient.ResponsePacket {
			return gatheringplanclient.ResponsePacket{
				StatusCode: request.Packet.Operation.SuccessStatus,
				Body: []byte(
					`{"planId":"plan-1","gatheringId":"gathering-1","planVersion":3,"currentRevisionId":"revision-1","currentRevisionNumber":1,"currentRevisionDigest":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","proposalId":"proposal-1","proposalDigest":"sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","replayed":false}`,
				),
			}
		},
	}
	binding := gatheringinfrastructure.NewCircleGatheringDomainOperationBinding(
		gatheringinfrastructure.WithCircleGatheringPlanCommercialProfile(
			explicitTestCommercialProfile{},
		),
		gatheringinfrastructure.WithCircleGatheringPlanDelegatedGrantTransport(
			transport,
		),
	)
	request := gatheringPlanCommand()
	packet, err := gatheringplanclient.EncodeProposeGatheringPlan(request)
	if err != nil {
		t.Fatal(err)
	}
	target := runtimeauth.DelegatedResourceConstraint{
		Type: "circle.gathering_plan",
		ID:   request.PlanID,
	}
	result, err := binding.ProposeGatheringPlan(
		t.Context(),
		planCommandCall(packet, target, "plan-idempotency"),
		request,
		"plan-idempotency",
	)
	if err != nil {
		t.Fatalf("plan proposal binding: %v", err)
	}
	if result.ProposalID != "proposal-1" || len(transport.requests) != 1 {
		t.Fatalf("plan result=%+v requests=%+v", result, transport.requests)
	}
	sent := transport.requests[0]
	if sent.Packet.Path != "/gathering-plans/plan-1/proposals" ||
		sent.Claims.RequestDigest != gatheringplanclient.CanonicalRequestDigest(
			sent.Packet.CanonicalRequest,
		) {
		t.Fatalf("plan transport request=%+v body=%s", sent, sent.Packet.Body)
	}
}

type explicitTestCommercialProfile struct{}

func (explicitTestCommercialProfile) Allows(
	serviceclients.CircleGatheringOperationMetadata,
) bool {
	return true
}

func (explicitTestCommercialProfile) AllowsPlan(
	serviceclients.CircleGatheringPlanOperationMetadata,
) bool {
	return true
}

type recordingCircleGatheringTransport struct {
	requests []gatheringinfrastructure.CircleGatheringDelegatedGrantRequest
	response func(
		gatheringinfrastructure.CircleGatheringDelegatedGrantRequest,
	) gatheringclient.ResponsePacket
}

type recordingCircleGatheringPlanTransport struct {
	requests []gatheringinfrastructure.CircleGatheringPlanDelegatedGrantRequest
	response func(
		gatheringinfrastructure.CircleGatheringPlanDelegatedGrantRequest,
	) gatheringplanclient.ResponsePacket
}

func (transport *recordingCircleGatheringTransport) Execute(
	_ context.Context,
	request gatheringinfrastructure.CircleGatheringDelegatedGrantRequest,
) (gatheringclient.ResponsePacket, error) {
	transport.requests = append(transport.requests, request)
	if transport.response == nil {
		return gatheringclient.ResponsePacket{}, errors.New("unexpected transport")
	}
	return transport.response(request), nil
}

func (transport *recordingCircleGatheringPlanTransport) ExecuteGatheringPlan(
	_ context.Context,
	request gatheringinfrastructure.CircleGatheringPlanDelegatedGrantRequest,
) (gatheringplanclient.ResponsePacket, error) {
	transport.requests = append(transport.requests, request)
	if transport.response == nil {
		return gatheringplanclient.ResponsePacket{}, errors.New("unexpected transport")
	}
	return transport.response(request), nil
}

func queryCall(
	packet gatheringclient.RequestPacket,
	target runtimeauth.DelegatedResourceConstraint,
) tooling.VerifiedGatheringQueryCall {
	digest := gatheringclient.CanonicalRequestDigest(packet.CanonicalRequest)
	claims := delegatedClaims(
		runtimeauth.DelegatedGrantTypeQuery,
		packet.Operation.OperationID,
		digest,
		target,
	)
	return tooling.VerifiedGatheringQueryCall{
		Binding: tooling.DomainOperationBinding{
			OwnerService:   "circle-service",
			OperationID:    packet.Operation.OperationID,
			ContractDigest: packet.Operation.ContractDigest,
			RequestDigest:  digest,
			Target:         target,
		},
		Grant:           runtimeauth.DelegatedQueryGrant{Claims: claims},
		SerializedGrant: "delegated-grant",
	}
}

func commandCall(
	packet gatheringclient.RequestPacket,
	target runtimeauth.DelegatedResourceConstraint,
	idempotencyKey string,
) tooling.VerifiedGatheringCommandCall {
	digest := gatheringclient.CanonicalRequestDigest(packet.CanonicalRequest)
	claims := delegatedClaims(
		runtimeauth.DelegatedGrantTypeCommand,
		packet.Operation.OperationID,
		digest,
		target,
	)
	claims.IdempotencyKey = idempotencyKey
	claims.ApprovalRef = "approval-1"
	return tooling.VerifiedGatheringCommandCall{
		Binding: tooling.DomainOperationBinding{
			OwnerService:   "circle-service",
			OperationID:    packet.Operation.OperationID,
			ContractDigest: packet.Operation.ContractDigest,
			RequestDigest:  digest,
			Target:         target,
		},
		Grant:           runtimeauth.DelegatedCommandGrant{Claims: claims},
		SerializedGrant: "delegated-grant",
	}
}

func planCommandCall(
	packet gatheringplanclient.RequestPacket,
	target runtimeauth.DelegatedResourceConstraint,
	idempotencyKey string,
) tooling.VerifiedGatheringCommandCall {
	digest := gatheringplanclient.CanonicalRequestDigest(packet.CanonicalRequest)
	claims := delegatedClaims(
		runtimeauth.DelegatedGrantTypeCommand,
		packet.Operation.OperationID,
		digest,
		target,
	)
	claims.IdempotencyKey = idempotencyKey
	claims.ApprovalRef = "approval-1"
	return tooling.VerifiedGatheringCommandCall{
		Binding: tooling.DomainOperationBinding{
			OwnerService:   "circle-service",
			OperationID:    packet.Operation.OperationID,
			ContractDigest: packet.Operation.ContractDigest,
			RequestDigest:  digest,
			Target:         target,
		},
		Grant:           runtimeauth.DelegatedCommandGrant{Claims: claims},
		SerializedGrant: "delegated-grant",
	}
}

func delegatedClaims(
	grantType runtimeauth.DelegatedGrantType,
	operationID string,
	requestDigest string,
	target runtimeauth.DelegatedResourceConstraint,
) runtimeauth.DelegatedGrantClaims {
	return runtimeauth.DelegatedGrantClaims{
		GrantType:        grantType,
		Audience:         tooling.GatheringDelegateAudience,
		AccountID:        "account-1",
		PersonaID:        "persona-1",
		DelegateService:  tooling.GatheringDelegateService,
		RunID:            "run-1",
		ToolInvocationID: "tool-invocation-1",
		OperationID:      operationID,
		Resource:         target,
		RequestDigest:    requestDigest,
	}
}

func assertGeneratedDigest(
	t *testing.T,
	packet gatheringclient.RequestPacket,
) {
	t.Helper()
	sum := sha256.Sum256(packet.CanonicalRequest)
	want := "sha256:" + hex.EncodeToString(sum[:])
	if got := gatheringclient.CanonicalRequestDigest(
		packet.CanonicalRequest,
	); got != want {
		t.Fatalf("canonical digest=%q, want %q", got, want)
	}
	var canonical any
	if err := json.Unmarshal(packet.CanonicalRequest, &canonical); err != nil {
		t.Fatalf("canonical request is not JSON: %v", err)
	}
}

func assertGeneratedPlanDigest(
	t *testing.T,
	packet gatheringplanclient.RequestPacket,
) {
	t.Helper()
	sum := sha256.Sum256(packet.CanonicalRequest)
	want := "sha256:" + hex.EncodeToString(sum[:])
	if got := gatheringplanclient.CanonicalRequestDigest(
		packet.CanonicalRequest,
	); got != want {
		t.Fatalf("canonical plan digest=%q, want %q", got, want)
	}
	var canonical any
	if err := json.Unmarshal(packet.CanonicalRequest, &canonical); err != nil {
		t.Fatalf("canonical plan request is not JSON: %v", err)
	}
}
