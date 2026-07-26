package recommendation_test

// N1-3 契约：AB 准入 runner 的纯逻辑（control 桶选择）与生产装配防回归。
// EvaluateAndRecordABAdmission 曾实现完备但零调度；cmd/api composition 必须保持
// ABAdmissionRunner 的周期启动，runner 的观测→评估→记账走同一代码路径。

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	recpolicy "quwoquan_service/runtime/recpolicy"
	. "quwoquan_service/services/content-service/internal/content/post/infrastructure/recommendation"
	"quwoquan_service/services/content-service/tests/support"
)

func TestControlBucketSelection(t *testing.T) {
	cases := []struct {
		name    string
		buckets []recpolicy.ExperimentBucket
		want    string
	}{
		{
			name: "explicit control wins",
			buckets: []recpolicy.ExperimentBucket{
				{Name: "model", WeightPct: 90},
				{Name: "control", WeightPct: 10},
			},
			want: "control",
		},
		{
			name: "rule counts as control",
			buckets: []recpolicy.ExperimentBucket{
				{Name: "rule", WeightPct: 100},
				{Name: "model", WeightPct: 0},
			},
			want: "rule",
		},
		{
			name: "fallback to heaviest bucket",
			buckets: []recpolicy.ExperimentBucket{
				{Name: "variant_a", WeightPct: 30},
				{Name: "variant_b", WeightPct: 70},
			},
			want: "variant_b",
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := ControlBucketFor(recpolicy.ExperimentDef{Buckets: tc.buckets})
			if got != tc.want {
				t.Fatalf("ControlBucketFor = %q, want %q", got, tc.want)
			}
		})
	}
}

// 生产装配防回归：cmd/api composition 必须启动 ABAdmissionRunner 周期任务，
// 否则 ab_experiment_validity SLI 再次退化为无数据虚标。
func TestMainWiresABAdmissionRunner(t *testing.T) {
	apiRoot := filepath.Join(support.ServiceRoot(), "cmd", "api")
	entries, err := os.ReadDir(apiRoot)
	if err != nil {
		t.Fatalf("read cmd/api composition: %v", err)
	}
	var source strings.Builder
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".go") ||
			strings.HasSuffix(entry.Name(), "_test.go") {
			continue
		}
		payload, readErr := os.ReadFile(filepath.Join(apiRoot, entry.Name()))
		if readErr != nil {
			t.Fatalf("read cmd/api composition file %s: %v", entry.Name(), readErr)
		}
		source.Write(payload)
	}
	if !strings.Contains(source.String(), "NewABAdmissionRunner") {
		t.Fatal("cmd/api composition must wire ABAdmissionRunner (N1-3); ab_experiment_validity has no data source otherwise")
	}
	if !strings.Contains(source.String(), "WithExperimentBucketResolver") {
		t.Fatal("cmd/api composition must wire WithExperimentBucketResolver so behavior attribution carries experiment_bucket")
	}
}
