// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/tool-fabric-runtime/spec.md#gwt-001
package local_contract

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"

	toolpkg "quwoquan_service/services/assistant-service/internal/assistant/assistant_conversation/application/tool"
)

type retryableToolError struct{}

func (retryableToolError) Error() string              { return "upstream jitter" }
func (retryableToolError) RetryableToolFailure() bool { return true }

// 工具持续超时必须在声明的尝试次数内停止，并带出该工具的恢复语义。
func TestToolTimeoutStopsWithinDeclaredAttempts(t *testing.T) {
	attempts := 0
	meta := toolpkg.DefaultMetadata("slow_probe")
	meta.Resilience.TimeoutMs = 20
	meta.Resilience.MaxAttempts = 3
	meta.Resilience.RetryBackoffMs = 1
	meta.Recovery = toolpkg.RecoveryPolicy{
		Action:             "degrade_answer",
		DisruptionLevel:    "partial",
		UserVisibleSummary: "实时数据暂不可用",
	}
	registry := toolpkg.BaseRegistry()
	registry.Register(meta, func(ctx context.Context, _ toolpkg.Request) (toolpkg.Result, error) {
		attempts++
		select {
		case <-ctx.Done():
			return toolpkg.Result{}, ctx.Err()
		case <-time.After(2 * time.Second):
			return toolpkg.Result{Output: map[string]any{"summary": "永远不该返回"}}, nil
		}
	})

	started := time.Now()
	_, err := registry.Execute(context.Background(), toolpkg.Request{
		ToolName: "slow_probe",
		Input:    map[string]any{"query": "杭州明天天气"},
	})
	elapsed := time.Since(started)
	if err == nil {
		t.Fatal("timing out tool must not report success")
	}
	if attempts != 3 {
		t.Fatalf("attempts=%d, want 3 as declared by MaxAttempts", attempts)
	}
	if elapsed > time.Second {
		t.Fatalf("elapsed=%v, per-attempt timeout was not enforced", elapsed)
	}
	var failure toolpkg.ExecutionFailure
	if !errors.As(err, &failure) {
		t.Fatalf("err=%v, want ExecutionFailure carrying recovery policy", err)
	}
	if failure.Recovery.Action != "degrade_answer" ||
		failure.Recovery.UserVisibleSummary != "实时数据暂不可用" {
		t.Fatalf("recovery=%+v, want declared degrade_answer policy", failure.Recovery)
	}
}

// 不可重试的失败不得消耗剩余尝试次数。
func TestNonRetryableToolFailureDoesNotRetry(t *testing.T) {
	attempts := 0
	meta := toolpkg.DefaultMetadata("deterministic_probe")
	meta.Resilience.MaxAttempts = 3
	registry := toolpkg.BaseRegistry()
	registry.Register(meta, func(_ context.Context, _ toolpkg.Request) (toolpkg.Result, error) {
		attempts++
		return toolpkg.Result{}, errors.New("contract rejected the request")
	})

	if _, err := registry.Execute(context.Background(), toolpkg.Request{
		ToolName: "deterministic_probe",
		Input:    map[string]any{"query": "问题"},
	}); err == nil {
		t.Fatal("deterministic failure must surface")
	}
	if attempts != 1 {
		t.Fatalf("attempts=%d, want 1 for non-retryable failure", attempts)
	}
}

// 声明可重试的失败在预算内重试，成功后返回真实结果。
func TestRetryableToolFailureRecoversWithinBudget(t *testing.T) {
	attempts := 0
	meta := toolpkg.DefaultMetadata("flaky_probe")
	meta.Resilience.MaxAttempts = 3
	meta.Resilience.RetryBackoffMs = 1
	registry := toolpkg.BaseRegistry()
	registry.Register(meta, func(_ context.Context, _ toolpkg.Request) (toolpkg.Result, error) {
		attempts++
		if attempts < 3 {
			return toolpkg.Result{}, retryableToolError{}
		}
		return toolpkg.Result{Output: map[string]any{"summary": "第三次成功"}}, nil
	})

	result, err := registry.Execute(context.Background(), toolpkg.Request{
		ToolName: "flaky_probe",
		Input:    map[string]any{"query": "问题"},
	})
	if err != nil {
		t.Fatalf("retryable failure should recover within budget: %v", err)
	}
	if attempts != 3 || result.Output["summary"] != "第三次成功" {
		t.Fatalf("attempts=%d output=%#v", attempts, result.Output)
	}
}

// 循环检测窗口内的重复调用必须被拒绝，且不进入 handler。
func TestLoopDetectionRejectsRepeatedToolWithoutInvoking(t *testing.T) {
	attempts := 0
	meta := toolpkg.DefaultMetadata("loop_probe")
	meta.Resilience.LoopDetectionWindow = 2
	registry := toolpkg.BaseRegistry()
	registry.Register(meta, func(_ context.Context, _ toolpkg.Request) (toolpkg.Result, error) {
		attempts++
		return toolpkg.Result{Output: map[string]any{"summary": "结果"}}, nil
	})

	_, err := registry.Execute(context.Background(), toolpkg.Request{
		ToolName: "loop_probe",
		Input:    map[string]any{"query": "问题"},
		History:  []string{"loop_probe", "loop_probe"},
	})
	if err == nil || !strings.Contains(err.Error(), "loop detected") {
		t.Fatalf("err=%v, want loop detection", err)
	}
	if attempts != 0 {
		t.Fatalf("attempts=%d, loop detection must run before invoking handler", attempts)
	}
}

// 输出缺必填键属于确定性错误，不得重试也不得当作成功观察。
func TestOutputContractViolationIsNotRetried(t *testing.T) {
	attempts := 0
	meta := toolpkg.DefaultMetadata("bad_output_probe")
	meta.Resilience.MaxAttempts = 3
	registry := toolpkg.BaseRegistry()
	registry.Register(meta, func(_ context.Context, _ toolpkg.Request) (toolpkg.Result, error) {
		attempts++
		return toolpkg.Result{Output: map[string]any{"unexpected": "值"}}, nil
	})

	_, err := registry.Execute(context.Background(), toolpkg.Request{
		ToolName: "bad_output_probe",
		Input:    map[string]any{"query": "问题"},
	})
	if err == nil || !strings.Contains(err.Error(), "summary") {
		t.Fatalf("err=%v, want missing output key", err)
	}
	if attempts != 1 {
		t.Fatalf("attempts=%d, output contract violation must not retry", attempts)
	}
}
