// spec_ref: specs/feature-tree/platform-ops-governance/commercial-readiness-risk-closure/spec.md#req-006
// 断言 GetPlatformTriageSummary 的 stale 分类：上报新鲜度边界、stale 与
// out-of-sync 互斥、排序键与截断上限、空态序列化、runtimeReady 阻断。
package local_contract

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"testing"
	"time"

	reportapp "quwoquan_service/control-plane/platform-ops/internal/platform_ops/config_instance_report/application"
	"quwoquan_service/runtime/controlplane"
	"quwoquan_service/runtime/controlplane/testsupport"
)

const triageStaleCandidate = "sha256:dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"

var triageStaleNow = time.Date(2026, 8, 6, 9, 0, 0, 0, time.UTC)

func newTriageStaleFacade(
	t *testing.T,
	reports []map[string]any,
) *reportapp.RuntimeFacade {
	t.Helper()
	store := testsupport.NewFileStore(t.TempDir() + "/platform-triage-stale.json")
	for _, report := range reports {
		id, _ := report["id"].(string)
		if err := store.PutDocument("config_instance_reports", id, report); err != nil {
			t.Fatal(err)
		}
	}
	topology := reportapp.RuntimeTopologyReaderFunc(
		func(context.Context) (reportapp.RuntimeTopology, error) {
			return reportapp.RuntimeTopology{}, nil
		},
	)
	facade, err := reportapp.NewRuntimeFacade(
		store,
		topology,
		triageStaleCandidate,
		func() time.Time { return triageStaleNow },
	)
	if err != nil {
		t.Fatal(err)
	}
	return facade
}

func triageStaleReport(id string, inSync bool, updatedAt string) map[string]any {
	report := map[string]any{
		"id": id, "instanceId": id,
		"environment": "beta", "cluster": "beta-control-a", "service": "content-service",
		"releaseManifestDigest": triageStaleCandidate,
		"desiredHash":           "expected", "effectiveHash": "expected",
		"inSync": inSync, "source": "config-center",
	}
	if !inSync {
		report["effectiveHash"] = "actual"
	}
	if updatedAt != "" {
		report["updatedAt"] = updatedAt
	}
	return report
}

func TestTriageStaleClassificationBoundary(t *testing.T) {
	t.Parallel()
	exactThreshold := triageStaleNow.Add(-10 * time.Minute).Format(time.RFC3339)
	beyondThreshold := triageStaleNow.Add(-10*time.Minute - time.Second).Format(time.RFC3339)
	facade := newTriageStaleFacade(t, []map[string]any{
		triageStaleReport("fresh-at-threshold", true, exactThreshold),
		triageStaleReport("stale-beyond-threshold", true, beyondThreshold),
		triageStaleReport("stale-missing-updated-at", true, ""),
		triageStaleReport("stale-invalid-updated-at", true, "not-a-timestamp"),
	})
	summary, err := facade.GetTriageSummary(
		context.Background(), controlplane.ConfigResolutionScope{},
	)
	if err != nil {
		t.Fatal(err)
	}
	if summary.ConfigDrift.TotalInstances != 4 {
		t.Fatalf("total=%d", summary.ConfigDrift.TotalInstances)
	}
	if summary.ConfigDrift.InSyncInstances != 1 {
		t.Fatalf("inSync=%d, exactly the at-threshold report must stay fresh", summary.ConfigDrift.InSyncInstances)
	}
	if summary.ConfigDrift.StaleInstances != 3 {
		t.Fatalf("stale=%d, beyond-threshold/missing/invalid updatedAt must all classify stale", summary.ConfigDrift.StaleInstances)
	}
	if len(summary.StaleInstances) != 3 {
		t.Fatalf("stale list=%d", len(summary.StaleInstances))
	}
	for _, item := range summary.StaleInstances {
		if item.InstanceID == "fresh-at-threshold" {
			t.Fatal("at-threshold report must not classify stale")
		}
	}
}

func TestTriageStaleAndOutOfSyncAreMutuallyExclusive(t *testing.T) {
	t.Parallel()
	staleAt := triageStaleNow.Add(-30 * time.Minute).Format(time.RFC3339)
	freshAt := triageStaleNow.Add(-time.Minute).Format(time.RFC3339)
	facade := newTriageStaleFacade(t, []map[string]any{
		triageStaleReport("stale-and-out-of-sync", false, staleAt),
		triageStaleReport("fresh-out-of-sync", false, freshAt),
	})
	summary, err := facade.GetTriageSummary(
		context.Background(), controlplane.ConfigResolutionScope{},
	)
	if err != nil {
		t.Fatal(err)
	}
	if summary.ConfigDrift.StaleInstances != 1 || summary.ConfigDrift.OutOfSyncInstances != 1 {
		t.Fatalf(
			"stale=%d outOfSync=%d, a stale report must not double-count as out-of-sync",
			summary.ConfigDrift.StaleInstances, summary.ConfigDrift.OutOfSyncInstances,
		)
	}
	if len(summary.OutOfSyncInstances) != 1 || summary.OutOfSyncInstances[0].InstanceID != "fresh-out-of-sync" {
		t.Fatalf("outOfSync list=%+v", summary.OutOfSyncInstances)
	}
	if len(summary.StaleInstances) != 1 || summary.StaleInstances[0].InstanceID != "stale-and-out-of-sync" {
		t.Fatalf("stale list=%+v", summary.StaleInstances)
	}
}

func TestTriageStaleListSortKeysAndTruncation(t *testing.T) {
	t.Parallel()
	staleAt := triageStaleNow.Add(-time.Hour).Format(time.RFC3339)
	reports := make([]map[string]any, 0, 10)
	for index := 9; index >= 0; index-- {
		report := triageStaleReport(fmt.Sprintf("instance-%d", index), true, staleAt)
		report["service"] = fmt.Sprintf("service-%d", index%2)
		reports = append(reports, report)
	}
	facade := newTriageStaleFacade(t, reports)
	summary, err := facade.GetTriageSummary(
		context.Background(), controlplane.ConfigResolutionScope{},
	)
	if err != nil {
		t.Fatal(err)
	}
	if summary.ConfigDrift.StaleInstances != 10 {
		t.Fatalf("stale count=%d", summary.ConfigDrift.StaleInstances)
	}
	if len(summary.StaleInstances) != 8 {
		t.Fatalf("stale list must truncate to 8, got %d", len(summary.StaleInstances))
	}
	for index := 1; index < len(summary.StaleInstances); index++ {
		previous, current := summary.StaleInstances[index-1], summary.StaleInstances[index]
		previousKey := previous.Service + "|" + previous.Cluster + "|" + previous.InstanceID
		currentKey := current.Service + "|" + current.Cluster + "|" + current.InstanceID
		if previousKey > currentKey {
			t.Fatalf("stale list must sort by service/cluster/instanceId, got %s before %s", previousKey, currentKey)
		}
	}
}

func TestTriageStaleEmptyStateSerializesAsEmptyArray(t *testing.T) {
	t.Parallel()
	freshAt := triageStaleNow.Add(-time.Minute).Format(time.RFC3339)
	facade := newTriageStaleFacade(t, []map[string]any{
		triageStaleReport("fresh-only", true, freshAt),
	})
	summary, err := facade.GetTriageSummary(
		context.Background(), controlplane.ConfigResolutionScope{},
	)
	if err != nil {
		t.Fatal(err)
	}
	payload, err := json.Marshal(summary)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(payload), `"staleInstances":[]`) {
		t.Fatalf("empty stale list must serialize as [], payload=%s", payload)
	}
}

func TestTriageRuntimeReadyBlockedByStaleInstances(t *testing.T) {
	t.Parallel()
	staleAt := triageStaleNow.Add(-time.Hour).Format(time.RFC3339)
	freshAt := triageStaleNow.Add(-time.Minute).Format(time.RFC3339)
	facade := newTriageStaleFacade(t, []map[string]any{
		triageStaleReport("fresh-in-sync", true, freshAt),
		triageStaleReport("stale-liveness-lost", true, staleAt),
	})
	summary, err := facade.GetTriageSummary(
		context.Background(), controlplane.ConfigResolutionScope{},
	)
	if err != nil {
		t.Fatal(err)
	}
	if summary.RuntimeReady {
		t.Fatal("a stale instance cannot prove convergence; runtimeReady must be false")
	}
	foundStaleCandidate := false
	for _, candidate := range summary.BacklogCandidates {
		if candidate.Category == "config_staleness" {
			foundStaleCandidate = true
		}
	}
	if !foundStaleCandidate {
		t.Fatal("stale instances must surface a config_staleness backlog candidate")
	}
}
