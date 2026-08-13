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
		"USER.PERSONA.not_found",
		"USER.PERSONA.retired_guard",
		"USER.PERSONA.handle_taken",
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
		"ErrRetiredPersonaGuard = errors.New(\"USER.PERSONA.retired_guard\")",
		"ErrPersonaHandleTaken = errors.New(\"USER.PERSONA.handle_taken\")",
	} {
		if !strings.Contains(goOut, needle) {
			t.Fatalf("go output missing %q", needle)
		}
	}
}
