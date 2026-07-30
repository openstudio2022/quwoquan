package local_contract

import (
	"context"
	"strings"
	"testing"

	application "quwoquan_service/services/entity-service/internal/entity_homepage/homepage/application/homepage_orchestration"
)

func importedSightInputAt(title string, latitude, longitude float64) application.ImportedHomepageInput {
	input := importedSightInput(title)
	input.Location = &application.GeoPoint{Latitude: latitude, Longitude: longitude}
	return input
}

// 发布线坐标必须落到 Homepage.location：这是搜索投影 doc.Geo 与「附近」召回的供给。
func TestReconcileImportedHomepagesPersistsLocation(t *testing.T) {
	svc := newEmptyHomepageService()
	report, err := reconcileImportedHomepages(
		t, svc,
		[]application.ImportedHomepageInput{importedSightInputAt("九寨沟", 33.2601, 103.9182)},
		application.HomepageImportModeUpsert, "release-geo-001",
	)
	if err != nil {
		t.Fatalf("upsert failed: %v", err)
	}
	homepage, err := svc.GetHomepage(context.Background(), report.Created[0])
	if err != nil {
		t.Fatalf("get homepage: %v", err)
	}
	if homepage.Location == nil {
		t.Fatalf("imported homepage must carry location")
	}
	if homepage.Location.Latitude != 33.2601 || homepage.Location.Longitude != 103.9182 {
		t.Fatalf("location axes must round-trip unchanged, got %+v", *homepage.Location)
	}
}

// 下一个 release 修正坐标时必须覆盖旧值，否则 importer 幂等会把错误坐标锁死。
func TestReconcileImportedHomepagesUpdatesLocationOnNextRelease(t *testing.T) {
	svc := newEmptyHomepageService()
	if _, err := reconcileImportedHomepages(
		t, svc,
		[]application.ImportedHomepageInput{importedSightInputAt("九寨沟", 33.0, 103.0)},
		application.HomepageImportModeUpsert, "release-geo-001",
	); err != nil {
		t.Fatalf("first upsert failed: %v", err)
	}
	report, err := reconcileImportedHomepages(
		t, svc,
		[]application.ImportedHomepageInput{importedSightInputAt("九寨沟", 33.2601, 103.9182)},
		application.HomepageImportModeUpsert, "release-geo-002",
	)
	if err != nil {
		t.Fatalf("second upsert failed: %v", err)
	}
	if len(report.Updated) != 1 {
		t.Fatalf("expected 1 updated, got %+v", report)
	}
	homepage, err := svc.GetHomepage(context.Background(), report.Updated[0])
	if err != nil {
		t.Fatalf("get homepage: %v", err)
	}
	if homepage.Location == nil ||
		homepage.Location.Latitude != 33.2601 ||
		homepage.Location.Longitude != 103.9182 {
		t.Fatalf("re-import must refresh location, got %+v", homepage.Location)
	}
}

// 没有坐标的 release 不得抹掉已有坐标，也不得凭空造点。
func TestReconcileImportedHomepagesKeepsLocationWhenReleaseHasNone(t *testing.T) {
	svc := newEmptyHomepageService()
	if _, err := reconcileImportedHomepages(
		t, svc,
		[]application.ImportedHomepageInput{importedSightInputAt("九寨沟", 33.2601, 103.9182)},
		application.HomepageImportModeUpsert, "release-geo-001",
	); err != nil {
		t.Fatalf("first upsert failed: %v", err)
	}
	report, err := reconcileImportedHomepages(
		t, svc,
		[]application.ImportedHomepageInput{importedSightInput("九寨沟")},
		application.HomepageImportModeUpsert, "release-geo-002",
	)
	if err != nil {
		t.Fatalf("second upsert failed: %v", err)
	}
	homepage, err := svc.GetHomepage(context.Background(), report.Updated[0])
	if err != nil {
		t.Fatalf("get homepage: %v", err)
	}
	if homepage.Location == nil || homepage.Location.Latitude != 33.2601 {
		t.Fatalf("coordinate-less release must not clear location, got %+v", homepage.Location)
	}
}

// 越界坐标在 application 边界就被拒，不进聚合、不进 Mongo 2dsphere 建键。
func TestReconcileImportedHomepagesRejectsOutOfRangeLocation(t *testing.T) {
	svc := newEmptyHomepageService()
	_, err := reconcileImportedHomepages(
		t, svc,
		[]application.ImportedHomepageInput{importedSightInputAt("九寨沟", 103.9182, 33.2601)},
		application.HomepageImportModeUpsert, "release-geo-001",
	)
	if err == nil {
		t.Fatalf("out-of-range latitude must be rejected")
	}
	if !strings.Contains(err.Error(), "coordinates") {
		t.Fatalf("rejection must name coordinates, got %v", err)
	}
}
