package livekit

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"strings"
	"time"
)

// VideoGrant defines LiveKit room permissions embedded in the JWT.
type VideoGrant struct {
	Room             string `json:"room,omitempty"`
	RoomJoin         bool   `json:"roomJoin,omitempty"`
	RoomCreate       bool   `json:"roomCreate,omitempty"`
	RoomAdmin        bool   `json:"roomAdmin,omitempty"`
	CanPublish       bool   `json:"canPublish,omitempty"`
	CanSubscribe     bool   `json:"canSubscribe,omitempty"`
	CanPublishData   bool   `json:"canPublishData,omitempty"`
}

type jwtHeader struct {
	Alg string `json:"alg"`
	Typ string `json:"typ"`
}

type jwtClaims struct {
	ISS   string      `json:"iss"`
	SUB   string      `json:"sub"`
	IAT   int64       `json:"iat"`
	NBF   int64       `json:"nbf"`
	EXP   int64       `json:"exp"`
	Video *VideoGrant `json:"video,omitempty"`
}

// GenerateAccessToken creates a LiveKit-compatible JWT for a participant.
func GenerateAccessToken(apiKey, apiSecret, roomName, participantIdentity string, ttl time.Duration) (string, error) {
	if ttl <= 0 {
		ttl = 6 * time.Hour
	}

	now := time.Now()
	claims := jwtClaims{
		ISS: apiKey,
		SUB: participantIdentity,
		IAT: now.Unix(),
		NBF: now.Unix(),
		EXP: now.Add(ttl).Unix(),
		Video: &VideoGrant{
			Room:           roomName,
			RoomJoin:       true,
			CanPublish:     true,
			CanSubscribe:   true,
			CanPublishData: true,
		},
	}
	return signJWT(claims, apiSecret)
}

// GenerateAdminToken creates a LiveKit-compatible JWT with room admin privileges.
func GenerateAdminToken(apiKey, apiSecret, roomName string) (string, error) {
	now := time.Now()
	claims := jwtClaims{
		ISS: apiKey,
		IAT: now.Unix(),
		NBF: now.Unix(),
		EXP: now.Add(10 * time.Minute).Unix(),
		Video: &VideoGrant{
			RoomCreate: true,
			RoomAdmin:  true,
			Room:       roomName,
		},
	}
	return signJWT(claims, apiSecret)
}

func signJWT(claims jwtClaims, secret string) (string, error) {
	header := jwtHeader{Alg: "HS256", Typ: "JWT"}

	headerJSON, err := json.Marshal(header)
	if err != nil {
		return "", fmt.Errorf("marshal header: %w", err)
	}
	claimsJSON, err := json.Marshal(claims)
	if err != nil {
		return "", fmt.Errorf("marshal claims: %w", err)
	}

	headerEncoded := base64URLEncode(headerJSON)
	claimsEncoded := base64URLEncode(claimsJSON)
	signingInput := headerEncoded + "." + claimsEncoded

	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write([]byte(signingInput))
	signature := base64URLEncode(mac.Sum(nil))

	return signingInput + "." + signature, nil
}

func base64URLEncode(data []byte) string {
	s := base64.StdEncoding.EncodeToString(data)
	s = strings.TrimRight(s, "=")
	s = strings.ReplaceAll(s, "+", "-")
	s = strings.ReplaceAll(s, "/", "_")
	return s
}
