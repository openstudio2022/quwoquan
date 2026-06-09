package main

import (
	"path/filepath"
	"strings"
	"testing"
)

func TestUserGreetingErrorGeneration_matchesFormalDirectMessagingContract(t *testing.T) {
	errorsPath := filepath.Join("..", "..", "contracts", "metadata", "user", "greeting_request", "errors.yaml")
	ef, err := readErrors(errorsPath)
	if err != nil {
		t.Fatalf("read errors: %v", err)
	}

	goOut := renderUserGreetingErrorsGo(ef)

	for _, needle := range []string{
		"ErrGreetingAlreadyContact = errors.New(\"USER.GREETING.already_contact\")",
		"ErrGreetingTargetBlockedSender = errors.New(\"USER.GREETING.target_blocked_sender\")",
		"code, _ := rerrors.ParseCode(string(ErrGreetingAlreadyContact.Error()))",
		"return rerrors.NewAppError(code, \"已互相关注，可直接进入正式私信\", debugMessage)",
		"return rerrors.NewAppError(code, \"发送失败，对方不接收你的打招呼\", debugMessage)",
	} {
		if !strings.Contains(goOut, needle) {
			t.Fatalf("go output missing %q", needle)
		}
	}
}
