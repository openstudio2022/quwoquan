package local_contract

import (
	"testing"
	"time"

	bindingmodel "quwoquan_service/services/user-service/internal/domain/account/credential_binding/model"
)

func TestCredentialBindingLifecycleIsOneWay(t *testing.T) {
	t.Parallel()

	boundAt := time.Date(2026, 7, 20, 8, 0, 0, 0, time.UTC)
	bound, err := bindingmodel.Bind(bindingmodel.BindParams{
		ID:             "binding-1",
		OwnerID:        "account-1",
		CredentialType: bindingmodel.CredentialTypeWechat,
		CredentialKey:  "wechat-subject-ref",
		DisplayLabel:   "微信",
		EventID:        "event-bound-1",
		BoundAt:        boundAt,
	})
	if err != nil {
		t.Fatalf("创建凭证绑定: %v", err)
	}
	if !bound.Changed ||
		bound.Aggregate.Snapshot().Status != bindingmodel.StatusActive ||
		bound.Aggregate.Snapshot().Version != 1 ||
		len(bound.Events) != 1 ||
		bound.Events[0].Type != bindingmodel.CredentialBoundEvent {
		t.Fatalf("新绑定必须产生 active v1 与 CredentialBound: %+v", bound)
	}

	revokedAt := boundAt.Add(time.Hour)
	revoked, err := bound.Aggregate.Revoke("event-revoked-1", revokedAt)
	if err != nil {
		t.Fatalf("吊销凭证绑定: %v", err)
	}
	if !revoked.Changed ||
		revoked.Aggregate.Snapshot().Status != bindingmodel.StatusRevoked ||
		revoked.Aggregate.Snapshot().Version != 2 ||
		len(revoked.Events) != 1 ||
		revoked.Events[0].Type != bindingmodel.CredentialRevokedEvent {
		t.Fatalf("active 必须单向迁移到 revoked v2: %+v", revoked)
	}

	replayed, err := revoked.Aggregate.Revoke(
		"event-must-not-be-used",
		revokedAt.Add(time.Hour),
	)
	if err != nil {
		t.Fatalf("重复吊销: %v", err)
	}
	if replayed.Changed ||
		replayed.Aggregate.Snapshot().Status != bindingmodel.StatusRevoked ||
		replayed.Aggregate.Snapshot().Version != 2 ||
		len(replayed.Events) != 0 {
		t.Fatalf("revoked 必须保持终态且重复吊销为 no-op: %+v", replayed)
	}
}

func TestCredentialBindingRecoverableCredentialTypes(t *testing.T) {
	t.Parallel()

	recoverable := []bindingmodel.CredentialType{
		bindingmodel.CredentialTypePhone,
		bindingmodel.CredentialTypeCarrierPhone,
		bindingmodel.CredentialTypeWechat,
		bindingmodel.CredentialTypeAlipay,
		bindingmodel.CredentialTypeQQ,
		bindingmodel.CredentialTypeApple,
		bindingmodel.CredentialTypePasskey,
	}
	for _, credentialType := range recoverable {
		if !credentialType.Recoverable() {
			t.Fatalf("%s 应是可恢复凭证", credentialType)
		}
	}
	if bindingmodel.CredentialTypeAnonymousDevice.Recoverable() {
		t.Fatal("anonymous_device 不能作为账号恢复凭证")
	}
}
