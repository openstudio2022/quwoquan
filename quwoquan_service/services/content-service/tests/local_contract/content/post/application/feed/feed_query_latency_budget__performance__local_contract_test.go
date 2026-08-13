// Feed 查询进程内延迟预算：固定 seed 供给 + 重复采样 p95 对照契约 SLO。
//
// 预算唯一真相源是 contracts/content/post/operations.yaml 中 GetFeed 的
// slo.latency_p95_ms；本测试从契约读取阈值，不承载第二份预算值。进程内
// application 路径的 p95 一旦逼近端到端 SLO，说明出现量级劣化（如每页
// 全量重排、无界物化），应在合入前阻断。
//
// spec_ref: specs/feature-tree/runtime/runtime-test-pyramid/spec.md#sit-002
package feed_test

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"testing"
	"time"

	"gopkg.in/yaml.v3"

	rtrec "quwoquan_service/runtime/recommendation"
	postmodel "quwoquan_service/services/content-service/generated/content/post/contract/model"
	. "quwoquan_service/services/content-service/internal/content/post/application/feed"
)

const (
	budgetSeedPostCount = 500
	budgetSampleCount   = 50
)

func feedContractSLOLatencyP95Ms(t *testing.T) int {
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
	contractPath := filepath.Join(
		dir, "services", "content-service", "contracts", "content", "post", "operations.yaml",
	)
	raw, err := os.ReadFile(contractPath)
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
		if route.Operation == "GetFeed" {
			if route.SLO.LatencyP95Ms <= 0 {
				t.Fatal("GetFeed declares no slo.latency_p95_ms; budget test cannot fabricate a threshold")
			}
			return route.SLO.LatencyP95Ms
		}
	}
	t.Fatal("GetFeed operation not declared in operations.yaml")
	return 0
}

func budgetSeedSupply() ([]postmodel.Post, []rtrec.ContentCandidate) {
	base := time.Date(2026, 6, 10, 10, 0, 0, 0, time.UTC)
	posts := make([]postmodel.Post, 0, budgetSeedPostCount)
	candidates := make([]rtrec.ContentCandidate, 0, budgetSeedPostCount)
	for index := 0; index < budgetSeedPostCount; index++ {
		publishedAt := base.Add(-time.Duration(index) * time.Minute)
		post := postmodel.Post{
			ID:              fmt.Sprintf("budget-video-%04d", index),
			AuthorId:        fmt.Sprintf("budget-author-%02d", index%25),
			ContentType:     "video",
			ContentIdentity: "work",
			Status:          "published",
			Visibility:      "public",
			VideoUrl:        fmt.Sprintf("https://media.example.test/budget-%04d.mp4", index),
			DurationMs:      5000,
			CreatedAt:       publishedAt,
			PublishedAt:     publishedAt,
		}
		posts = append(posts, post)
		candidates = append(candidates, rtrec.ContentCandidate{
			ContentID:   post.ID,
			ContentType: post.ContentType,
			AuthorID:    post.AuthorId,
			PublishedAt: post.PublishedAt,
		})
	}
	return posts, candidates
}

func TestFeedQueryLatencyBudgetHoldsContractSLO(t *testing.T) {
	sloP95Ms := feedContractSLOLatencyP95Ms(t)
	posts, candidates := budgetSeedSupply()
	service := newTerminalFeedService(
		newTerminalFeedEngine(candidates),
		fixtureFeedReader{posts: posts},
		WithActiveSupplyReader(&terminalActiveSupplyReader{active: true}),
		feedDeliveryPageStoreOption(),
	)

	// 预热一次，排除首次初始化成本混入采样。
	if _, err := service.ListFeed(context.Background(), ListFeedRequest{
		UserID: "budget-warmup", SessionID: "budget-session-warmup",
		ChannelID: "recommend", Limit: 20,
	}); err != nil {
		t.Fatalf("warmup feed query: %v", err)
	}

	latenciesMs := make([]float64, 0, budgetSampleCount)
	for sample := 0; sample < budgetSampleCount; sample++ {
		request := ListFeedRequest{
			UserID:    fmt.Sprintf("budget-user-%02d", sample),
			SessionID: fmt.Sprintf("budget-session-%02d", sample),
			ChannelID: "recommend",
			Limit:     20,
		}
		started := time.Now()
		response, err := service.ListFeed(context.Background(), request)
		elapsedMs := float64(time.Since(started).Microseconds()) / 1000
		if err != nil {
			t.Fatalf("sample %d feed query: %v", sample, err)
		}
		if len(response.Items) == 0 {
			t.Fatalf("sample %d returned no feed items; budget sampling requires real pages", sample)
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
		"feed query in-process latency over %d samples (%d seeded posts): p95=%.2fms contract slo=%dms",
		len(latenciesMs), budgetSeedPostCount, p95Ms, sloP95Ms,
	)
	if p95Ms > float64(sloP95Ms) {
		t.Fatalf(
			"in-process feed query p95 %.2fms exceeds contract slo.latency_p95_ms %dms; "+
				"this indicates an order-of-magnitude regression in the feed read path",
			p95Ms, sloP95Ms,
		)
	}
}
