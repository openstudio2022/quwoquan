package local_contract

import (
	"context"
	"testing"

	rtredis "quwoquan_service/runtime/redis"
	usercache "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/cache"
)

// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-001
func TestClosedAccountCacheReleasesHashedOtpAdmission(t *testing.T) {
	t.Parallel()
	ctx := context.Background()
	client := rtredis.NewMemoryClient()
	otp := usercache.NewOtpCodeCache(client)
	closed := usercache.NewClosedAccountCache(client)
	const phone = "+8618038139016"

	first, err := otp.AllowSend(ctx, phone, "otp-key-close-0000000000000001", "login:close-phone")
	if err != nil || !first.Allowed {
		t.Fatalf("first admission = %+v, %v", first, err)
	}
	limited, err := otp.AllowSend(ctx, phone, "otp-key-close-0000000000000002", "login:close-phone")
	if err != nil || limited.Allowed {
		t.Fatalf("cooldown before close = %+v, %v", limited, err)
	}

	if err := closed.InvalidateClosedAccount(ctx, "acct_close_otp", []string{phone}); err != nil {
		t.Fatalf("invalidate closed account cache: %v", err)
	}

	released, err := otp.AllowSend(ctx, phone, "otp-key-close-0000000000000003", "login:close-phone")
	if err != nil || !released.Allowed {
		t.Fatalf("phone must send OTP after close cache invalidation: %+v, %v", released, err)
	}
}
