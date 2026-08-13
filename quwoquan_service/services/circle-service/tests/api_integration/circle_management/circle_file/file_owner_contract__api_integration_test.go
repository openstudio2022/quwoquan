// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-file-collaboration/spec.md#gwt-001
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-file-collaboration/spec.md#gwt-001.t1
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-file-collaboration/spec.md#gwt-001.t2
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-file-collaboration/spec.md#gwt-002
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-file-collaboration/spec.md#gwt-002.t1
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-file-collaboration/spec.md#gwt-002.t2
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-file-collaboration/spec.md#gwt-003
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-file-collaboration/spec.md#gwt-003.t1
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-file-collaboration/spec.md#gwt-003.t2
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-file-collaboration/spec.md#gwt-003.t3
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-file-collaboration/spec.md#gwt-003.t4
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-file-collaboration/spec.md#gwt-004
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-file-collaboration/spec.md#gwt-004.t1
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-file-collaboration/spec.md#gwt-004.t2
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-file-collaboration/spec.md#gwt-004.t3
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-file-collaboration/spec.md#gwt-004.t4
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-file-collaboration/spec.md#gwt-005
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-file-collaboration/spec.md#gwt-005.t1
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-file-collaboration/spec.md#gwt-005.t2
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-file-collaboration/spec.md#gwt-005.t3
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-file-collaboration/spec.md#gwt-005.t4
// spec_ref: specs/feature-tree/circle-community/circle-collaboration-tools/circle-file-collaboration/spec.md#gwt-005.t5
// readiness_case: list-circle-files-api
// readiness_case: create-circle-file-api
// readiness_case: get-circle-file-api
// readiness_case: update-circle-file-api
// readiness_case: delete-circle-file-api
//
// CircleFile owner 合同证据：List/Get/Create/Update/Delete 各证明 typed page/
// slice 收敛、稳定分页、幂等重放与 BOLA/version/幂等冲突的失败原子性；
// slice 不暴露 storage identity、object key 或 upload URL。
package api_integration

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"

	"go.mongodb.org/mongo-driver/v2/bson"
	"go.mongodb.org/mongo-driver/v2/mongo"

	httpadapter "quwoquan_service/services/circle-service/internal/circle_management/circle_file/adapters/inbound/http"
	app "quwoquan_service/services/circle-service/internal/circle_management/circle_file/application"
	"quwoquan_service/services/circle-service/internal/circle_management/circle_file/infrastructure/persistence"
	testsupport "quwoquan_service/services/circle-service/tests/support"
)

const (
	fileContractCircleID = "circle-file-contract"
	fileContractOwner    = "persona-fc-owner"
)

type fileContractHarness struct {
	database *mongo.Database
	handler  *httpadapter.Handler
}

func newFileContractHarness(t *testing.T, databaseName string) fileContractHarness {
	t.Helper()
	database := testsupport.StartRealMongo(t, databaseName)
	ctx := context.Background()
	if _, err := database.Collection("circles").InsertOne(ctx, bson.M{
		"_id": fileContractCircleID, "status": "active", "storageQuotaBytes": int64(1 << 20),
	}); err != nil {
		t.Fatal(err)
	}
	if _, err := database.Collection("circle_memberships").InsertOne(ctx, bson.M{
		"_id": "cm-fc-owner", "circleId": fileContractCircleID,
		"personaId": fileContractOwner, "role": "owner", "state": "active",
	}); err != nil {
		t.Fatal(err)
	}
	store := persistence.NewMongoAggregateStore(database)
	if err := store.EnsureIndexes(ctx); err != nil {
		t.Fatal(err)
	}
	readers := persistence.NewMongoReaders(database)
	return fileContractHarness{
		database: database,
		handler: httpadapter.NewHandler(
			app.NewCommandFacade(store, readers, mediaAssetReader{}),
			app.NewQueryFacade(readers, readers),
		),
	}
}

func (h fileContractHarness) serve(
	t *testing.T,
	method, path string,
	body map[string]any,
	operationID, personaID, idempotencyKey, ifMatch string,
	tail []string,
) *httptest.ResponseRecorder {
	t.Helper()
	request := testsupport.Request(t, method, path, body, operationID, personaID, idempotencyKey)
	if ifMatch != "" {
		request.Header.Set("If-Match", "\""+ifMatch+"\"")
	}
	recorder := httptest.NewRecorder()
	h.handler.ServeCircleRoute(recorder, request, fileContractCircleID, tail)
	return recorder
}

func (h fileContractHarness) count(t *testing.T, collection string) int64 {
	t.Helper()
	count, err := h.database.Collection(collection).CountDocuments(context.Background(), bson.M{})
	if err != nil {
		t.Fatal(err)
	}
	return count
}

func (h fileContractHarness) createFolder(t *testing.T, personaID, name, key string) map[string]any {
	t.Helper()
	created := h.serve(t, http.MethodPost,
		"/circles/"+fileContractCircleID+"/files",
		map[string]any{"name": name, "fileType": "folder"},
		"circle.circle_file.CreateCircleFile", personaID, key, "", nil)
	body := decodeFileResponse(t, created)
	if created.Code != http.StatusCreated {
		t.Fatalf("create folder %s status=%d body=%#v", name, created.Code, body)
	}
	return body
}

func (h fileContractHarness) getFile(t *testing.T, personaID, fileID, key string) *httptest.ResponseRecorder {
	t.Helper()
	return h.serve(t, http.MethodGet,
		"/circles/"+fileContractCircleID+"/files/"+fileID, nil,
		"circle.circle_file.GetCircleFile", personaID, key, "",
		[]string{fileID})
}

func decodeFileResponse(t *testing.T, recorder *httptest.ResponseRecorder) map[string]any {
	t.Helper()
	var value map[string]any
	if err := json.Unmarshal(recorder.Body.Bytes(), &value); err != nil {
		t.Fatalf("decode CircleFile response: %v body=%s", err, recorder.Body.String())
	}
	return value
}

var circleFileForbiddenSliceKeys = []string{"objectKey", "uploadUrl", "storageKey", "bucket"}

func assertPublicFileSlice(t *testing.T, item map[string]any) {
	t.Helper()
	if item["fileId"] == "" || item["version"] == nil {
		t.Fatalf("file slice must carry owner identity facts: %#v", item)
	}
	for _, key := range circleFileForbiddenSliceKeys {
		if _, leaked := item[key]; leaked {
			t.Fatalf("file slice leaked storage identity key %q: %#v", key, item)
		}
	}
}

func TestListCircleFilesOwnerContract(t *testing.T) {
	h := newFileContractHarness(t, "circle_file_owner_contract_list")
	seeded := make([]string, 0, 3)
	for index := 0; index < 3; index++ {
		body := h.createFolder(t, fileContractOwner,
			fmt.Sprintf("资料夹-%d", index), fmt.Sprintf("fc-list-seed-%d", index))
		id, _ := body["fileId"].(string)
		seeded = append(seeded, id)
	}
	list := func(personaID, query, key string) *httptest.ResponseRecorder {
		return h.serve(t, http.MethodGet,
			"/circles/"+fileContractCircleID+"/files"+query, nil,
			"circle.circle_file.ListCircleFiles", personaID, key, "", nil)
	}

	// t1：nonempty typed page，顺序与 cursor 稳定、不重不漏。
	page1 := list(fileContractOwner, "?limit=2", "fc-list-page1")
	page1Body := decodeFileResponse(t, page1)
	page1Items, _ := page1Body["items"].([]any)
	cursor, _ := page1Body["cursor"].(string)
	if page1.Code != http.StatusOK || len(page1Items) != 2 || cursor == "" {
		t.Fatalf("first page must page by owner cursor: %#v", page1Body)
	}
	for _, raw := range page1Items {
		item, _ := raw.(map[string]any)
		assertPublicFileSlice(t, item)
	}
	page2 := list(fileContractOwner, "?limit=2&cursor="+cursor, "fc-list-page2")
	page2Items, _ := decodeFileResponse(t, page2)["items"].([]any)
	seen := map[string]bool{}
	for _, raw := range append(page1Items, page2Items...) {
		item, _ := raw.(map[string]any)
		id, _ := item["fileId"].(string)
		if seen[id] {
			t.Fatalf("cursor pagination must not repeat file %q", id)
		}
		seen[id] = true
	}
	if len(seen) != len(seeded) {
		t.Fatalf("cursor pagination must not drop files: got %d of %d", len(seen), len(seeded))
	}

	// t2：无权访问返回 canonical typed failure，不合成成功空页。
	denied := list("persona-fc-stranger", "?limit=20", "fc-list-denied")
	deniedBody := decodeFileResponse(t, denied)
	if denied.Code < http.StatusBadRequest || deniedBody["code"] == nil {
		t.Fatalf("non-member listing must fail typed: status=%d body=%#v", denied.Code, deniedBody)
	}
	if _, hasItems := deniedBody["items"]; hasItems {
		t.Fatal("denied listing must not synthesize an empty success page")
	}
}

func TestGetCircleFileOwnerContract(t *testing.T) {
	h := newFileContractHarness(t, "circle_file_owner_contract_get")
	created := h.createFolder(t, fileContractOwner, "读取资料夹", "fc-get-seed")
	fileID, _ := created["fileId"].(string)

	// t1：nonempty typed slice 与 owner readback 一致，不含 storage identity。
	got := h.getFile(t, fileContractOwner, fileID, "fc-get-1")
	gotBody := decodeFileResponse(t, got)
	if got.Code != http.StatusOK ||
		gotBody["fileId"] != fileID ||
		gotBody["version"] != created["version"] {
		t.Fatalf("get must converge with owner readback: %#v", gotBody)
	}
	assertPublicFileSlice(t, gotBody)

	// t2：不存在与 BOLA 返回 canonical typed failure，不以空 slice 合成成功。
	missing := h.getFile(t, fileContractOwner, "file-fc-missing", "fc-get-missing")
	missingBody := decodeFileResponse(t, missing)
	if missing.Code < http.StatusBadRequest ||
		missingBody["code"] != "CIRCLE.USER.file_not_found" {
		t.Fatalf("missing file must fail typed: status=%d body=%#v", missing.Code, missingBody)
	}
	denied := h.getFile(t, "persona-fc-stranger", fileID, "fc-get-denied")
	deniedBody := decodeFileResponse(t, denied)
	if denied.Code < http.StatusBadRequest || deniedBody["code"] == nil {
		t.Fatalf("non-member get must fail typed: status=%d body=%#v", denied.Code, deniedBody)
	}
}

func TestCreateCircleFileOwnerContract(t *testing.T) {
	h := newFileContractHarness(t, "circle_file_owner_contract_create")
	receiptsBefore := h.count(t, "circle_files_command_receipts")
	outboxBefore := h.count(t, "circle_files_outbox")

	// t3+t4：BOLA 与非法输入返回 canonical typed failure，无部分成功。
	denied := h.serve(t, http.MethodPost,
		"/circles/"+fileContractCircleID+"/files",
		map[string]any{"name": "越权资料夹", "fileType": "folder"},
		"circle.circle_file.CreateCircleFile", "persona-fc-stranger", "fc-create-denied", "", nil)
	deniedBody := decodeFileResponse(t, denied)
	if denied.Code < http.StatusBadRequest || deniedBody["code"] == nil {
		t.Fatalf("non-member create must fail typed: status=%d body=%#v", denied.Code, deniedBody)
	}
	if h.count(t, "circle_files") != 0 ||
		h.count(t, "circle_files_command_receipts") != receiptsBefore ||
		h.count(t, "circle_files_outbox") != outboxBefore {
		t.Fatal("failed create must not partially commit state, receipt or outbox")
	}

	// t1+t2：一次创建成功，fresh readback 收敛同一 identity/version，且只提交一次。
	created := h.createFolder(t, fileContractOwner, "创建合同资料夹", "fc-create-1")
	fileID, _ := created["fileId"].(string)
	readback := decodeFileResponse(t, h.getFile(t, fileContractOwner, fileID, "fc-create-readback"))
	if readback["fileId"] != fileID || readback["version"] != created["version"] {
		t.Fatalf("create readback must converge: %#v vs %#v", created, readback)
	}
	if h.count(t, "circle_files") != 1 ||
		h.count(t, "circle_files_command_receipts") != receiptsBefore+1 ||
		h.count(t, "circle_files_outbox") != outboxBefore+1 {
		t.Fatal("create must commit exactly one state, receipt and outbox event")
	}

	// t3（重放段）：同键同语义重放返回同一 file/receipt。
	replay := h.serve(t, http.MethodPost,
		"/circles/"+fileContractCircleID+"/files",
		map[string]any{"name": "创建合同资料夹", "fileType": "folder"},
		"circle.circle_file.CreateCircleFile", fileContractOwner, "fc-create-1", "", nil)
	replayBody := decodeFileResponse(t, replay)
	if replay.Code >= http.StatusBadRequest ||
		replayBody["fileId"] != fileID ||
		replayBody["version"] != created["version"] {
		t.Fatalf("create replay must be idempotent: status=%d body=%#v", replay.Code, replayBody)
	}
	if h.count(t, "circle_files") != 1 ||
		h.count(t, "circle_files_command_receipts") != receiptsBefore+1 ||
		h.count(t, "circle_files_outbox") != outboxBefore+1 {
		t.Fatal("create replay must not create a second file, receipt or outbox event")
	}

	// t4（幂等冲突段）：同键冲突输入返回 canonical idempotency failure。
	conflict := h.serve(t, http.MethodPost,
		"/circles/"+fileContractCircleID+"/files",
		map[string]any{"name": "同键不同名", "fileType": "folder"},
		"circle.circle_file.CreateCircleFile", fileContractOwner, "fc-create-1", "", nil)
	conflictBody := decodeFileResponse(t, conflict)
	if conflict.Code < http.StatusBadRequest ||
		conflictBody["code"] != "CIRCLE.USER.file_idempotency_conflict" {
		t.Fatalf(
			"conflicting reuse of the idempotency key must fail typed: status=%d body=%#v",
			conflict.Code, conflictBody,
		)
	}
}

func TestUpdateCircleFileOwnerContract(t *testing.T) {
	h := newFileContractHarness(t, "circle_file_owner_contract_update")
	created := h.createFolder(t, fileContractOwner, "更新合同资料夹", "fc-update-seed")
	fileID, _ := created["fileId"].(string)
	receiptsBefore := h.count(t, "circle_files_command_receipts")
	outboxBefore := h.count(t, "circle_files_outbox")
	update := func(personaID, name, ifMatch, key string) *httptest.ResponseRecorder {
		return h.serve(t, http.MethodPatch,
			"/circles/"+fileContractCircleID+"/files/"+fileID,
			map[string]any{"name": name},
			"circle.circle_file.UpdateCircleFile", personaID, key, ifMatch,
			[]string{fileID})
	}

	// t3+t4：BOLA 与 stale version 返回 canonical typed failure，无部分成功。
	denied := update("persona-fc-stranger", "越权改名", "1", "fc-update-denied")
	deniedBody := decodeFileResponse(t, denied)
	if denied.Code < http.StatusBadRequest || deniedBody["code"] == nil {
		t.Fatalf("non-member update must fail typed: status=%d body=%#v", denied.Code, deniedBody)
	}
	stale := update(fileContractOwner, "过期改名", "99", "fc-update-stale")
	staleBody := decodeFileResponse(t, stale)
	if stale.Code < http.StatusBadRequest ||
		staleBody["code"] != "CIRCLE.USER.file_version_conflict" {
		t.Fatalf("stale version update must fail typed: status=%d body=%#v", stale.Code, staleBody)
	}
	if h.count(t, "circle_files_command_receipts") != receiptsBefore ||
		h.count(t, "circle_files_outbox") != outboxBefore {
		t.Fatal("failed updates must not commit receipt or outbox")
	}

	// t1+t2：一次更新成功，fresh readback 收敛新 name 与 version，且只提交一次。
	updated := decodeFileResponse(t, update(fileContractOwner, "更新合同资料夹（改名）", "1", "fc-update-1"))
	readback := decodeFileResponse(t, h.getFile(t, fileContractOwner, fileID, "fc-update-readback"))
	if readback["version"] != updated["version"] || readback["name"] != "更新合同资料夹（改名）" {
		t.Fatalf("update readback must converge: %#v vs %#v", updated, readback)
	}
	if h.count(t, "circle_files_command_receipts") != receiptsBefore+1 ||
		h.count(t, "circle_files_outbox") != outboxBefore+1 {
		t.Fatal("update must commit exactly one receipt and one outbox event")
	}

	// t3（重放段）：同键同语义重放稳定，不重复推进。
	replay := decodeFileResponse(t, update(fileContractOwner, "更新合同资料夹（改名）", "1", "fc-update-1"))
	if replay["fileId"] != fileID || replay["version"] != updated["version"] {
		t.Fatalf("update replay must be idempotent: %#v vs %#v", replay, updated)
	}
	if h.count(t, "circle_files_command_receipts") != receiptsBefore+1 ||
		h.count(t, "circle_files_outbox") != outboxBefore+1 {
		t.Fatal("update replay must not append receipts or outbox events")
	}
}

func TestDeleteCircleFileOwnerContract(t *testing.T) {
	h := newFileContractHarness(t, "circle_file_owner_contract_delete")
	created := h.createFolder(t, fileContractOwner, "删除合同资料夹", "fc-delete-seed")
	fileID, _ := created["fileId"].(string)
	receiptsBefore := h.count(t, "circle_files_command_receipts")
	outboxBefore := h.count(t, "circle_files_outbox")
	remove := func(personaID, targetID, key string) *httptest.ResponseRecorder {
		return h.serve(t, http.MethodDelete,
			"/circles/"+fileContractCircleID+"/files/"+targetID, nil,
			"circle.circle_file.DeleteCircleFile", personaID, key, "",
			[]string{targetID})
	}

	// t4+t5：BOLA 与不存在返回 canonical typed failure，无部分 state/receipt/outbox。
	denied := remove("persona-fc-stranger", fileID, "fc-delete-denied")
	deniedBody := decodeFileResponse(t, denied)
	if denied.Code < http.StatusBadRequest || deniedBody["code"] == nil {
		t.Fatalf("non-member delete must fail typed: status=%d body=%#v", denied.Code, deniedBody)
	}
	missing := remove(fileContractOwner, "file-fc-missing", "fc-delete-missing")
	missingBody := decodeFileResponse(t, missing)
	if missing.Code < http.StatusBadRequest ||
		missingBody["code"] != "CIRCLE.USER.file_not_found" {
		t.Fatalf("missing delete must fail typed: status=%d body=%#v", missing.Code, missingBody)
	}
	if h.count(t, "circle_files_command_receipts") != receiptsBefore ||
		h.count(t, "circle_files_outbox") != outboxBefore {
		t.Fatal("failed deletes must not commit receipt or outbox")
	}

	// t1+t2：一次删除成功，owner readback 确认不可读，且只提交一次 state 与 outbox。
	removed := remove(fileContractOwner, fileID, "fc-delete-1")
	if removed.Code >= http.StatusBadRequest {
		t.Fatalf("delete status=%d body=%s", removed.Code, removed.Body.String())
	}
	unreadable := h.getFile(t, fileContractOwner, fileID, "fc-delete-readback")
	unreadableBody := decodeFileResponse(t, unreadable)
	if unreadable.Code < http.StatusBadRequest ||
		unreadableBody["code"] != "CIRCLE.USER.file_not_found" {
		t.Fatalf("deleted file must become unreadable: status=%d body=%#v", unreadable.Code, unreadableBody)
	}
	if h.count(t, "circle_files_command_receipts") != receiptsBefore+1 ||
		h.count(t, "circle_files_outbox") != outboxBefore+1 {
		t.Fatal("delete must commit exactly one receipt and one outbox event")
	}
	// t3：不删除或改写 MediaAsset 事实——folder 无 asset；断言删除链未触碰
	// media 集合（本库不存在 media_assets 写入）。
	if h.count(t, "media_assets") != 0 {
		t.Fatal("delete must not write MediaAsset facts")
	}

	// t4（重放段）：同键同语义重放稳定。
	replay := remove(fileContractOwner, fileID, "fc-delete-1")
	replayBody := decodeFileResponse(t, replay)
	if replay.Code >= http.StatusBadRequest {
		t.Fatalf("delete replay must be idempotent: status=%d body=%#v", replay.Code, replayBody)
	}
	if h.count(t, "circle_files_command_receipts") != receiptsBefore+1 ||
		h.count(t, "circle_files_outbox") != outboxBefore+1 {
		t.Fatal("delete replay must not append receipts or outbox events")
	}
}
