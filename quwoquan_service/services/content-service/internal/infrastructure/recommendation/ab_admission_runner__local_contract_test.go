package recommendation

// N1-3 契约：AB 准入 runner 的纯逻辑（control 桶选择）与生产装配防回归。
// EvaluateAndRecordABAdmission 曾实现完备但零调度；main.go 必须保持
// ABAdmissionRunner 的周期启动，runner 的观测→评估→记账走同一代码路径。

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	recpolicy "quwoquan_service/runtime/recpolicy"
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
			got := controlBucketFor(recpolicy.ExperimentDef{Buckets: tc.buckets})
			if got != tc.want {
				t.Fatalf("controlBucketFor = %q, want %q", got, tc.want)
			}
		})
	}
}

// 生产装配防回归：main.go 必须启动 ABAdmissionRunner 周期任务，
// 否则 ab_experiment_validity SLI 再次退化为无数据虚标。
func TestMainWiresABAdmissionRunner(t *testing.T) {
	mainPath := filepath.Join("..", "..", "..", "cmd", "api", "main.go")
	payload, err := os.ReadFile(mainPath)
	if err != nil {
		t.Fatalf("read main.go: %v", err)
	}
	source := string(payload)
	if !strings.Contains(source, "NewABAdmissionRunner") {
		t.Fatal("main.go must wire ABAdmissionRunner (N1-3); ab_experiment_validity has no data source otherwise")
	}
	if !strings.Contains(source, "WithExperimentBucketResolver") {
		t.Fatal("main.go must wire WithExperimentBucketResolver so behavior attribution carries experiment_bucket")
	}
}
