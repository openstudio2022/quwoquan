package api_integration

import (
	"context"
	"encoding/json"
	"net/http"
	"testing"
	"time"

	"go.mongodb.org/mongo-driver/v2/bson"
)

// TestSubjectFollow_FullChain 验证 SubjectFollow 聚合的商用契约全链：
// HTTP 命令 → PG state/receipt/outbox 原子提交 → relay 投递 Redis Stream 并
// upsert following_subjects 投影 → ListFollowingSubjects 关注频道回读 →
// mark-visited 水位推进。
func TestSubjectFollow_FullChain(t *testing.T) {
	requireMongoBackedRuntime(t)
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "sf_user_1", "sfuser1")
	createTestPersonaFull(t, "", "sf_user_1", "ps_sf_1", "关注者", "default", true)

	headers := authHeadersForPersona("sf_user_1", "ps_sf_1")

	rec := doRequest(
		t,
		http.MethodPost,
		"/relationships/subjects/homepage/homepage_emeishan/follow",
		`{"source":"homepage_detail"}`,
		headers,
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("follow subject status=%d body=%s", rec.Code, rec.Body.String())
	}
	var result struct {
		PersonaID        string `json:"personaId"`
		SubjectType      string `json:"subjectType"`
		SubjectID        string `json:"subjectId"`
		State            string `json:"state"`
		IdempotentReplay bool   `json:"idempotentReplay"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &result); err != nil {
		t.Fatalf("decode follow result: %v", err)
	}
	if result.PersonaID != "ps_sf_1" || result.SubjectType != "homepage" ||
		result.SubjectID != "homepage_emeishan" || result.State != "following" ||
		result.IdempotentReplay {
		t.Fatalf("unexpected follow result: %+v", result)
	}

	ctx := context.Background()
	var state string
	var version int64
	if err := pgPool.QueryRow(ctx, `
		SELECT state, version FROM subject_follows
		WHERE persona_id = $1 AND subject_type = 'homepage' AND subject_id = $2`,
		"ps_sf_1", "homepage_emeishan").Scan(&state, &version); err != nil {
		t.Fatalf("query subject follow row: %v", err)
	}
	if state != "following" || version != 1 {
		t.Fatalf("unexpected aggregate state=%s version=%d", state, version)
	}
	var outboxCount int
	if err := pgPool.QueryRow(ctx,
		`SELECT COUNT(*) FROM subject_follow_outbox`).Scan(&outboxCount); err != nil {
		t.Fatalf("count outbox: %v", err)
	}
	if outboxCount != 1 {
		t.Fatalf("subject follow outbox count=%d, want 1", outboxCount)
	}

	// relay 投递后投影收敛（轮询最多 5s）。
	waitForFollowingSubjectRow(t, "ps_sf_1", "homepage", "homepage_emeishan")

	listRec := doRequest(t, http.MethodGet, "/user/following-subjects", "", headers)
	if listRec.Code != http.StatusOK {
		t.Fatalf("list following subjects status=%d body=%s", listRec.Code, listRec.Body.String())
	}
	var page struct {
		Items []struct {
			SubjectID     string `json:"subjectId"`
			SubjectType   string `json:"subjectType"`
			TargetRouteID string `json:"targetRouteId"`
			DisplayName   string `json:"displayName"`
		} `json:"items"`
	}
	if err := json.Unmarshal(listRec.Body.Bytes(), &page); err != nil {
		t.Fatalf("decode following subjects: %v", err)
	}
	if len(page.Items) != 1 || page.Items[0].SubjectID != "homepage_emeishan" ||
		page.Items[0].SubjectType != "homepage" ||
		page.Items[0].TargetRouteID != "homepage_detail" {
		t.Fatalf("unexpected following subjects page: %+v", page)
	}

	// mark-visited 水位推进（清关注频道红点）。
	visitRec := doRequest(
		t,
		http.MethodPost,
		"/user/followed-subjects/homepage/homepage_emeishan:mark-visited",
		`{"subjectId":"homepage_emeishan","subjectType":"homepage","clientRequestId":"visit-1"}`,
		headers,
	)
	if visitRec.Code != http.StatusOK {
		t.Fatalf("mark visited status=%d body=%s", visitRec.Code, visitRec.Body.String())
	}
	var visit struct {
		SubjectID        string `json:"subjectId"`
		LastVisitedAt    string `json:"lastVisitedAt"`
		HasUnreadChanges bool   `json:"hasUnreadChanges"`
	}
	if err := json.Unmarshal(visitRec.Body.Bytes(), &visit); err != nil {
		t.Fatalf("decode visit result: %v", err)
	}
	if visit.SubjectID != "homepage_emeishan" || visit.LastVisitedAt == "" || visit.HasUnreadChanges {
		t.Fatalf("unexpected visit result: %+v", visit)
	}
	// 相同 clientRequestId 重放返回同一 receipt。
	replayRec := doRequest(
		t,
		http.MethodPost,
		"/user/followed-subjects/homepage/homepage_emeishan:mark-visited",
		`{"subjectId":"homepage_emeishan","subjectType":"homepage","clientRequestId":"visit-1"}`,
		headers,
	)
	var replayVisit struct {
		LastVisitedAt string `json:"lastVisitedAt"`
	}
	if err := json.Unmarshal(replayRec.Body.Bytes(), &replayVisit); err != nil {
		t.Fatalf("decode visit replay: %v", err)
	}
	if replayVisit.LastVisitedAt != visit.LastVisitedAt {
		t.Fatalf("visit replay watermark drifted: first=%s replay=%s",
			visit.LastVisitedAt, replayVisit.LastVisitedAt)
	}
}

// TestSubjectFollow_LocationReadAndVisitClosure 固定 FollowSubjectKind 的 location
// 分支：写聚合、following_subjects 读模型与访问水位必须使用同一值域，不能出现
// “可关注但不可读/不可清红点”的半条链路。
// spec_ref: specs/feature-tree/user-identity-profile-relationship/persona-follow-graph/spec.md#sit-001
func TestSubjectFollow_LocationReadAndVisitClosure(t *testing.T) {
	requireMongoBackedRuntime(t)
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "sf_location_user", "location-user")
	createTestPersonaFull(
		t,
		"",
		"sf_location_user",
		"ps_sf_location",
		"地点关注者",
		"default",
		true,
	)

	headers := authHeadersForPersona("sf_location_user", "ps_sf_location")
	follow := doRequest(
		t,
		http.MethodPost,
		"/relationships/subjects/location/location_shenzhen/follow",
		`{"source":"location_detail"}`,
		headers,
	)
	if follow.Code != http.StatusOK {
		t.Fatalf("follow location status=%d body=%s", follow.Code, follow.Body.String())
	}
	waitForFollowingSubjectRow(
		t,
		"ps_sf_location",
		"location",
		"location_shenzhen",
	)

	list := doRequest(
		t,
		http.MethodGet,
		"/user/following-subjects?subjectType=location",
		"",
		headers,
	)
	if list.Code != http.StatusOK {
		t.Fatalf("list location subjects status=%d body=%s", list.Code, list.Body.String())
	}
	var page struct {
		Items []struct {
			SubjectID   string `json:"subjectId"`
			SubjectType string `json:"subjectType"`
		} `json:"items"`
	}
	if err := json.Unmarshal(list.Body.Bytes(), &page); err != nil {
		t.Fatalf("decode location subjects: %v", err)
	}
	if len(page.Items) != 1 || page.Items[0].SubjectID != "location_shenzhen" ||
		page.Items[0].SubjectType != "location" {
		t.Fatalf("unexpected location subjects: %+v", page.Items)
	}

	visit := doRequest(
		t,
		http.MethodPost,
		"/user/followed-subjects/location/location_shenzhen:mark-visited",
		`{"subjectId":"location_shenzhen","subjectType":"location","clientRequestId":"visit-location-1"}`,
		headers,
	)
	if visit.Code != http.StatusOK {
		t.Fatalf("mark location visited status=%d body=%s", visit.Code, visit.Body.String())
	}
	var result struct {
		SubjectID        string `json:"subjectId"`
		SubjectType      string `json:"subjectType"`
		HasUnreadChanges bool   `json:"hasUnreadChanges"`
	}
	if err := json.Unmarshal(visit.Body.Bytes(), &result); err != nil {
		t.Fatalf("decode location visit: %v", err)
	}
	if result.SubjectID != "location_shenzhen" || result.SubjectType != "location" ||
		result.HasUnreadChanges {
		t.Fatalf("unexpected location visit result: %+v", result)
	}

	// 新请求回读投影，证明 mark-visited 不只是命令响应自称成功：持久水位
	// 必须已经清除 following_subjects 的红点并可跨请求观察。
	readback := doRequest(
		t,
		http.MethodGet,
		"/user/following-subjects?subjectType=location",
		"",
		headers,
	)
	if readback.Code != http.StatusOK {
		t.Fatalf("read back visited location status=%d body=%s", readback.Code, readback.Body.String())
	}
	var visitedPage struct {
		Items []struct {
			SubjectID         string `json:"subjectId"`
			SubjectType       string `json:"subjectType"`
			LastVisitedAt     string `json:"lastVisitedAt"`
			UnreadChangeCount int64  `json:"unreadChangeCount"`
			HasUnreadChanges  bool   `json:"hasUnreadChanges"`
		} `json:"items"`
	}
	if err := json.Unmarshal(readback.Body.Bytes(), &visitedPage); err != nil {
		t.Fatalf("decode visited location readback: %v", err)
	}
	if len(visitedPage.Items) != 1 ||
		visitedPage.Items[0].SubjectID != "location_shenzhen" ||
		visitedPage.Items[0].SubjectType != "location" ||
		visitedPage.Items[0].LastVisitedAt == "" ||
		visitedPage.Items[0].UnreadChangeCount != 0 ||
		visitedPage.Items[0].HasUnreadChanges {
		t.Fatalf("visited location projection did not converge: %+v", visitedPage.Items)
	}
}

// TestSubjectFollow_IdempotentReplayAndUnfollow 验证 set/unset 命名迁移语义：
// 重复 follow 幂等重放不推进版本、不追加事件；unfollow 后投影行删除。
func TestSubjectFollow_IdempotentReplayAndUnfollow(t *testing.T) {
	requireMongoBackedRuntime(t)
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "sf_user_2", "sfuser2")
	createTestPersonaFull(t, "", "sf_user_2", "ps_sf_2", "重复关注者", "default", true)

	headers := authHeadersForPersona("sf_user_2", "ps_sf_2")
	path := "/relationships/subjects/circle/circle_sichuan/follow"

	first := doRequest(t, http.MethodPost, path, "", headers)
	if first.Code != http.StatusOK {
		t.Fatalf("first follow status=%d body=%s", first.Code, first.Body.String())
	}
	second := doRequest(t, http.MethodPost, path, "", headers)
	if second.Code != http.StatusOK {
		t.Fatalf("second follow status=%d body=%s", second.Code, second.Body.String())
	}
	var replay struct {
		State            string `json:"state"`
		IdempotentReplay bool   `json:"idempotentReplay"`
	}
	if err := json.Unmarshal(second.Body.Bytes(), &replay); err != nil {
		t.Fatalf("decode replay: %v", err)
	}
	if !replay.IdempotentReplay || replay.State != "following" {
		t.Fatalf("second follow must be idempotent replay: %+v", replay)
	}

	ctx := context.Background()
	var version int64
	if err := pgPool.QueryRow(ctx, `
		SELECT version FROM subject_follows
		WHERE persona_id = 'ps_sf_2' AND subject_type = 'circle' AND subject_id = 'circle_sichuan'`,
	).Scan(&version); err != nil {
		t.Fatalf("query version: %v", err)
	}
	if version != 1 {
		t.Fatalf("idempotent replay must not advance version, got %d", version)
	}
	var outboxCount int
	if err := pgPool.QueryRow(ctx,
		`SELECT COUNT(*) FROM subject_follow_outbox WHERE aggregate_version > 1`).Scan(&outboxCount); err != nil {
		t.Fatalf("count outbox: %v", err)
	}
	if outboxCount != 0 {
		t.Fatalf("idempotent replay must not append outbox, got %d extra events", outboxCount)
	}

	waitForFollowingSubjectRow(t, "ps_sf_2", "circle", "circle_sichuan")

	unfollow := doRequest(t, http.MethodDelete, path, "", headers)
	if unfollow.Code != http.StatusOK {
		t.Fatalf("unfollow status=%d body=%s", unfollow.Code, unfollow.Body.String())
	}
	deadline := time.Now().Add(5 * time.Second)
	for {
		count, err := mongoDB.Collection("following_subjects").CountDocuments(
			context.Background(),
			bson.M{"viewerPersonaId": "ps_sf_2", "subjectType": "circle", "subjectId": "circle_sichuan"},
		)
		if err != nil {
			t.Fatalf("count projection rows: %v", err)
		}
		if count == 0 {
			break
		}
		if time.Now().After(deadline) {
			t.Fatalf("unfollow projection row not removed, count=%d", count)
		}
		time.Sleep(50 * time.Millisecond)
	}
}

// TestSubjectFollow_RejectsPersonaSubjectType 验证 persona 主体被拒绝：
// persona 间关系只能走 PersonaRelationship。
func TestSubjectFollow_RejectsPersonaSubjectType(t *testing.T) {
	requireMongoBackedRuntime(t)
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "sf_user_3", "sfuser3")
	createTestPersonaFull(t, "", "sf_user_3", "ps_sf_3", "越界关注者", "default", true)

	rec := doRequest(
		t,
		http.MethodPost,
		"/relationships/subjects/persona/ps_other/follow",
		"",
		authHeadersForPersona("sf_user_3", "ps_sf_3"),
	)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("persona subject type status=%d body=%s", rec.Code, rec.Body.String())
	}
	var failure struct {
		Code string `json:"code"`
	}
	if err := json.Unmarshal(rec.Body.Bytes(), &failure); err != nil {
		t.Fatalf("decode failure: %v", err)
	}
	if failure.Code != "USER.SUBJECT_FOLLOW.invalid_subject_type" {
		t.Fatalf("unexpected failure code: %+v", failure)
	}
	var count int
	if err := pgPool.QueryRow(context.Background(),
		`SELECT COUNT(*) FROM subject_follows WHERE persona_id = 'ps_sf_3'`).Scan(&count); err != nil {
		t.Fatalf("count rows: %v", err)
	}
	if count != 0 {
		t.Fatalf("rejected command must not create rows, got %d", count)
	}
}

// TestPersonaFollow_ProjectsIntoFollowingSubjects 验证 PersonaFollowStateChanged
// 事件驱动 following_subjects 投影的 persona 主体行（首页关注频道跨域聚合）。
func TestPersonaFollow_ProjectsIntoFollowingSubjects(t *testing.T) {
	requireMongoBackedRuntime(t)
	t.Cleanup(func() { cleanAll(t) })
	createTestProfile(t, "sf_user_4", "sfuser4")
	createTestProfile(t, "sf_user_5", "sfuser5")
	createTestPersonaFull(t, "", "sf_user_4", "ps_sf_4", "关注发起者", "default", true)
	createTestPersonaFull(t, "", "sf_user_5", "ps_sf_5", "被关注者", "default", true)

	rec := doRequest(
		t,
		http.MethodPost,
		"/user/personas/ps_sf_5/follow",
		"",
		authHeadersForPersona("sf_user_4", "ps_sf_4"),
	)
	if rec.Code != http.StatusOK {
		t.Fatalf("persona follow status=%d body=%s", rec.Code, rec.Body.String())
	}
	waitForFollowingSubjectRow(t, "ps_sf_4", "persona", "ps_sf_5")

	listRec := doRequest(
		t,
		http.MethodGet,
		"/user/following-subjects?subjectType=persona",
		"",
		authHeadersForPersona("sf_user_4", "ps_sf_4"),
	)
	var page struct {
		Items []struct {
			SubjectID     string `json:"subjectId"`
			DisplayName   string `json:"displayName"`
			TargetRouteID string `json:"targetRouteId"`
		} `json:"items"`
	}
	if err := json.Unmarshal(listRec.Body.Bytes(), &page); err != nil {
		t.Fatalf("decode page: %v", err)
	}
	if len(page.Items) != 1 || page.Items[0].SubjectID != "ps_sf_5" {
		t.Fatalf("unexpected user rows: %+v", page)
	}
	if page.Items[0].DisplayName != "被关注者" {
		t.Fatalf("user row must be enriched with persona display name: %+v", page.Items[0])
	}
	if page.Items[0].TargetRouteID != "user_profile" {
		t.Fatalf("persona row must retain the canonical profile route: %+v", page.Items[0])
	}
}

func waitForFollowingSubjectRow(t *testing.T, personaID, subjectType, subjectID string) {
	t.Helper()
	deadline := time.Now().Add(5 * time.Second)
	for {
		count, err := mongoDB.Collection("following_subjects").CountDocuments(
			context.Background(),
			bson.M{
				"viewerPersonaId": personaID,
				"subjectType":     subjectType,
				"subjectId":       subjectID,
			},
		)
		if err != nil {
			t.Fatalf("count following_subjects: %v", err)
		}
		if count == 1 {
			return
		}
		if time.Now().After(deadline) {
			t.Fatalf("following_subjects row not converged: %s/%s/%s", personaID, subjectType, subjectID)
		}
		time.Sleep(50 * time.Millisecond)
	}
}
