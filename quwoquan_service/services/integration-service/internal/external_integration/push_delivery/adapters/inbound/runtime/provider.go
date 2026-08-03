package runtimeadapter

import (
	"context"
	"fmt"

	"quwoquan_service/runtime/reliabletask"
	pushapp "quwoquan_service/services/integration-service/internal/external_integration/push_delivery/application"
)

// Provider 是 reliable-task 进入 PushDelivery external port 的唯一入站适配器。
// 它在任何 endpoint secret 解析或 provider 调用前执行 typed payload 校验。
type Provider struct {
	delegate reliabletask.ExternalProvider
}

func NewProvider(delegate reliabletask.ExternalProvider) (*Provider, error) {
	if delegate == nil {
		return nil, fmt.Errorf("push delivery provider delegate is required")
	}
	return &Provider{delegate: delegate}, nil
}

func (provider *Provider) Send(
	ctx context.Context,
	request reliabletask.ExternalInteractionRequest,
	task reliabletask.ReliableAsyncTask,
) (reliabletask.ExternalInteractionResult, error) {
	if err := pushapp.ValidatePushDeliveryRequest(request); err != nil {
		return reliabletask.ExternalInteractionResult{}, err
	}
	return provider.delegate.Send(ctx, request, task)
}

var _ reliabletask.ExternalProvider = (*Provider)(nil)
