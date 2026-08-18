package bootstrap

import (
	"time"

	rtauth "quwoquan_service/runtime/auth"
	userintegration "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/integration"
)

func newRemoteOTPExternalInteractionClient(
	baseURL string,
	appEnv string,
	signer *rtauth.Signer,
) (*userintegration.ExternalInteractionClient, error) {
	client, err := userintegration.NewIntegrationServiceMTLSClient(3 * time.Second)
	if err != nil {
		return nil, err
	}
	return userintegration.NewExternalInteractionClient(baseURL, appEnv, client, signer)
}
