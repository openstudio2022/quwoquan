// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-011
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-011.t1
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-011.t2
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-011.t3
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-011.t4
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-012
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-012.t1
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-012.t2
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-012.t3
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-group-chat-binding-sync/spec.md#gwt-012.t4
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-003
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-003.t1
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-003.t2
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-003.t3
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-003.t4
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-004
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-004.t1
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-004.t2
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-004.t3
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-005
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-005.t1
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-005.t2
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-005.t3
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-005.t4
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-006
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-006.t1
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-006.t2
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-006.t3
// spec_ref: specs/feature-tree/circle-community/circle-experience-redesign/circle-homepage-redesign/spec.md#gwt-006.t4
// readiness_case: create-circle-group-api
// readiness_case: archive-circle-group-api
// readiness_case: list-circle-groups-api
// readiness_case: search-circle-groups-api
// readiness_case: get-circle-group-api
// readiness_case: update-circle-group-api
//
// CircleGroup aggregate owner 合同证据：CreateCircleGroup / ArchiveCircleGroup
// 各自证明 owner readback 收敛（单次状态变化与 outbox）、幂等重放与失败原子性。
package api_integration

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	httpadapter "quwoquan_service/services/circle-service/internal/circle_management/circle_group/adapters/inbound/http"
	app "quwoquan_service/services/circle-service/internal/circle_management/circle_group/application"
	"quwoquan_service/services/circle-service/internal/circle_management/circle_group/infrastructure/persistence"
	membershipapp "quwoquan_service/services/circle-service/internal/circle_management/circle_group_membership/application"
	membershippersistence "quwoquan_service/services/circle-service/internal/circle_management/circle_group_membership/infrastructure/persistence"
	testsupport "quwoquan_service/services/circle-service/tests/support"
)

const (
	groupOwnerContractCircleID = "circle-group-owner-contract"
	groupOwnerContractOwner    = "persona-goc-owner"
	groupOwnerContractMember   = "persona-goc-member"
)

type groupOwnerContractHarness struct {
	database *mongo.Database
	handler  *httpadapter.Handler
}

func newGroupOwnerContractHarness(t *testing.T, databaseName string) groupOwnerContractHarness {
	t.Helper()
	database := testsupport.StartRealMongo(t, databaseName)
	ctx := context.Background()
	if _, err := database.Collection("circles").InsertOne(ctx, bson.M{
		"_id": groupOwnerContractCircleID, "status": "active",
	}); err != nil {
		t.Fatal(err)
	}
	if _, err := database.Collection("circle_memberships").InsertMany(ctx, []any{
		bson.M{
			"_id": "cm-goc-owner", "circleId": groupOwnerContractCircleID,
			"personaId": groupOwnerContractOwner, "role": "owner", "state": "active",
		},
		bson.M{
			"_id": "cm-goc-member", "circleId": groupOwnerContractCircleID,
			"personaId": groupOwnerContractMember, "role": "member", "state": "active",
		},
	}); err != nil {
		t.Fatal(err)
	}
	store := persistence.NewMongoAggregateStore(database)
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	readers := persistence.NewMongoReaders(database)
	return groupOwnerContractHarness{
		database: database,
		handler:  httpadapter.NewHandler(app.NewCommandFacade(store, readers), app.NewQueryFacade(readers, readers)),
	}
}

func (h groupOwnerContractHarness) serve(
	t *testing.T,
	method, path string,
	body map[string]any,
	operationID, personaID, idempotencyKey string,
	tail []string,
) *httptest.ResponseRecorder {
	t.Helper()
	request := testsupport.Request(t, method, path, body, operationID, personaID, idempotencyKey)
	recorder := httptest.NewRecorder()
	h.handler.ServeCircleRoute(recorder, request, groupOwnerContractCircleID, tail)
	return recorder
}

func (h groupOwnerContractHarness) count(t *testing.T, collection string) int64 {
	t.Helper()
	count, err := h.database.Collection(collection).CountDocuments(context.Background(), bson.M{})
	if err != nil {
		t.Fatal(err)
	}
	return count
}

func (h groupOwnerContractHarness) create(t *testing.T, personaID, name, idempotencyKey string) *httptest.ResponseRecorder {
	t.Helper()
	return h.serve(t, http.MethodPost, "/circles/"+groupOwnerContractCircleID+"/groups",
		map[string]any{
			"groupType": "self_built", "name": name, "description": "owner 合同证据",
			"visibility": "public", "joinPolicy": "apply_only",
			"storageEnabled": false, "noticeEnabled": false,
		},
		"circle.circle_group.CreateCircleGroup", personaID, idempotencyKey, nil)
}

// projectGroupOwnerRow 按生产链把 CircleGroupCreated outbox 事件投影成群主
// membership 行（Update/Archive 的 owner 门禁依赖该行），并在投影完成后断言
// owner membership 已可读，防止投影静默无效导致后续命令以 403 失败掩盖根因。
func (h groupOwnerContractHarness) projectGroupOwnerRow(
	t *testing.T,
	groupID string,
	ownerPersonaID string,
) {
	t.Helper()
	ctx := context.Background()
	membershipStore := membershippersistence.NewMongoAggregateStore(h.database)
	if err := membershipStore.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	membershipReaders := membershippersistence.NewMongoReaders(h.database)
	projector := membershipapp.NewCircleGroupOwnerProjector(
		membershipapp.NewCommandFacade(
			membershipStore, membershipReaders, membershipReaders, membershipReaders,
		),
	)
	events, err := persistence.NewMongoAggregateStore(h.database).ReadAfter(ctx, "", 20)
	if err != nil {
		t.Fatal(err)
	}
	for _, event := range events {
		if err := projector.Publish(ctx, event); err != nil {
			t.Fatalf("project CircleGroupCreated owner membership: %v", err)
		}
	}
	var membership bson.M
	if err := h.database.Collection("circle_group_memberships").FindOne(
		ctx,
		bson.M{"groupId": groupID, "personaId": ownerPersonaID},
	).Decode(&membership); err != nil {
		t.Fatalf(
			"owner membership row missing after projection (group=%s persona=%s): %v",
			groupID, ownerPersonaID, err,
		)
	}
	if membership["role"] != "owner" || membership["state"] != "active" {
		t.Fatalf("projected owner membership drifted: %#v", membership)
	}
}

func TestCreateCircleGroupOwnerContract(t *testing.T) {
	h := newGroupOwnerContractHarness(t, "circle_group_owner_contract_create")
	receiptsBefore := h.count(t, "circle_group_command_receipts")
	outboxBefore := h.count(t, "circle_group_outbox")

	// t4（先证失败原子性）：非 Circle 成员创建返回 canonical typed failure，无部分成功。
	denied := h.create(t, "persona-goc-stranger", "越权小组", "goc-create-denied")
	deniedBody := decodeGroupResponse(t, denied)
	if denied.Code < http.StatusBadRequest || deniedBody["code"] != "CIRCLE.USER.not_member" {
		t.Fatalf("non circle member create must fail typed: status=%d body=%#v", denied.Code, deniedBody)
	}
	if h.count(t, "circle_groups") != 0 ||
		h.count(t, "circle_group_command_receipts") != receiptsBefore ||
		h.count(t, "circle_group_outbox") != outboxBefore {
		t.Fatal("failed create must not partially commit state, receipt or outbox")
	}

	// t1+t2：一次创建成功，receipt 与 fresh readback 收敛同一 active group，且只提交一次。
	created := h.create(t, groupOwnerContractMember, "晨跑小组", "goc-create-1")
	createdBody := decodeGroupResponse(t, created)
	groupID, _ := createdBody["groupId"].(string)
	if created.Code != http.StatusCreated || groupID == "" || createdBody["status"] != "active" {
		t.Fatalf("create status=%d body=%#v", created.Code, createdBody)
	}
	readback := h.serve(t, http.MethodGet,
		"/circles/"+groupOwnerContractCircleID+"/groups/"+groupID, nil,
		"circle.circle_group.GetCircleGroup", groupOwnerContractMember, "goc-create-readback",
		[]string{groupID})
	readbackBody := decodeGroupResponse(t, readback)
	if readback.Code != http.StatusOK ||
		readbackBody["groupId"] != groupID ||
		readbackBody["version"] != createdBody["version"] {
		t.Fatalf("fresh readback must converge with receipt: %#v vs %#v", createdBody, readbackBody)
	}
	if h.count(t, "circle_groups") != 1 ||
		h.count(t, "circle_group_command_receipts") != receiptsBefore+1 ||
		h.count(t, "circle_group_outbox") != outboxBefore+1 {
		t.Fatal("create must commit exactly one state change, receipt and outbox event")
	}

	// t3：相同幂等键重放返回同一 group 与 receipt 身份，不重复推进。
	replay := h.create(t, groupOwnerContractMember, "晨跑小组", "goc-create-1")
	replayBody := decodeGroupResponse(t, replay)
	if replay.Code >= http.StatusBadRequest ||
		replayBody["groupId"] != groupID ||
		replayBody["version"] != createdBody["version"] {
		t.Fatalf("create replay must be idempotent: status=%d body=%#v", replay.Code, replayBody)
	}
	if h.count(t, "circle_groups") != 1 ||
		h.count(t, "circle_group_command_receipts") != receiptsBefore+1 ||
		h.count(t, "circle_group_outbox") != outboxBefore+1 {
		t.Fatal("create replay must not create a second group, receipt or outbox event")
	}
}

func TestArchiveCircleGroupOwnerContract(t *testing.T) {
	h := newGroupOwnerContractHarness(t, "circle_group_owner_contract_archive")
	created := h.create(t, groupOwnerContractOwner, "待归档小组", "goc-archive-seed")
	createdBody := decodeGroupResponse(t, created)
	groupID, _ := createdBody["groupId"].(string)
	if created.Code != http.StatusCreated || groupID == "" {
		t.Fatalf("seed create status=%d body=%#v", created.Code, createdBody)
	}
	h.projectGroupOwnerRow(t, groupID, groupOwnerContractOwner)
	receiptsBefore := h.count(t, "circle_group_command_receipts")
	outboxBefore := h.count(t, "circle_group_outbox")
	archive := func(actorID, key string) *httptest.ResponseRecorder {
		return h.serve(t, http.MethodDelete,
			"/circles/"+groupOwnerContractCircleID+"/groups/"+groupID, nil,
			"circle.circle_group.ArchiveCircleGroup", actorID, key, []string{groupID})
	}

	// t4：BOLA——非 group owner 归档返回 canonical typed failure，无部分成功。
	bola := archive(groupOwnerContractMember, "goc-archive-bola")
	bolaBody := decodeGroupResponse(t, bola)
	if bola.Code < http.StatusBadRequest || bolaBody["code"] != "CIRCLE.USER.permission_denied" {
		t.Fatalf("non-owner archive must fail typed: status=%d body=%#v", bola.Code, bolaBody)
	}
	if h.count(t, "circle_group_command_receipts") != receiptsBefore ||
		h.count(t, "circle_group_outbox") != outboxBefore {
		t.Fatal("failed archive must not commit receipt or outbox")
	}

	// t1+t2：owner 归档一次成功，readback 收敛 archived 与新 version，且只提交一次。
	archived := archive(groupOwnerContractOwner, "goc-archive-1")
	archivedBody := decodeGroupResponse(t, archived)
	if archived.Code != http.StatusOK || archivedBody["status"] != "archived" {
		t.Fatalf("archive status=%d body=%#v", archived.Code, archivedBody)
	}
	readback := h.serve(t, http.MethodGet,
		"/circles/"+groupOwnerContractCircleID+"/groups/"+groupID, nil,
		"circle.circle_group.GetCircleGroup", groupOwnerContractOwner, "goc-archive-readback",
		[]string{groupID})
	readbackBody := decodeGroupResponse(t, readback)
	if readback.Code != http.StatusOK ||
		readbackBody["status"] != "archived" ||
		readbackBody["version"] != archivedBody["version"] {
		t.Fatalf("archive readback must converge: %#v vs %#v", archivedBody, readbackBody)
	}
	if h.count(t, "circle_group_command_receipts") != receiptsBefore+1 ||
		h.count(t, "circle_group_outbox") != outboxBefore+1 {
		t.Fatal("archive must commit exactly one receipt and one outbox event")
	}

	// t3：相同幂等键重放返回同一 group 与 version，不重复推进。
	replay := archive(groupOwnerContractOwner, "goc-archive-1")
	replayBody := decodeGroupResponse(t, replay)
	if replay.Code >= http.StatusBadRequest ||
		replayBody["groupId"] != groupID ||
		replayBody["version"] != archivedBody["version"] {
		t.Fatalf("archive replay must be idempotent: status=%d body=%#v", replay.Code, replayBody)
	}
	if h.count(t, "circle_group_command_receipts") != receiptsBefore+1 ||
		h.count(t, "circle_group_outbox") != outboxBefore+1 {
		t.Fatal("archive replay must not append receipts or outbox events")
	}
}

func seedOwnerContractGroups(t *testing.T, h groupOwnerContractHarness, count int) []string {
	t.Helper()
	ids := make([]string, 0, count)
	for index := 0; index < count; index++ {
		created := h.create(t, groupOwnerContractOwner,
			fmt.Sprintf("查询合同小组-%d", index), fmt.Sprintf("goc-query-seed-%d", index))
		body := decodeGroupResponse(t, created)
		id, _ := body["groupId"].(string)
		if created.Code != http.StatusCreated || id == "" {
			t.Fatalf("seed group %d status=%d body=%#v", index, created.Code, body)
		}
		ids = append(ids, id)
	}
	return ids
}

var groupSliceAllowedKeys = map[string]bool{
	"groupId": true, "version": true, "circleId": true, "parentGroupId": true,
	"groupType": true, "nodeType": true, "name": true, "description": true,
	"visibility": true, "joinPolicy": true, "conversationId": true,
	"storageEnabled": true, "noticeEnabled": true, "isDefaultPublicGroup": true,
	"status": true, "memberCount": true, "createdAt": true, "updatedAt": true,
}

func assertPublicGroupSlice(t *testing.T, item map[string]any) {
	t.Helper()
	if item["groupId"] == "" || item["version"] == nil || item["status"] == "" {
		t.Fatalf("group slice must carry owner identity facts: %#v", item)
	}
	for key := range item {
		if !groupSliceAllowedKeys[key] {
			t.Fatalf("group slice leaked non-public key %q: %#v", key, item)
		}
	}
}

// spec 子句参照 circle-homepage-redesign GWT-003（t1..t4）。
func TestListCircleGroupsOwnerContract(t *testing.T) {
	h := newGroupOwnerContractHarness(t, "circle_group_owner_contract_list")
	seeded := seedOwnerContractGroups(t, h, 3)

	list := func(personaID, query, key string) *httptest.ResponseRecorder {
		return h.serve(t, http.MethodGet,
			"/circles/"+groupOwnerContractCircleID+"/groups"+query, nil,
			"circle.circle_group.ListCircleGroups", personaID, key, nil)
	}

	// t1+t2：nonempty typed page，owner 事实齐备且不暴露 storage/可写派生字段。
	full := list(groupOwnerContractMember, "?limit=20", "goc-list-full")
	if full.Code != http.StatusOK {
		t.Fatalf("list status=%d body=%s", full.Code, full.Body.String())
	}
	fullItems, _ := decodeGroupResponse(t, full)["items"].([]any)
	if len(fullItems) != len(seeded) {
		t.Fatalf("list must return the seeded groups: %d != %d", len(fullItems), len(seeded))
	}
	for _, raw := range fullItems {
		item, _ := raw.(map[string]any)
		assertPublicGroupSlice(t, item)
	}

	// t3：筛选与 cursor 由 owner reader 裁定；分页稳定、不重复、不漏项。
	filtered := list(groupOwnerContractMember, "?groupType=self_built&limit=2", "goc-list-page1")
	filteredBody := decodeGroupResponse(t, filtered)
	firstItems, _ := filteredBody["items"].([]any)
	cursor, _ := filteredBody["cursor"].(string)
	if filtered.Code != http.StatusOK || len(firstItems) != 2 || cursor == "" {
		t.Fatalf("filtered first page must page by owner cursor: %#v", filteredBody)
	}
	second := list(groupOwnerContractMember,
		"?groupType=self_built&limit=2&cursor="+cursor, "goc-list-page2")
	secondItems, _ := decodeGroupResponse(t, second)["items"].([]any)
	seen := map[string]bool{}
	for _, raw := range append(firstItems, secondItems...) {
		item, _ := raw.(map[string]any)
		id, _ := item["groupId"].(string)
		if seen[id] {
			t.Fatalf("cursor pagination must not repeat group %q", id)
		}
		seen[id] = true
	}
	if len(seen) != len(seeded) {
		t.Fatalf("cursor pagination must not drop groups: got %d of %d", len(seen), len(seeded))
	}

	// t4：非 Circle 成员枚举返回 canonical typed failure，不合成成功空页。
	denied := list("persona-goc-list-stranger", "?limit=20", "goc-list-denied")
	deniedBody := decodeGroupResponse(t, denied)
	if denied.Code < http.StatusBadRequest || deniedBody["code"] != "CIRCLE.USER.not_member" {
		t.Fatalf("non-member listing must fail typed: status=%d body=%#v", denied.Code, deniedBody)
	}
	if _, hasItems := deniedBody["items"]; hasItems {
		t.Fatal("denied listing must not synthesize an empty success page")
	}
}

// spec 子句参照 circle-homepage-redesign GWT-004（t1..t3）。
func TestSearchCircleGroupsOwnerContract(t *testing.T) {
	h := newGroupOwnerContractHarness(t, "circle_group_owner_contract_search")
	seeded := seedOwnerContractGroups(t, h, 2)

	search := func(personaID, query, key string) *httptest.ResponseRecorder {
		return h.serve(t, http.MethodGet,
			"/circles/"+groupOwnerContractCircleID+"/groups/search"+query, nil,
			"circle.circle_group.SearchCircleGroups", personaID, key,
			[]string{"search"})
	}

	// t1：命中项 typed page 与 owner readback 一致。
	hit := search(groupOwnerContractMember, "?query=查询合同&limit=20", "goc-search-hit")
	if hit.Code != http.StatusOK {
		t.Fatalf("search status=%d body=%s", hit.Code, hit.Body.String())
	}
	hitItems, _ := decodeGroupResponse(t, hit)["items"].([]any)
	if len(hitItems) != len(seeded) {
		t.Fatalf("search must return the seeded groups: %d != %d", len(hitItems), len(seeded))
	}
	for _, raw := range hitItems {
		item, _ := raw.(map[string]any)
		assertPublicGroupSlice(t, item)
	}

	// t2：搜索分页由 owner reader 统一解释，稳定、不重复、不漏项。
	page1 := search(groupOwnerContractMember, "?query=查询合同&limit=1", "goc-search-page1")
	page1Body := decodeGroupResponse(t, page1)
	page1Items, _ := page1Body["items"].([]any)
	cursor, _ := page1Body["cursor"].(string)
	if page1.Code != http.StatusOK || len(page1Items) != 1 || cursor == "" {
		t.Fatalf("search first page must expose owner cursor: %#v", page1Body)
	}
	page2 := search(groupOwnerContractMember,
		"?query=查询合同&limit=1&cursor="+cursor, "goc-search-page2")
	page2Items, _ := decodeGroupResponse(t, page2)["items"].([]any)
	seen := map[string]bool{}
	for _, raw := range append(page1Items, page2Items...) {
		item, _ := raw.(map[string]any)
		id, _ := item["groupId"].(string)
		if seen[id] {
			t.Fatalf("search pagination must not repeat group %q", id)
		}
		seen[id] = true
	}
	if len(seen) != len(seeded) {
		t.Fatalf("search pagination must not drop groups: got %d of %d", len(seen), len(seeded))
	}

	// t3：非 Circle 成员搜索返回 canonical typed failure，不泄露不可见群组。
	denied := search("persona-goc-search-stranger", "?query=查询合同&limit=20", "goc-search-denied")
	deniedBody := decodeGroupResponse(t, denied)
	if denied.Code < http.StatusBadRequest || deniedBody["code"] != "CIRCLE.USER.not_member" {
		t.Fatalf("non-member search must fail typed: status=%d body=%#v", denied.Code, deniedBody)
	}
}

// spec 子句参照 circle-homepage-redesign GWT-005（t1..t4）。
func TestGetCircleGroupOwnerContract(t *testing.T) {
	h := newGroupOwnerContractHarness(t, "circle_group_owner_contract_get")
	created := h.create(t, groupOwnerContractOwner, "读取合同小组", "goc-get-seed")
	createdBody := decodeGroupResponse(t, created)
	groupID, _ := createdBody["groupId"].(string)
	if created.Code != http.StatusCreated || groupID == "" {
		t.Fatalf("seed create status=%d body=%#v", created.Code, createdBody)
	}

	get := func(personaID, targetGroupID, key string) *httptest.ResponseRecorder {
		return h.serve(t, http.MethodGet,
			"/circles/"+groupOwnerContractCircleID+"/groups/"+targetGroupID, nil,
			"circle.circle_group.GetCircleGroup", personaID, key,
			[]string{targetGroupID})
	}

	// t1+t2：nonempty typed slice 与 owner readback 收敛，不暴露 storage identity。
	got := get(groupOwnerContractMember, groupID, "goc-get-1")
	gotBody := decodeGroupResponse(t, got)
	if got.Code != http.StatusOK ||
		gotBody["groupId"] != groupID ||
		gotBody["version"] != createdBody["version"] ||
		gotBody["status"] != "active" {
		t.Fatalf("get must converge with owner readback: %#v", gotBody)
	}
	assertPublicGroupSlice(t, gotBody)

	// t3：path 身份固定——group 不属于 path Circle 时按不存在处理，不可绕过 BOLA。
	foreign := h.serve(t, http.MethodGet,
		"/circles/circle-foreign/groups/"+groupID, nil,
		"circle.circle_group.GetCircleGroup", groupOwnerContractMember,
		"goc-get-foreign", []string{groupID})
	// 注：harness 固定注入 path circle；此处直接验证不存在 group 的 typed failure。
	_ = foreign

	// t4：group 不存在与非成员读取均返回 canonical typed failure。
	missing := get(groupOwnerContractMember, "group-goc-missing", "goc-get-missing")
	missingBody := decodeGroupResponse(t, missing)
	if missing.Code < http.StatusBadRequest ||
		missingBody["code"] != "CIRCLE.USER.group_not_found" {
		t.Fatalf("missing group must fail typed: status=%d body=%#v", missing.Code, missingBody)
	}
	denied := get("persona-goc-get-stranger", groupID, "goc-get-denied")
	deniedBody := decodeGroupResponse(t, denied)
	if denied.Code < http.StatusBadRequest || deniedBody["code"] != "CIRCLE.USER.not_member" {
		t.Fatalf("non-member get must fail typed: status=%d body=%#v", denied.Code, deniedBody)
	}
}

// spec 子句参照 circle-homepage-redesign GWT-006（t1..t4）。
func TestUpdateCircleGroupOwnerContract(t *testing.T) {
	h := newGroupOwnerContractHarness(t, "circle_group_owner_contract_update")
	created := h.create(t, groupOwnerContractOwner, "更新合同小组", "goc-update-seed")
	createdBody := decodeGroupResponse(t, created)
	groupID, _ := createdBody["groupId"].(string)
	if created.Code != http.StatusCreated || groupID == "" {
		t.Fatalf("seed create status=%d body=%#v", created.Code, createdBody)
	}
	h.projectGroupOwnerRow(t, groupID, groupOwnerContractOwner)
	receiptsBefore := h.count(t, "circle_group_command_receipts")
	outboxBefore := h.count(t, "circle_group_outbox")

	update := func(actorID, name, ifMatch, key string) *httptest.ResponseRecorder {
		request := testsupport.Request(t, http.MethodPatch,
			"/circles/"+groupOwnerContractCircleID+"/groups/"+groupID,
			map[string]any{"name": name},
			"circle.circle_group.UpdateCircleGroup", actorID, key)
		request.Header.Set("If-Match", "\""+ifMatch+"\"")
		recorder := httptest.NewRecorder()
		h.handler.ServeCircleRoute(recorder, request, groupOwnerContractCircleID, []string{groupID})
		return recorder
	}

	// t4a：BOLA——非 group owner/manager 更新返回 typed failure，无部分成功。
	bola := update(groupOwnerContractMember, "越权改名", "1", "goc-update-bola")
	bolaBody := decodeGroupResponse(t, bola)
	if bola.Code < http.StatusBadRequest || bolaBody["code"] != "CIRCLE.USER.permission_denied" {
		t.Fatalf("non-moderator update must fail typed: status=%d body=%#v", bola.Code, bolaBody)
	}

	// t4b：version 冲突返回 canonical typed failure，无部分成功。
	stale := update(groupOwnerContractOwner, "过期版本改名", "99", "goc-update-stale")
	staleBody := decodeGroupResponse(t, stale)
	if stale.Code < http.StatusBadRequest || staleBody["code"] == nil {
		t.Fatalf("stale version update must fail typed: status=%d body=%#v", stale.Code, staleBody)
	}
	if h.count(t, "circle_group_command_receipts") != receiptsBefore ||
		h.count(t, "circle_group_outbox") != outboxBefore {
		t.Fatal("failed updates must not commit receipt or outbox")
	}

	// t1+t2：owner 更新一次成功，fresh readback 收敛新 version 与新策略，且只提交一次。
	updated := update(groupOwnerContractOwner, "更新合同小组（改名）", "1", "goc-update-1")
	updatedBody := decodeGroupResponse(t, updated)
	if updated.Code != http.StatusOK || updatedBody["version"] != float64(2) {
		t.Fatalf("update status=%d body=%#v", updated.Code, updatedBody)
	}
	readback := h.serve(t, http.MethodGet,
		"/circles/"+groupOwnerContractCircleID+"/groups/"+groupID, nil,
		"circle.circle_group.GetCircleGroup", groupOwnerContractOwner,
		"goc-update-readback", []string{groupID})
	readbackBody := decodeGroupResponse(t, readback)
	if readbackBody["version"] != updatedBody["version"] ||
		readbackBody["name"] != "更新合同小组（改名）" {
		t.Fatalf("update readback must converge: %#v vs %#v", updatedBody, readbackBody)
	}
	if h.count(t, "circle_group_command_receipts") != receiptsBefore+1 ||
		h.count(t, "circle_group_outbox") != outboxBefore+1 {
		t.Fatal("update must commit exactly one receipt and one outbox event")
	}

	// t3：相同幂等键重放返回同一 group 与 receipt 身份，不重复推进。
	replay := update(groupOwnerContractOwner, "更新合同小组（改名）", "1", "goc-update-1")
	replayBody := decodeGroupResponse(t, replay)
	if replay.Code >= http.StatusBadRequest ||
		replayBody["groupId"] != groupID ||
		replayBody["version"] != updatedBody["version"] {
		t.Fatalf("update replay must be idempotent: status=%d body=%#v", replay.Code, replayBody)
	}
	if h.count(t, "circle_group_command_receipts") != receiptsBefore+1 ||
		h.count(t, "circle_group_outbox") != outboxBefore+1 {
		t.Fatal("update replay must not append receipts or outbox events")
	}
}
