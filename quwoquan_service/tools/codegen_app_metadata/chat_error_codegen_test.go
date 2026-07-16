package main

import (
	"path/filepath"
	"strings"
	"testing"
)

func TestChatErrorGeneration_matchesFormalDirectMessagingContract(t *testing.T) {
	metadataDir := initializeTestContractGraph(t)
	errorsPath := filepath.Join(metadataDir, "messages", "conversation", "errors.yaml")
	ef, err := readErrors(errorsPath)
	if err != nil {
		t.Fatalf("read errors: %v", err)
	}

	dartOut := renderChatErrorsDart(ef)
	goOut := renderChatErrorsGo(ef)

	for _, needle := range []string{
		"CHAT.USER.not_mutual",
		"CHAT.USER.greeting_required",
		"CHAT.USER.blocked",
		"互相关注后可进入正式私信",
		"请先打招呼，等对方回复后再进入正式私信",
		"Current relationship does not allow messaging",
	} {
		if !strings.Contains(dartOut, needle) {
			t.Fatalf("dart output missing %q", needle)
		}
	}

	for _, needle := range []string{
		"ErrNotMutual = errors.New(\"CHAT.USER.not_mutual\")",
		"ErrGreetingRequired = errors.New(\"CHAT.USER.greeting_required\")",
		"ErrBlocked = errors.New(\"CHAT.USER.blocked\")",
		"return rerrors.NewAppError(code, \"互相关注后可进入正式私信\", debugMessage)",
		"WithMetadata(\"forbidden\", 403)",
		"return rerrors.NewAppError(code, \"请先打招呼，等对方回复后再进入正式私信\", debugMessage)",
		"code, _ := rerrors.ParseCode(string(ErrNotMutual.Error()))",
	} {
		if !strings.Contains(goOut, needle) {
			t.Fatalf("go output missing %q", needle)
		}
	}
}
