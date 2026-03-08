package application

import (
	"time"

	livekitinfra "quwoquan_service/services/rtc-service/internal/infrastructure/livekit"
)

type TokenService struct {
	apiKey    string
	apiSecret string
}

func NewTokenService(apiKey, apiSecret string) *TokenService {
	return &TokenService{
		apiKey:    apiKey,
		apiSecret: apiSecret,
	}
}

func (s *TokenService) GenerateParticipantToken(roomName, participantIdentity string) (string, error) {
	return livekitinfra.GenerateAccessToken(s.apiKey, s.apiSecret, roomName, participantIdentity, 6*time.Hour)
}
