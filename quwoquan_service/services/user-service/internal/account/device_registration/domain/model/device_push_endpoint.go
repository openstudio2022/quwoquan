package model

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"strings"
	"time"
)

const maxCiphertextLength = 8192

type EndpointKind string

const (
	EndpointKindAPNSVoIP EndpointKind = "apns_voip"
	EndpointKindFCM      EndpointKind = "fcm"
)

func (kind EndpointKind) Valid() bool {
	switch kind {
	case EndpointKindAPNSVoIP, EndpointKindFCM:
		return true
	default:
		return false
	}
}

// EndpointState 是 owned entity 的持久化形态，禁止增加 JSON tag 或直接返回 transport。
type EndpointState struct {
	EndpointRef        string
	AccountID          string
	DeviceID           string
	Kind               EndpointKind
	TokenCiphertext    string
	TokenFingerprint   string
	Status             Status
	InvalidationReason string
	Version            int64
	CreatedAt          time.Time
	UpdatedAt          time.Time
}

type UpsertEndpointParams struct {
	AccountID        string
	DeviceID         string
	Kind             EndpointKind
	TokenCiphertext  string
	TokenFingerprint string
	AppVersion       string
	UpdatedAt        time.Time
}

func normalizeUpsertEndpointParams(params UpsertEndpointParams) UpsertEndpointParams {
	params.AccountID = strings.TrimSpace(params.AccountID)
	params.DeviceID = strings.TrimSpace(params.DeviceID)
	params.Kind = EndpointKind(strings.TrimSpace(string(params.Kind)))
	params.TokenCiphertext = strings.TrimSpace(params.TokenCiphertext)
	params.TokenFingerprint = strings.TrimSpace(params.TokenFingerprint)
	params.AppVersion = strings.TrimSpace(params.AppVersion)
	params.UpdatedAt = params.UpdatedAt.UTC()
	return params
}

func validateUpsertEndpointParams(params UpsertEndpointParams) error {
	if invalidText(params.AccountID, maxAccountIDLength) ||
		invalidText(params.DeviceID, maxDeviceIDLength) ||
		!params.Kind.Valid() ||
		invalidOptionalText(params.AppVersion, maxAppVersionLength) ||
		params.UpdatedAt.IsZero() ||
		!validTokenMaterial(params.TokenCiphertext, params.TokenFingerprint, true) {
		return fmt.Errorf("%w: endpoint upsert input is incomplete or malformed", ErrInvalidEndpoint)
	}
	return nil
}

func validateEndpointState(endpoint EndpointState, accountID, deviceID string) error {
	if endpoint.AccountID != accountID ||
		endpoint.DeviceID != deviceID ||
		endpoint.EndpointRef != canonicalEndpointRef(accountID, deviceID, endpoint.Kind) ||
		!endpoint.Kind.Valid() ||
		!endpoint.Status.Valid() ||
		endpoint.Version < 1 ||
		endpoint.CreatedAt.IsZero() ||
		endpoint.UpdatedAt.IsZero() ||
		endpoint.UpdatedAt.Before(endpoint.CreatedAt) {
		return fmt.Errorf("%w: persisted endpoint state is malformed", ErrInvalidEndpoint)
	}
	switch endpoint.Status {
	case StatusActive:
		if !validTokenMaterial(endpoint.TokenCiphertext, endpoint.TokenFingerprint, true) ||
			endpoint.InvalidationReason != "" {
			return fmt.Errorf("%w: active endpoint material is malformed", ErrInvalidEndpoint)
		}
	case StatusRevoked:
		if !validTokenMaterial(endpoint.TokenCiphertext, endpoint.TokenFingerprint, false) ||
			endpoint.InvalidationReason != "" {
			return fmt.Errorf("%w: revoked endpoint retained secret state", ErrInvalidEndpoint)
		}
	case StatusStale:
		if !validTokenMaterial(endpoint.TokenCiphertext, endpoint.TokenFingerprint, false) ||
			invalidText(endpoint.InvalidationReason, maxInvalidationReasonLength) {
			return fmt.Errorf("%w: stale endpoint state is malformed", ErrInvalidEndpoint)
		}
	}
	return nil
}

func validTokenMaterial(ciphertext, fingerprint string, required bool) bool {
	if ciphertext == "" || fingerprint == "" {
		return !required && ciphertext == "" && fingerprint == ""
	}
	if !required ||
		len(ciphertext) > maxCiphertextLength ||
		strings.TrimSpace(ciphertext) != ciphertext ||
		len(fingerprint) != sha256.Size*2 ||
		strings.ToLower(fingerprint) != fingerprint {
		return false
	}
	_, err := hex.DecodeString(fingerprint)
	return err == nil
}

func canonicalEndpointRef(accountID, deviceID string, kind EndpointKind) string {
	return canonicalDigest(accountID, deviceID, string(kind))
}

func canonicalDigest(parts ...string) string {
	sum := sha256.Sum256([]byte(strings.Join(parts, "\x00")))
	return hex.EncodeToString(sum[:])
}

func endpointIndexByKind(endpoints []EndpointState, kind EndpointKind) int {
	for index := range endpoints {
		if endpoints[index].Kind == kind {
			return index
		}
	}
	return -1
}

func endpointIndexByRef(endpoints []EndpointState, endpointRef string) int {
	for index := range endpoints {
		if endpoints[index].EndpointRef == endpointRef {
			return index
		}
	}
	return -1
}

func sortEndpoints(endpoints []EndpointState) {
	if len(endpoints) == 2 && endpoints[0].Kind > endpoints[1].Kind {
		endpoints[0], endpoints[1] = endpoints[1], endpoints[0]
	}
}
