package orchestration

import (
	"context"
	"errors"
	"strings"
	"time"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_run/domain/ports"
)

// TierDegradingModelProvider 在主档位不可用时沿 ModelTierDegradeOrder 向下重试，让单次
// 运行仍能完成。它只处理"该档位当前不可用"，不掩盖协议错误：invalid_response 一类
// 确定性失败立即上抛，避免用降级掩盖契约漂移。
type TierDegradingModelProvider struct {
	Backend ports.ModelCompletionProvider
}

func (p TierDegradingModelProvider) Complete(
	ctx context.Context,
	request ports.ModelCompletionRequest,
) (result ports.ModelCompletionResult, err error) {
	startedAt := time.Now()
	defer func() {
		observeModelProviderCompletion(request, result, startedAt, err)
	}()
	if p.Backend == nil {
		return ports.ModelCompletionResult{}, ports.ProviderFailure{
			Capability: "model",
			Reason:     ports.ProviderFailureUnavailable,
		}
	}
	var lastErr error
	for _, tier := range ModelTierDegradeOrder(request.Tier) {
		attempt := request
		attempt.Tier = tier
		attemptResult, attemptErr := p.Backend.Complete(ctx, attempt)
		if attemptErr == nil {
			if !validModelCompletionReceipt(attemptResult) {
				return ports.ModelCompletionResult{}, invalidModelCompletionReceipt()
			}
			attemptResult.ModelID = strings.TrimSpace(attemptResult.ModelID)
			return attemptResult, nil
		}
		lastErr = attemptErr
		if !modelTierDegradable(attemptErr) {
			return ports.ModelCompletionResult{}, attemptErr
		}
	}
	return ports.ModelCompletionResult{}, lastErr
}

// Stream 一旦已向客户端发出增量就不再降级：重试会让用户看到两段互相矛盾的回答。
func (p TierDegradingModelProvider) Stream(
	ctx context.Context,
	request ports.ModelCompletionRequest,
	emit func(ports.ModelTextDelta) error,
) (result ports.ModelCompletionResult, err error) {
	startedAt := time.Now()
	defer func() {
		observeModelProviderCompletion(request, result, startedAt, err)
	}()
	if p.Backend == nil {
		return ports.ModelCompletionResult{}, ports.ProviderFailure{
			Capability: "model",
			Reason:     ports.ProviderFailureUnavailable,
		}
	}
	var lastErr error
	for _, tier := range ModelTierDegradeOrder(request.Tier) {
		attempt := request
		attempt.Tier = tier
		emitted := false
		attemptResult, attemptErr := p.Backend.Stream(
			ctx,
			attempt,
			func(delta ports.ModelTextDelta) error {
				emitted = true
				if emit == nil {
					return nil
				}
				return emit(delta)
			},
		)
		if attemptErr == nil {
			if !validModelCompletionReceipt(attemptResult) {
				return ports.ModelCompletionResult{}, invalidModelCompletionReceipt()
			}
			attemptResult.ModelID = strings.TrimSpace(attemptResult.ModelID)
			return attemptResult, nil
		}
		lastErr = attemptErr
		if emitted || !modelTierDegradable(attemptErr) {
			return ports.ModelCompletionResult{}, attemptErr
		}
	}
	return ports.ModelCompletionResult{}, lastErr
}

// SupportsNativeToolCalling 透传底层能力，装饰器不改变协议能力。
func (p TierDegradingModelProvider) SupportsNativeToolCalling() bool {
	return ports.SupportsNativeToolCalling(p.Backend)
}

func (p TierDegradingModelProvider) SupportsParallelModelRequests() bool {
	return ports.SupportsParallelModelRequests(p.Backend)
}

func (p TierDegradingModelProvider) SupportsReasoningTier() bool {
	return ports.SupportsReasoningTier(p.Backend)
}

func modelTierDegradable(err error) bool {
	var failure ports.ProviderFailure
	if !errors.As(err, &failure) || failure.Capability != "model" {
		return false
	}
	switch failure.Reason {
	case ports.ProviderFailureUnavailable, ports.ProviderFailureTimeout:
		return true
	default:
		return false
	}
}

// validModelCompletionReceipt enforces the provider-neutral success boundary.
// Every adapter must prove which configured tier actually served the request
// and return internally consistent usage; HTTP-specific validation alone is
// insufficient because new adapters can implement the same domain port.
func validModelCompletionReceipt(result ports.ModelCompletionResult) bool {
	if strings.TrimSpace(result.ModelID) == "" || !canonicalModelTier(result.TierServed) {
		return false
	}
	usage := result.Usage
	if usage.PromptTokens < 0 || usage.CompletionTokens < 0 || usage.TotalTokens <= 0 ||
		usage.Latency < 0 {
		return false
	}
	return usage.TotalTokens >= usage.PromptTokens+usage.CompletionTokens
}

func canonicalModelTier(tier ports.ModelTier) bool {
	switch tier {
	case ports.ModelTierFast, ports.ModelTierBalanced, ports.ModelTierReasoning:
		return true
	default:
		return false
	}
}

func invalidModelCompletionReceipt() ports.ProviderFailure {
	return ports.ProviderFailure{
		Capability: "model",
		Reason:     ports.ProviderFailureInvalidResponse,
	}
}
