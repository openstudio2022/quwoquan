// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-007
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-007.t1
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-007.t2
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-007.t3
// spec_ref: specs/feature-tree/circle-community/gathering-coordination/gathering-lifecycle/spec.md#gwt-007.t4
// readiness_case: list-gatherings-by-source-api
//
// ListGatheringsBySource 公开读面合同：typed page 只含精确引用冻结 source
// identity 的公开 published/cancelled/completed Gathering；cursor 重放稳定不重复；
// 合法无匹配返回 typed empty page；source 形状无效或 cursor 非法返回 canonical
// failure，不回退模糊匹配。
package gathering_test

import (
	"context"
	"fmt"
	"net/http"
	"testing"
	"time"

	"quwoquan_service/internal/platform/testinfra"
	gatheringhttp "quwoquan_service/services/circle-service/internal/circle_management/gathering/adapters/inbound/http"
	gatheringapp "quwoquan_service/services/circle-service/internal/circle_management/gathering/application"
	gatheringpersistence "quwoquan_service/services/circle-service/internal/circle_management/gathering/infrastructure/persistence"
)

const bySourceHomepageID = "homepage-by-source-a"

func TestListGatheringsBySourcePublicPageContract(t *testing.T) {
	ctx := context.Background()
	runtime, err := testinfra.StartRealMongo(ctx, "circle_gathering_by_source_api")
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
	queries := gatheringapp.NewGatheringQueryFacade(
		gatheringpersistence.NewMongoGatheringQueryReader(runtime.Database),
		time.Now,
	)
	mux := http.NewServeMux()
	gatheringhttp.NewHandler(
		lifecycle,
		gatheringapp.NewCommandFacade(store),
		hostOutcome,
		queries,
	).Register(mux)
	// publish 前置：真实 reconciler 驱动 room provision（chat projection double）。
	reconciler := gatheringapp.NewReconciler(store, store, &chatProjection{})

	now := time.Now().UTC()
	sourceRefs := func(objectID string) []any {
		return []any{map[string]any{
			"objectRef":    map[string]any{"objectTypeRef": "homepage", "objectId": objectID},
			"routeId":      "homepageDetail",
			"sourceDigest": "sha256:0f2c15b7fbcb45f4a1e79c05ff3f2eaa1d0563a3f1d5a4dbb0a83e1e63a9c001",
		}}
	}
	createAt := func(title, sourceObjectID, key string, startOffset time.Duration) string {
		t.Helper()
		body := map[string]any{
			"hostBinding": map[string]any{
				"hostSubjectKind": "persona", "hostSubjectId": "persona-source-host",
				"authorityEvidenceRef": "authority/owner", "authorityVersion": 1,
				"authorityExpiresAt": now.Add(24 * time.Hour),
			},
			"creatorParticipates": true,
			"purpose": map[string]any{
				"title": title, "summary": "公开安全的来源锚点行动",
				"topicRefs": []string{}, "requirementRefs": []string{},
				"sourceObjectRefs": sourceRefs(sourceObjectID), "costNotice": "free",
			},
			"schedule": map[string]any{
				"timezone": "Asia/Shanghai", "startAt": now.Add(startOffset),
				"endAt":             now.Add(startOffset + 2*time.Hour),
				"admissionClosesAt": now.Add(startOffset - time.Hour),
			},
			"place": map[string]any{"mode": "online", "onlineLocationRef": "room://gathering"},
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
		created := execute(t, mux, http.MethodPost, "/gatherings", body, "persona-source-host", key)
		if created.Code != http.StatusCreated {
			t.Fatalf("create %s status=%d body=%s", title, created.Code, created.Body.String())
		}
		id, _ := decode(t, created)["gatheringId"].(string)
		if id == "" {
			t.Fatalf("created gathering %s lacks id", title)
		}
		return id
	}
	publish := func(gatheringID, key string) {
		t.Helper()
		if _, reconcileErr := reconciler.ReconcileOnce(ctx, 20); reconcileErr != nil {
			t.Fatalf("reconcile gathering rooms: %v", reconcileErr)
		}
		current, found, loadErr := store.Load(ctx, gatheringID)
		if loadErr != nil || !found {
			t.Fatalf("load gathering %s: found=%v err=%v", gatheringID, found, loadErr)
		}
		published := execute(t, mux, http.MethodPost, "/gatherings/"+gatheringID+":publish",
			map[string]any{"expectedGatheringVersion": current.Version}, "persona-source-host", key)
		if published.Code != http.StatusOK {
			t.Fatalf("publish %s status=%d body=%s", gatheringID, published.Code, published.Body.String())
		}
	}

	firstID := createAt("西湖晨雾散步", bySourceHomepageID, "by-source-create-1", 3*time.Hour)
	publish(firstID, "by-source-publish-1")
	secondID := createAt("西湖黄昏骑行", bySourceHomepageID, "by-source-create-2", 5*time.Hour)
	publish(secondID, "by-source-publish-2")
	// draft：同 source 但未发布，禁止进入公开读面。
	draftID := createAt("西湖草稿计划", bySourceHomepageID, "by-source-create-3", 7*time.Hour)
	// 其他 source：published 但不得混入。
	otherID := createAt("孤山访梅", "homepage-by-source-b", "by-source-create-4", 9*time.Hour)
	publish(otherID, "by-source-publish-4")

	list := func(query string) map[string]any {
		t.Helper()
		response := execute(t, mux, http.MethodGet, "/gatherings/by-source"+query, nil, "", "")
		if response.Code != http.StatusOK {
			t.Fatalf("list by source %s status=%d body=%s", query, response.Code, response.Body.String())
		}
		return decode(t, response)
	}
	itemIDs := func(page map[string]any) []string {
		items, _ := page["items"].([]any)
		ids := make([]string, 0, len(items))
		for _, raw := range items {
			item, _ := raw.(map[string]any)
			id, _ := item["gatheringId"].(string)
			if status, _ := item["lifecycleStatus"].(string); status != "published" &&
				status != "cancelled" && status != "completed" {
				t.Fatalf("public source page leaked non-public lifecycle %q: %#v", status, item)
			}
			ids = append(ids, id)
		}
		return ids
	}

	// t1：typed page 只含精确引用该 source、公开可见生命周期的 Gathering。
	full := list("?sourceObjectTypeRef=homepage&sourceObjectId=" + bySourceHomepageID + "&limit=20")
	fullIDs := itemIDs(full)
	if len(fullIDs) != 2 {
		t.Fatalf("source page must hold exactly the two published gatherings: %v", fullIDs)
	}
	for _, id := range fullIDs {
		if id == draftID || id == otherID {
			t.Fatalf("source page leaked draft or foreign-source gathering: %v", fullIDs)
		}
	}

	// t2：cursor 分页稳定、不重复、不漏项；同一 cursor 重放返回同一页。
	first := list("?sourceObjectTypeRef=homepage&sourceObjectId=" + bySourceHomepageID + "&limit=1")
	firstIDs := itemIDs(first)
	cursor, _ := first["nextCursor"].(string)
	if len(firstIDs) != 1 || cursor == "" || first["hasMore"] != true {
		t.Fatalf("first page must expose one item and a continuation cursor: %#v", first)
	}
	replayed := list("?sourceObjectTypeRef=homepage&sourceObjectId=" + bySourceHomepageID + "&limit=1")
	if replayedIDs := itemIDs(replayed); len(replayedIDs) != 1 || replayedIDs[0] != firstIDs[0] {
		t.Fatalf("cursor replay must be stable: %v vs %v", replayedIDs, firstIDs)
	}
	second := list("?sourceObjectTypeRef=homepage&sourceObjectId=" + bySourceHomepageID +
		"&limit=1&cursor=" + cursor)
	secondIDs := itemIDs(second)
	if len(secondIDs) != 1 || secondIDs[0] == firstIDs[0] {
		t.Fatalf("second page must continue without repetition: %v then %v", firstIDs, secondIDs)
	}
	pageUnion := map[string]bool{firstIDs[0]: true, secondIDs[0]: true}
	for _, id := range fullIDs {
		if !pageUnion[id] {
			t.Fatalf("cursor pagination dropped gathering %s", id)
		}
	}

	// t3：形状合法但无匹配返回 typed empty page，不合成失败也不借用其他来源。
	empty := list("?sourceObjectTypeRef=homepage&sourceObjectId=homepage-by-source-none&limit=20")
	if items, _ := empty["items"].([]any); len(items) != 0 || empty["hasMore"] != false {
		t.Fatalf("unmatched source identity must return a typed empty page: %#v", empty)
	}

	// t4：source identity 形状无效或 cursor 非法返回 canonical failure，不回退模糊匹配。
	invalidSource := execute(t, mux, http.MethodGet,
		"/gatherings/by-source?sourceObjectTypeRef=homepage", nil, "", "")
	invalidSourceBody := decode(t, invalidSource)
	if invalidSource.Code < http.StatusBadRequest ||
		invalidSourceBody["code"] != "CIRCLE.USER.invalid_argument" {
		t.Fatalf(
			"invalid source shape must fail typed: status=%d body=%#v",
			invalidSource.Code, invalidSourceBody,
		)
	}
	invalidCursor := execute(t, mux, http.MethodGet,
		fmt.Sprintf(
			"/gatherings/by-source?sourceObjectTypeRef=homepage&sourceObjectId=%s&cursor=%s",
			bySourceHomepageID, "not-a-cursor",
		), nil, "", "")
	invalidCursorBody := decode(t, invalidCursor)
	if invalidCursor.Code < http.StatusBadRequest || invalidCursorBody["code"] == nil {
		t.Fatalf(
			"invalid cursor must fail typed instead of fuzzy matching: status=%d body=%#v",
			invalidCursor.Code, invalidCursorBody,
		)
	}
}
