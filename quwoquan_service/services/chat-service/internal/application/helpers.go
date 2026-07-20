package application

import (
	"crypto/rand"
	"encoding/hex"

	rterr "quwoquan_service/runtime/errors"
	generated "quwoquan_service/services/chat-service/internal/generated"
)

func generateID() string {
	b := make([]byte, 12)
	_, _ = rand.Read(b)
	return hex.EncodeToString(b)
}

func chatBlocked(debugMessage string) *rterr.AppError {
	return generated.AppErrorFromBlocked(debugMessage)
}

func chatNotMutual(debugMessage string) *rterr.AppError {
	return generated.AppErrorFromNotMutual(debugMessage)
}

func chatGreetingRequired(debugMessage string) *rterr.AppError {
	return generated.AppErrorFromGreetingRequired(debugMessage)
}

func chatGroupMemberNotMutual(debugMessage string) *rterr.AppError {
	return generated.AppErrorFromGroupMemberNotMutual(debugMessage)
}

func chatGroupMemberBlocked(debugMessage string) *rterr.AppError {
	return generated.AppErrorFromGroupMemberBlocked(debugMessage)
}

func chatGroupGovernanceForbidden(debugMessage string) *rterr.AppError {
	return generated.AppErrorFromGroupGovernanceForbidden(debugMessage)
}

func chatGroupFull(debugMessage string) *rterr.AppError {
	return generated.AppErrorFromGroupFull(debugMessage)
}

func chatConversationDissolved(debugMessage string) *rterr.AppError {
	return generated.AppErrorFromConversationDissolved(debugMessage)
}

func chatOwnerMustTransferBeforeLeave(debugMessage string) *rterr.AppError {
	return generated.AppErrorFromGroupOwnerMustTransferBeforeLeave(debugMessage)
}

// chatConversationNotFoundForNonMember 对非成员统一返回 not_found，
// 避免通过成员操作探测会话存在性（信息隐藏）。
func chatConversationNotFoundForNonMember(debugMessage string) *rterr.AppError {
	return generated.AppErrorFromConversationNotFound(debugMessage)
}
