// Tag 读路径进程内延迟预算：固定 seed 标签树 + 重复采样 p95 对照契约 SLO。
//
// 预算唯一真相源是 contracts/tag/tag_node_view/operations.yaml 中 ResolveTag 的
// slo.latency_p95_ms；本测试从契约读取阈值，不承载第二份预算值。进程内
// application 路径的 p95 一旦逼近端到端 SLO，说明出现量级劣化。
//
// spec_ref: specs/feature-tree/runtime/runtime-testinfra/performance-load-harness/spec.md#gwt-001
package local_contract

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"testing"
	"time"

	"gopkg.in/yaml.v3"

	"quwoquan_service/services/tag-service/internal/tag/tag_node_view/application"
	"quwoquan_service/services/tag-service/internal/tag/tag_node_view/domain/model"
)

const (
	budgetSeedTagCount = 500
	budgetSampleCount  = 50
)

func resolveTagContractSLOLatencyP95Ms(t *testing.T) int {
	t.Helper()
	dir, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	for {
		if _, statErr := os.Stat(filepath.Join(dir, "go.mod")); statErr == nil {
			if _, metadataErr := os.Stat(filepath.Join(dir, "contracts/metadata")); metadataErr == nil {
				break
			}
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			t.Fatal("quwoquan_service root not found above test directory")
		}
		dir = parent
	}
	raw, err := os.ReadFile(filepath.Join(
		dir, "services", "tag-service", "contracts", "tag", "tag_node_view", "operations.yaml",
	))
	if err != nil {
		t.Fatalf("read operations contract: %v", err)
	}
	var document struct {
		APIRoutes []struct {
			Operation string `yaml:"operation"`
			SLO       struct {
				LatencyP95Ms int `yaml:"latency_p95_ms"`
			} `yaml:"slo"`
		} `yaml:"api_routes"`
	}
	if err := yaml.Unmarshal(raw, &document); err != nil {
		t.Fatalf("decode operations contract: %v", err)
	}
	for _, route := range document.APIRoutes {
		if route.Operation == "ResolveTag" {
			if route.SLO.LatencyP95Ms <= 0 {
				t.Fatal("ResolveTag declares no slo.latency_p95_ms; budget test cannot fabricate a threshold")
			}
			return route.SLO.LatencyP95Ms
		}
	}
	t.Fatal("ResolveTag operation not declared in operations.yaml")
	return 0
}

func budgetSeedTagNodes() map[string]*model.TagNode {
	nodes := make(map[string]*model.TagNode, budgetSeedTagCount)
	for index := 0; index < budgetSeedTagCount; index++ {
		tagRef := fmt.Sprintf("Topic/预算样本/%04d", index)
		nodes[tagRef] = &model.TagNode{
			TagRef:          tagRef,
			Group:           "Topic",
			Label:           fmt.Sprintf("预算样本%04d", index),
			LabelEn:         fmt.Sprintf("BudgetSample%04d", index),
			ParentTagRef:    "Topic/预算样本",
			ReleaseID:       "release-current",
			LifecycleStatus: "active",
		}
	}
	return nodes
}

func TestTagResolveLatencyBudgetHoldsContractSLO(t *testing.T) {
	sloP95Ms := resolveTagContractSLOLatencyP95Ms(t)
	service := application.NewTagService(
		migratedTagNodeReader{nodes: budgetSeedTagNodes()},
		migratedObjectTagIndexReader{},
		migratedActiveReleaseReader{releaseID: "release-current", found: true},
	)

	// 预热一次，排除首次初始化成本混入采样。
	if _, err := service.Resolve(context.Background(), "Topic/预算样本/0000"); err != nil {
		t.Fatalf("warmup resolve: %v", err)
	}

	latenciesMs := make([]float64, 0, budgetSampleCount)
	for sample := 0; sample < budgetSampleCount; sample++ {
		tagRef := fmt.Sprintf("Topic/预算样本/%04d", sample%budgetSeedTagCount)
		started := time.Now()
		view, err := service.Resolve(context.Background(), tagRef)
		elapsedMs := float64(time.Since(started).Microseconds()) / 1000
		if err != nil || view == nil {
			t.Fatalf("sample %d resolve %s: view=%v err=%v", sample, tagRef, view, err)
		}
		latenciesMs = append(latenciesMs, elapsedMs)
	}

	sort.Float64s(latenciesMs)
	index := (95*len(latenciesMs)+99)/100 - 1
	if index < 0 {
		index = 0
	}
	p95Ms := latenciesMs[index]
	t.Logf(
		"tag resolve in-process latency over %d samples (%d seeded tags): p95=%.3fms contract slo=%dms",
		len(latenciesMs), budgetSeedTagCount, p95Ms, sloP95Ms,
	)
	if p95Ms > float64(sloP95Ms) {
		t.Fatalf(
			"in-process tag resolve p95 %.3fms exceeds contract slo.latency_p95_ms %dms; "+
				"this indicates an order-of-magnitude regression in the tag read path",
			p95Ms, sloP95Ms,
		)
	}
}
