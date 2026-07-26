package local_contract

import (
	"context"
	"encoding/json"
	"strings"
	"testing"

	"quwoquan_service/runtime/operation"
	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application/homepage_orchestration"
	"quwoquan_service/services/entity-service/internal/entity_homepage/homepage/infrastructure/testsupport"
)

func importedSightInput(title string) application.ImportedHomepageInput {
	return application.ImportedHomepageInput{
		EntityRef:    "地点/景区/" + title,
		Title:        title,
		HomepageType: "sight",
		City:         "阿坝",
		IntroductionMarkdown: "---\ncoverImage: asset://" + title + "_cover_树正寨_42_a1b2c3d4\n---\n\n# " + title +
			"\n\n## 概况\n\n真实底稿概况正文。\n\n## 相关图片\n\n:::gallery\nasset://" + title + "_detail_老虎海_42_b2c3d4e5\n:::\n",
		IntroductionAssets: []application.HomepageIntroductionAsset{
			{AssetID: title + "_cover_树正寨_42_a1b2c3d4", URL: "https://media.local/media/objects/sha256/aa/bb/c1.jpg", Caption: "树正寨", Role: "cover"},
			{AssetID: title + "_detail_老虎海_42_b2c3d4e5", URL: "https://media.local/media/objects/sha256/cc/dd/e2.jpg", Caption: "老虎海", Role: "related"},
		},
		CategoryTags: []string{
			"Entity/地点/景区/5A景区",
			"Topic/地理/行政区/中国/四川省/阿坝藏族羌族自治州/九寨沟县",
		},
		PrimarySource: &application.HomepageSource{
			SourceKind: "wikipedia", SourceURL: "https://zh.wikipedia.org/wiki/" + title,
			Title: title, FetchedAt: "2026-07-11T00:00:00Z",
			SnapshotHash:   "sha256:" + strings.Repeat("a", 64),
			PolicyRevision: "encyclopedia-primary", SourceUseMode: "licensed_adaptation",
		},
		SourceURLs:   []string{"https://zh.wikipedia.org/wiki/" + title},
		SourceTaskID: "旅行/地域/中国/景区/全国景区主页试点0706a",
	}
}

func reconcileImportedHomepages(
	t *testing.T,
	svc *application.HomepageService,
	inputs []application.ImportedHomepageInput,
	mode application.HomepageImportMode,
	releaseID string,
) (application.HomepageImportReport, error) {
	t.Helper()
	return svc.ReconcileImportedHomepages(context.Background(), application.HomepageImportRequest{
		Mode:            mode,
		SourceOwner:     "qwq_data",
		SourceReleaseID: releaseID,
		RunID:           "run-" + releaseID,
		Inputs:          inputs,
	})
}

func newEmptyHomepageService() *application.HomepageService {
	service, _ := testsupport.NewEmptyHomepageService()
	return service
}

func TestReconcileImportedHomepagesCreatesPublishedHomepage(t *testing.T) {
	svc := newEmptyHomepageService()
	report, err := reconcileImportedHomepages(t, svc, []application.ImportedHomepageInput{importedSightInput("九寨沟")}, application.HomepageImportModeUpsert, "release-001")
	if err != nil {
		t.Fatalf("upsert failed: %v", err)
	}
	if len(report.Created) != 1 || len(report.Updated) != 0 {
		t.Fatalf("expected 1 created, got %+v", report)
	}
	// WP4 覆盖账本核对面：导入报告必须携带 entityRef→homepageId 映射产物。
	if got := report.EntityRefToHomepageID["地点/景区/九寨沟"]; got != report.Created[0] {
		t.Fatalf("entityRefToHomepageId must map 地点/景区/九寨沟 to created id, got %+v", report.EntityRefToHomepageID)
	}
	homepage, err := svc.GetHomepage(context.Background(), report.Created[0])
	if err != nil {
		t.Fatalf("get homepage: %v", err)
	}
	if homepage.Status != "published" || homepage.SourceType != "official_seed" {
		t.Fatalf("imported homepage must be published official_seed, got %s/%s", homepage.Status, homepage.SourceType)
	}
	if homepage.SourceOwner != "qwq_data" || homepage.SourceEntityRef != "地点/景区/九寨沟" || homepage.SourceReleaseID != "release-001" {
		t.Fatalf("import provenance must be release-bound, got %+v", homepage)
	}
	if !strings.Contains(homepage.IntroductionMarkdown, "## 概况") {
		t.Fatalf("introductionMarkdown missing body: %q", homepage.IntroductionMarkdown)
	}
	if len(homepage.IntroductionAssets) != 2 {
		t.Fatalf("expected 2 introduction assets, got %d", len(homepage.IntroductionAssets))
	}
	if homepage.CoverURL == "" {
		t.Fatalf("cover url must be derived from introduction assets")
	}
	// WP3 统一打标：_entity.json.tagRefs → categoryTags 投影（与 content-service import 同源）。
	if len(homepage.CategoryTags) != 2 ||
		homepage.CategoryTags[0] != "Entity/地点/景区/5A景区" ||
		homepage.CategoryTags[1] != "Topic/地理/行政区/中国/四川省/阿坝藏族羌族自治州/九寨沟县" {
		t.Fatalf("categoryTags must carry imported tagRefs, got %+v", homepage.CategoryTags)
	}
	// introduction API 端到端可读（page.md 三段结构投影生效，非 generic fallback）。
	intro, err := svc.GetHomepageIntroduction(context.Background(), homepage.ID)
	if err != nil {
		t.Fatalf("get introduction: %v", err)
	}
	foundOverview := false
	foundRelated := false
	for _, section := range intro.Sections {
		if strings.Contains(section.BodyMarkdown, "真实底稿概况正文") {
			foundOverview = true
		}
		if section.Kind == "relatedImages" && len(section.Assets) > 0 {
			foundRelated = true
		}
	}
	if !foundOverview || !foundRelated {
		t.Fatalf("introduction must project page.md body + related images, got %+v", intro.Sections)
	}
	if intro.PrimarySource == nil || intro.PrimarySource.SourceKind != "wikipedia" ||
		len(intro.SourceURLs) != 1 {
		t.Fatalf("introduction must expose public source without internal refs: %+v", intro)
	}
	wire, err := json.Marshal(intro)
	if err != nil {
		t.Fatalf("marshal introduction: %v", err)
	}
	if strings.Contains(string(wire), "sourceRefs") || strings.Contains(string(wire), "primaryEvidenceRef") {
		t.Fatalf("introduction wire must not expose internal refs: %s", wire)
	}
}

func TestReconcileImportedHomepagesIsIdempotentBySourceEntityRef(t *testing.T) {
	svc := newEmptyHomepageService()
	first, err := reconcileImportedHomepages(t, svc, []application.ImportedHomepageInput{importedSightInput("黄龙")}, application.HomepageImportModeUpsert, "release-001")
	if err != nil {
		t.Fatalf("first upsert: %v", err)
	}
	second, err := reconcileImportedHomepages(t, svc, []application.ImportedHomepageInput{importedSightInput("黄龙")}, application.HomepageImportModeUpsert, "release-002")
	if err != nil {
		t.Fatalf("second upsert: %v", err)
	}
	if len(first.Created) != 1 || len(second.Created) != 0 || len(second.Updated) != 1 {
		t.Fatalf("re-import must update, not duplicate: first=%+v second=%+v", first, second)
	}
	if second.Updated[0] != first.Created[0] {
		t.Fatalf("re-import must hit the same homepage id: %s vs %s", second.Updated[0], first.Created[0])
	}
	// updated 分支同样要产出 entityRef→homepageId 映射（幂等重放不丢核对面）。
	if got := second.EntityRefToHomepageID["地点/景区/黄龙"]; got != first.Created[0] {
		t.Fatalf("re-import entityRefToHomepageId must keep stable id, got %+v", second.EntityRefToHomepageID)
	}
}

func TestReconcileImportedHomepagesPreservesClaimedEdits(t *testing.T) {
	svc := newEmptyHomepageService()
	ctx := operation.WithContext(context.Background(), operation.Context{
		OperationID:    "entity.homepage.UpdateClaimedHomepageBasics",
		RequestID:      "req-import-preserve",
		TraceID:        "trace-import-preserve",
		IdempotencyKey: "import-preserve",
		Actor: operation.ActorContext{
			AccountID: "fixture-reviewer-account",
			PersonaID: "fixture_operator",
		},
	})
	report, err := reconcileImportedHomepages(t, svc, []application.ImportedHomepageInput{importedSightInput("武侯祠")}, application.HomepageImportModeUpsert, "release-001")
	if err != nil {
		t.Fatalf("seed upsert: %v", err)
	}
	id := report.Created[0]
	claim, err := svc.CreateHomepageClaimRequest(ctx, id, application.ClaimRequestInput{
		RequesterPersonaID: "fixture_operator",
		ClaimTier:          "business",
		ContactPhone:       "13800000000",
	})
	if err != nil {
		t.Fatalf("claim request: %v", err)
	}
	if err := svc.ApplyClaimRequestedProjection(
		ctx,
		"test-import-claim-requested",
		id,
	); err != nil {
		t.Fatalf("project pending claim: %v", err)
	}
	if _, err := svc.ReviewHomepageClaimRequest(
		ctx,
		id,
		claim.ClaimRequestID,
		application.ClaimReviewInput{Status: "approved"},
	); err != nil {
		t.Fatalf("approve claim: %v", err)
	}
	if err := svc.ApplyClaimReviewedProjection(
		ctx,
		"test-import-claim-reviewed",
		id,
		"fixture_operator",
		true,
	); err != nil {
		t.Fatalf("project approved claim: %v", err)
	}
	if _, err := svc.UpdateClaimedHomepageBasics(ctx, id, application.HomepageBasicInput{
		CoverURL: "https://claimed.example/cover.jpg",
		City:     "成都",
	}); err != nil {
		t.Fatalf("update claimed basics: %v", err)
	}

	updated := importedSightInput("武侯祠")
	updated.IntroductionMarkdown = "# 武侯祠\n\n## 概况\n\n新一批更优底稿。\n"
	if _, err := reconcileImportedHomepages(t, svc, []application.ImportedHomepageInput{updated}, application.HomepageImportModeUpsert, "release-002"); err != nil {
		t.Fatalf("re-import: %v", err)
	}
	homepage, err := svc.GetHomepage(ctx, id)
	if err != nil {
		t.Fatalf("get homepage: %v", err)
	}
	if homepage.CoverURL != "https://claimed.example/cover.jpg" || homepage.City != "成都" {
		t.Fatalf("import must not overwrite existing edits: cover=%s city=%s", homepage.CoverURL, homepage.City)
	}
	if !strings.Contains(homepage.IntroductionMarkdown, "新一批更优底稿") {
		t.Fatalf("introduction must follow latest publish, got %q", homepage.IntroductionMarkdown)
	}
}

func TestReconcileImportedHomepagesRejectsInvalidType(t *testing.T) {
	svc := newEmptyHomepageService()
	bad := importedSightInput("九寨沟")
	bad.HomepageType = "galaxy"
	report, err := reconcileImportedHomepages(t, svc, []application.ImportedHomepageInput{bad}, application.HomepageImportModeUpsert, "release-001")
	if err == nil {
		t.Fatalf("invalid homepageType must fail closed, got %+v", report)
	}
	if len(report.Created) != 0 || len(report.Skipped) != 0 {
		t.Fatalf("invalid import must not mutate or silently skip, got %+v", report)
	}
}

func TestReconcileImportedHomepagesAcceptsPilotScopePlaceTypes(t *testing.T) {
	// 地点类主页类型闭集与 metadata HomepageType 枚举 / 数据工程试点 scope 对齐（WP3-4）。
	svc := newEmptyHomepageService()
	pilotTypes := []string{
		"museum", "heritage_site", "ancient_town", "religious_site",
		"check_in_spot", "natural_landscape", "park", "hot_spring", "theme_park",
	}
	inputs := make([]application.ImportedHomepageInput, 0, len(pilotTypes))
	for i, homepageType := range pilotTypes {
		input := importedSightInput("试点类型实体" + string(rune('A'+i)))
		input.HomepageType = homepageType
		inputs = append(inputs, input)
	}
	report, err := reconcileImportedHomepages(t, svc, inputs, application.HomepageImportModeUpsert, "release-001")
	if err != nil {
		t.Fatalf("upsert: %v", err)
	}
	if len(report.Created) != len(pilotTypes) || len(report.Skipped) != 0 {
		t.Fatalf("all pilot-scope place types must be importable, got %+v", report)
	}
}

func TestReconcileImportedHomepagesKeepsExistingTagsWhenImportHasNone(t *testing.T) {
	// 数据工程无打标时不清空既有 categoryTags（保护存量/运营侧标签）。
	svc := newEmptyHomepageService()
	ctx := context.Background()
	report, err := reconcileImportedHomepages(t, svc, []application.ImportedHomepageInput{importedSightInput("青城山")}, application.HomepageImportModeUpsert, "release-001")
	if err != nil {
		t.Fatalf("seed upsert: %v", err)
	}
	id := report.Created[0]
	bare := importedSightInput("青城山")
	bare.CategoryTags = nil
	if _, err := reconcileImportedHomepages(t, svc, []application.ImportedHomepageInput{bare}, application.HomepageImportModeUpsert, "release-002"); err != nil {
		t.Fatalf("re-import: %v", err)
	}
	homepage, err := svc.GetHomepage(ctx, id)
	if err != nil {
		t.Fatalf("get homepage: %v", err)
	}
	if len(homepage.CategoryTags) != 2 {
		t.Fatalf("re-import without tags must keep existing categoryTags, got %+v", homepage.CategoryTags)
	}
}

func TestSyncImportedHomepagesOfflinesOnlyStaleDataOwnedHomepages(t *testing.T) {
	svc := newEmptyHomepageService()
	first, err := reconcileImportedHomepages(
		t,
		svc,
		[]application.ImportedHomepageInput{importedSightInput("普陀山"), importedSightInput("东钱湖")},
		application.HomepageImportModeUpsert,
		"release-canary-001",
	)
	if err != nil {
		t.Fatalf("initial import: %v", err)
	}
	manual, err := svc.IntakeHomepageCandidate(context.Background(), application.HomepageInput{
		Title:        "人工主页",
		HomepageType: "sight",
	}, "official_seed")
	if err != nil {
		t.Fatalf("create manual homepage: %v", err)
	}
	if _, err := svc.PublishHomepageCandidate(context.Background(), manual.ID); err != nil {
		t.Fatalf("publish manual homepage: %v", err)
	}

	report, err := reconcileImportedHomepages(
		t,
		svc,
		[]application.ImportedHomepageInput{importedSightInput("普陀山")},
		application.HomepageImportModeSync,
		"release-baseline-001",
	)
	if err != nil {
		t.Fatalf("sync import: %v", err)
	}
	if len(report.Offlined) != 1 || report.Offlined[0] != first.EntityRefToHomepageID["地点/景区/东钱湖"] {
		t.Fatalf("sync must offline only stale data-owned homepage, got %+v", report)
	}
	offlined, err := svc.GetHomepage(context.Background(), first.EntityRefToHomepageID["地点/景区/东钱湖"])
	if err == nil || offlined != nil {
		t.Fatalf("offlined homepage must be unavailable, got homepage=%+v err=%v", offlined, err)
	}
	stillPublished, err := svc.GetHomepage(context.Background(), manual.ID)
	if err != nil || stillPublished.Status != "published" {
		t.Fatalf("sync must not alter independent homepage, got %+v err=%v", stillPublished, err)
	}
}

func TestSyncImportedHomepagesRejectsInvalidInputBeforeMutation(t *testing.T) {
	svc := newEmptyHomepageService()
	valid := importedSightInput("海螺沟")
	if _, err := reconcileImportedHomepages(t, svc, []application.ImportedHomepageInput{valid}, application.HomepageImportModeUpsert, "release-001"); err != nil {
		t.Fatalf("initial import: %v", err)
	}
	invalid := importedSightInput("坏数据")
	invalid.HomepageType = "unsupported"
	if _, err := reconcileImportedHomepages(t, svc, []application.ImportedHomepageInput{invalid}, application.HomepageImportModeSync, "release-002"); err == nil {
		t.Fatal("sync must reject invalid desired state before mutation")
	}
	homepage, err := svc.GetHomepage(context.Background(), "海螺沟")
	if err != nil || homepage.Status != "published" {
		t.Fatalf("failed sync must not offline existing data homepage, got %+v err=%v", homepage, err)
	}
}
