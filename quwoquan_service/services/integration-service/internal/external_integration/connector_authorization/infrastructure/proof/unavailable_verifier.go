package proof

import (
	"context"

	"quwoquan_service/services/integration-service/internal/external_integration/connector_authorization/domain/model"
)

// UnavailableVerifier 是生产组合根在未绑定受信 native/OAuth adapter 时的 fail-closed
// 实现。它不会把客户端自报 proofRef 或 callbackRef 当作授权成功。
type UnavailableVerifier struct{}

func NewUnavailableVerifier() UnavailableVerifier {
	return UnavailableVerifier{}
}

func (UnavailableVerifier) VerifyNative(
	context.Context,
	model.Authorization,
	string,
) (model.VerifiedProof, error) {
	return model.VerifiedProof{}, model.ErrProviderUnavailable
}

func (UnavailableVerifier) VerifyOAuth(
	context.Context,
	model.Authorization,
	string,
) (model.VerifiedProof, error) {
	return model.VerifiedProof{}, model.ErrProviderUnavailable
}
