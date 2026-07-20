package local_contract

import (
	"testing"
	"time"

	registrationmodel "quwoquan_service/services/user-service/internal/domain/account/device_registration/model"
)

func TestDeviceRegistrationOwnsDualEndpointsAndKeepsLifecycleAligned(t *testing.T) {
	t.Parallel()

	registeredAt := time.Date(2026, 7, 20, 9, 0, 0, 0, time.UTC)
	registration, err := registrationmodel.New(registrationmodel.RegisterParams{
		AccountID:    "account-1",
		DeviceID:     "device-1",
		AppVersion:   "1.0.0",
		RegisteredAt: registeredAt,
	})
	if err != nil {
		t.Fatalf("创建设备登记: %v", err)
	}

	apns, err := registration.UpsertEndpoint(registrationmodel.UpsertEndpointParams{
		AccountID:        "account-1",
		DeviceID:         "device-1",
		Kind:             registrationmodel.EndpointKindAPNSVoIP,
		TokenCiphertext:  "encrypted-apns-token",
		TokenFingerprint: fingerprint("a"),
		AppVersion:       "1.0.0",
		UpdatedAt:        registeredAt.Add(time.Minute),
	})
	if err != nil {
		t.Fatalf("upsert apns_voip: %v", err)
	}
	if !apns.Changed || apns.Aggregate.Snapshot().Version != 2 {
		t.Fatalf("首个 endpoint 必须推进父 version: %+v", apns)
	}

	replay, err := apns.Aggregate.UpsertEndpoint(
		registrationmodel.UpsertEndpointParams{
			AccountID:        "account-1",
			DeviceID:         "device-1",
			Kind:             registrationmodel.EndpointKindAPNSVoIP,
			TokenCiphertext:  "fresh-nonce-ciphertext",
			TokenFingerprint: fingerprint("a"),
			AppVersion:       "1.0.0",
			UpdatedAt:        registeredAt.Add(2 * time.Minute),
		},
	)
	if err != nil {
		t.Fatalf("重复 upsert: %v", err)
	}
	if replay.Changed || replay.Aggregate.Snapshot().Version != 2 {
		t.Fatalf("同 fingerprint + appVersion 必须自然幂等: %+v", replay)
	}

	fcm, err := replay.Aggregate.UpsertEndpoint(
		registrationmodel.UpsertEndpointParams{
			AccountID:        "account-1",
			DeviceID:         "device-1",
			Kind:             registrationmodel.EndpointKindFCM,
			TokenCiphertext:  "encrypted-fcm-token",
			TokenFingerprint: fingerprint("b"),
			AppVersion:       "1.0.0",
			UpdatedAt:        registeredAt.Add(3 * time.Minute),
		},
	)
	if err != nil {
		t.Fatalf("upsert fcm: %v", err)
	}
	if len(fcm.Aggregate.State().PushEndpoints) != 2 {
		t.Fatal("同设备必须可同时拥有 apns_voip 与 fcm")
	}

	removed, err := fcm.Aggregate.RemoveEndpoint(
		registrationmodel.EndpointKindAPNSVoIP,
		registeredAt.Add(4*time.Minute),
	)
	if err != nil {
		t.Fatalf("撤销 apns_voip: %v", err)
	}
	if removed.Aggregate.Snapshot().Status != registrationmodel.StatusActive {
		t.Fatal("仍有 active fcm 时父聚合必须保持 active")
	}
	revoked, _ := removed.Aggregate.EndpointByKind(
		registrationmodel.EndpointKindAPNSVoIP,
	)
	if revoked.Status != registrationmodel.StatusRevoked ||
		revoked.TokenCiphertext != "" ||
		revoked.TokenFingerprint != "" {
		t.Fatalf("revoked endpoint 必须清除 token material: %+v", revoked)
	}

	fcmEndpoint, _ := removed.Aggregate.EndpointByKind(registrationmodel.EndpointKindFCM)
	invalidated, err := removed.Aggregate.InvalidateEndpoint(
		fcmEndpoint.EndpointRef,
		"provider_unregistered",
		registeredAt.Add(5*time.Minute),
	)
	if err != nil {
		t.Fatalf("永久失效 fcm: %v", err)
	}
	if invalidated.Aggregate.Snapshot().Status != registrationmodel.StatusStale {
		t.Fatal("无 active 且存在 stale child 时父聚合必须为 stale")
	}
	stale, _ := invalidated.Aggregate.EndpointByKind(registrationmodel.EndpointKindFCM)
	if stale.Status != registrationmodel.StatusStale ||
		stale.TokenCiphertext != "" ||
		stale.TokenFingerprint != "" ||
		stale.InvalidationReason != "provider_unregistered" {
		t.Fatalf("stale endpoint 状态错误: %+v", stale)
	}
}

func fingerprint(value string) string {
	if value == "a" {
		return "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	}
	return "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
}
