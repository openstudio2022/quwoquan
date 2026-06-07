package application

import (
	"crypto/rand"
	"encoding/hex"

	rterr "quwoquan_service/runtime/errors"
)

func generateID() string {
	b := make([]byte, 12)
	_, _ = rand.Read(b)
	return hex.EncodeToString(b)
}

func chatForbidden(reason, userMessage, debugMessage string) *rterr.AppError {
	return rterr.NewAppError(
		rterr.NewCode(rterr.ModuleChat, rterr.KindUser, reason),
		userMessage,
		debugMessage,
	)
}

func chatBlocked(debugMessage string) *rterr.AppError {
	return chatForbidden("blocked", "当前状态不能继续发送消息", debugMessage)
}

func chatNotMutual(debugMessage string) *rterr.AppError {
	return chatForbidden("not_mutual", "互相关注后可直接私信", debugMessage)
}

func chatGreetingRequired(debugMessage string) *rterr.AppError {
	return chatForbidden("greeting_required", "请先打招呼，等对方回复后再进入私信", debugMessage)
}
