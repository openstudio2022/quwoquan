package application

import (
	"github.com/google/uuid"
)

func generateID() string {
	// CallKit/CXCallUpdate 要求通话标识为 RFC 4122 UUID。CallSession 直接使用
	// 同一个 UUID，避免端云再维护一套 nativeCallId 映射。
	return uuid.NewString()
}
