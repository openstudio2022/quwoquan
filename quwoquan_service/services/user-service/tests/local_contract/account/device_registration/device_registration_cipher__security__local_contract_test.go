package local_contract

import (
	"bytes"
	"context"
	"encoding/base64"
	"testing"

	registrationmodel "quwoquan_service/services/user-service/internal/account/device_registration/domain/model"
	registrationports "quwoquan_service/services/user-service/internal/account/device_registration/domain/ports"
	registrationpersistence "quwoquan_service/services/user-service/internal/account/device_registration/infrastructure/persistence"
)

func TestAESGCMDeviceTokenCipherNeverEmitsPlaintextAndUsesFreshNonce(t *testing.T) {
	t.Parallel()

	tokenCipher, err := registrationpersistence.NewAESGCMTokenCipher(
		bytes.Repeat([]byte{0x2a}, 32),
	)
	if err != nil {
		t.Fatalf("创建 AES-GCM token cipher: %v", err)
	}
	plaintext := []byte("sensitive-push-token")
	scope := registrationports.TokenCipherScope{
		AccountID: "account-1",
		DeviceID:  "device-1",
		Kind:      registrationmodel.EndpointKindAPNSVoIP,
	}
	first, firstFingerprint, err := tokenCipher.ProtectPushToken(
		context.Background(),
		plaintext,
		scope,
	)
	if err != nil {
		t.Fatalf("首次加密: %v", err)
	}
	second, secondFingerprint, err := tokenCipher.ProtectPushToken(
		context.Background(),
		plaintext,
		scope,
	)
	if err != nil {
		t.Fatalf("第二次加密: %v", err)
	}
	if first == second {
		t.Fatal("AES-GCM 每次加密必须使用新 nonce")
	}
	if firstFingerprint == "" || firstFingerprint != secondFingerprint {
		t.Fatal("同一 push token 的 keyed fingerprint 必须稳定且非空")
	}
	if firstFingerprint == string(plaintext) {
		t.Fatal("fingerprint 不得等于 push token 明文")
	}
	for _, ciphertext := range []string{first, second} {
		decoded, decodeErr := base64.RawURLEncoding.DecodeString(ciphertext)
		if decodeErr != nil {
			t.Fatalf("密文必须是可传输的 raw URL base64: %v", decodeErr)
		}
		if bytes.Contains(decoded, plaintext) ||
			bytes.Contains([]byte(ciphertext), plaintext) {
			t.Fatal("AES-GCM 输出不得包含 push token 明文")
		}
	}
	revealed, err := tokenCipher.RevealPushToken(
		context.Background(),
		first,
		scope,
	)
	if err != nil || !bytes.Equal(revealed, plaintext) {
		t.Fatalf("同一 AAD scope 必须可解密: plaintext=%q err=%v", revealed, err)
	}
	wrongScope := scope
	wrongScope.Kind = registrationmodel.EndpointKindFCM
	if _, err := tokenCipher.RevealPushToken(
		context.Background(),
		first,
		wrongScope,
	); err == nil {
		t.Fatal("endpointKind 不同必须导致 AES-GCM AAD 认证失败")
	}
}
