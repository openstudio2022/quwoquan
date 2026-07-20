package main

import (
	"strings"
	"testing"
)

func TestUserErrorGeneration_aggregatesAllUserErrorMetadata(t *testing.T) {
	metadataDir := initializeTestContractGraph(t)
	ef, err := readUserDomainErrors(metadataDir)
	if err != nil {
		t.Fatalf("read user errors: %v", err)
	}

	dartOut := renderUserErrorsDart(ef)
	goOut := renderUserErrorsGo(ef)

	// invite_record 对象已随邀请能力退役从 metadata 删除，USER.INVITE.* 不再生成。
	for _, needle := range []string{
		"USER.USER.not_found",
		"USER.GREETING.already_contact",
		"USER.CONTACT.rate_limited",
		"USER.AUTH.token_expired",
		"USER.SUB_ACCOUNT.not_found",
		"USER.SUB_ACCOUNT.retired_guard",
		"USER.SUB_ACCOUNT.handle_taken",
		"USER.SETTING.invalid_call_ringtone",
		"已互相关注，可直接进入正式私信",
	} {
		if !strings.Contains(dartOut, needle) {
			t.Fatalf("dart output missing %q", needle)
		}
	}

	for _, retired := range []string{"USER.INVITE."} {
		if strings.Contains(dartOut, retired) {
			t.Fatalf("dart output must not resurrect retired error namespace %q", retired)
		}
	}

	for _, needle := range []string{
		"ErrGreetingAlreadyContact = errors.New(\"USER.GREETING.already_contact\")",
		"ErrContactDiscoveryRateLimited = errors.New(\"USER.CONTACT.rate_limited\")",
		"ErrTokenExpired = errors.New(\"USER.AUTH.token_expired\")",
		"ErrInvalidCallRingtone = errors.New(\"USER.SETTING.invalid_call_ringtone\")",
		"ErrRetiredSubAccountGuard = errors.New(\"USER.SUB_ACCOUNT.retired_guard\")",
		"ErrSubAccountHandleTaken = errors.New(\"USER.SUB_ACCOUNT.handle_taken\")",
	} {
		if !strings.Contains(goOut, needle) {
			t.Fatalf("go output missing %q", needle)
		}
	}
}
