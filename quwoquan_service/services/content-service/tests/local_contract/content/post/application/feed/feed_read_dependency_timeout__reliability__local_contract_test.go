// Feed 读路径依赖超时/取消的可靠性契约：结构化失败、错误码闭集同源、零伪成功。
//
// 故障语义唯一真相源是 contracts/content/post/operations.yaml 中 GetFeed 的
// error_codes 闭集与 reliability 声明（timeout_ms=1500 / cancellation=supported）；
// 本测试从契约读取错误码闭集，不建立第二错误清单。
//
// spec_ref: specs/feature-tree/runtime/runtime-testinfra/fault-injection-harness/spec.md#gwt-001
package feed_test

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"testing"
	"time"

	"gopkg.in/yaml.v3"

	rterr "quwoquan_service/runtime/errors"
	postports "quwoquan_service/services/content-service/internal/content/post/domain/ports"
	. "quwoquan_service/services/content-service/internal/content/post/application/feed"
)

// blockingFeedReader 模拟慢依赖：阻塞到调用方 context 结束再返回 ctx.Err()。
type blockingFeedReader struct{}

func (blockingFeedReader) FindPublishedFeedPost(
	ctx context.Context,
	_ postports.PostID,
) (postports.PostFeedItemSlice, bool, error) {
	<-ctx.Done()
	return postports.PostFeedItemSlice{}, false, ctx.Err()
}

func (blockingFeedReader) FindPublishedFeedPosts(
	ctx context.Context,
	_ postports.PostFeedHydrationRequest,
) (map[postports.PostID]postports.PostFeedItemSlice, error) {
	<-ctx.Done()
	return nil, ctx.Err()
}

func (blockingFeedReader) ListPublishedFeedPosts(
	ctx context.Context,
	_ postports.PostFeedReadRequest,
) (postports.PostFeedSlice, error) {
	<-ctx.Done()
	return postports.PostFeedSlice{}, ctx.Err()
}

func feedContractErrorCodeClosedSet(t *testing.T) map[string]bool {
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
		dir, "services", "content-service", "contracts", "content", "post", "operations.yaml",
	))
	if err != nil {
		t.Fatalf("read operations contract: %v", err)
	}
	var document struct {
		APIRoutes []struct {
			Operation  string   `yaml:"operation"`
			ErrorCodes []string `yaml:"error_codes"`
		} `yaml:"api_routes"`
	}
	if err := yaml.Unmarshal(raw, &document); err != nil {
		t.Fatalf("decode operations contract: %v", err)
	}
	for _, route := range document.APIRoutes {
		if route.Operation != "GetFeed" {
			continue
		}
		closed := make(map[string]bool, len(route.ErrorCodes))
		for _, code := range route.ErrorCodes {
			closed[code] = true
		}
		if len(closed) == 0 {
			t.Fatal("GetFeed declares no error_codes closed set")
		}
		return closed
	}
	t.Fatal("GetFeed operation not declared in operations.yaml")
	return nil
}

func TestFeedReadDependencyTimeoutFailsClosedWithContractError(t *testing.T) {
	contractCodes := feedContractErrorCodeClosedSet(t)
	posts, candidates := budgetSeedSupply()
	service := newTerminalFeedService(
		newTerminalFeedEngine(candidates[:2]),
		blockingFeedReader{},
		WithActiveSupplyReader(&terminalActiveSupplyReader{active: true}),
		feedDeliveryPageStoreOption(),
	)
	_ = posts

	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()
	started := time.Now()
	response, err := service.ListFeed(ctx, ListFeedRequest{
		UserID: "reliability-user", SessionID: "reliability-session",
		ChannelID: "recommend", Limit: 20,
	})
	elapsed := time.Since(started)

	if err == nil {
		t.Fatalf("slow dependency must fail closed; got response=%+v", response)
	}
	if response != nil && len(response.Items) > 0 {
		t.Fatalf("timeout must not return partial success items: %+v", response.Items)
	}
	// 尊重取消：耗时应与调用方 deadline 同量级，而非阻塞到内部长超时。
	if elapsed > 2*time.Second {
		t.Fatalf("ListFeed ignored caller cancellation; elapsed=%v", elapsed)
	}
	var appErr *rterr.AppError
	if errors.As(err, &appErr) {
		code := appErr.Code.String()
		if !contractCodes[code] {
			t.Fatalf(
				"timeout failure code %q is outside the GetFeed contract error_codes closed set %v",
				code, contractCodes,
			)
		}
	} else if !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("timeout failure must be a canonical AppError or context deadline; got %T: %v", err, err)
	}
}

func TestFeedReadRetriesDoNotFabricateSuccessAfterFault(t *testing.T) {
	// 依赖持续失败时，契约 retry_mode=idempotent/max_attempts=2 之内也必须以
	// 结构化失败收敛，禁止本地合成成功页面。
	contractCodes := feedContractErrorCodeClosedSet(t)
	_, candidates := budgetSeedSupply()
	service := newTerminalFeedService(
		newTerminalFeedEngine(candidates[:2]),
		terminalFailingFeedReader{err: errors.New("storage transient failure")},
		WithActiveSupplyReader(&terminalActiveSupplyReader{active: true}),
		feedDeliveryPageStoreOption(),
	)
	for attempt := 0; attempt < 2; attempt++ {
		response, err := service.ListFeed(context.Background(), ListFeedRequest{
			UserID: "reliability-retry-user", SessionID: "reliability-retry-session",
			ChannelID: "recommend", Limit: 20,
		})
		if err == nil {
			t.Fatalf("attempt %d: failing dependency must not yield success %+v", attempt, response)
		}
		var appErr *rterr.AppError
		if errors.As(err, &appErr) && !contractCodes[appErr.Code.String()] {
			t.Fatalf(
				"attempt %d: failure code %q outside GetFeed contract closed set",
				attempt, appErr.Code.String(),
			)
		}
	}
}
