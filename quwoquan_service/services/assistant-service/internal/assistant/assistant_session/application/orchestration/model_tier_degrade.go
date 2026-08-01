package orchestration

import (
	"context"
	"errors"

	"quwoquan_service/services/assistant-service/internal/assistant/assistant_session/domain/ports"
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
) (ports.ModelCompletionResult, error) {
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
		result, err := p.Backend.Complete(ctx, attempt)
		if err == nil {
			return result, nil
		}
		lastErr = err
		if !modelTierDegradable(err) {
			return ports.ModelCompletionResult{}, err
		}
	}
	return ports.ModelCompletionResult{}, lastErr
}

// Stream 一旦已向客户端发出增量就不再降级：重试会让用户看到两段互相矛盾的回答。
func (p TierDegradingModelProvider) Stream(
	ctx context.Context,
	request ports.ModelCompletionRequest,
	emit func(ports.ModelTextDelta) error,
) (ports.ModelCompletionResult, error) {
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
		result, err := p.Backend.Stream(
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
		if err == nil {
			return result, nil
		}
		lastErr = err
		if emitted || !modelTierDegradable(err) {
			return ports.ModelCompletionResult{}, err
		}
	}
	return ports.ModelCompletionResult{}, lastErr
}

// SupportsNativeToolCalling 透传底层能力，装饰器不改变协议能力。
func (p TierDegradingModelProvider) SupportsNativeToolCalling() bool {
	return ports.SupportsNativeToolCalling(p.Backend)
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
