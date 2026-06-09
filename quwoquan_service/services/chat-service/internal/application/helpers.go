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
