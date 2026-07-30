package identity

import "strings"

const (
	// Frozen reserved identities already persisted in content/recommendation
	// state. The `01` bytes are part of the sole canonical ID, not a version fork.
	AnonymousFallbackOwnerID   = "uo_01_ad_0000_00000000000000000000000000"
	AnonymousFallbackPersonaID = "us_01_0000_00000000000000000000000000"
)

func NormalizeAnonymousPersonaID(personaID string) string {
	trimmed := strings.TrimSpace(personaID)
	if trimmed == "" {
		return AnonymousFallbackPersonaID
	}
	return trimmed
}

func IsAnonymousFallbackPersonaID(personaID string) bool {
	return NormalizeAnonymousPersonaID(personaID) == AnonymousFallbackPersonaID
}

// RankedFeedWindowSubjectID returns the private storage/quota subject for an
// immutable recommendation window. Named personas and verified device actors
// share the canonical actor quota across their sessions. Identity-less public
// traffic must instead be isolated by session: using the global anonymous
// fallback actor here would let one visitor's ninth window evict another
// visitor's still-valid continuation.
func RankedFeedWindowSubjectID(actorID, sessionID string) string {
	actorID = NormalizeAnonymousPersonaID(actorID)
	if actorID != AnonymousFallbackPersonaID {
		return "actor\x00" + actorID
	}
	sessionID = strings.TrimSpace(sessionID)
	if sessionID == "" {
		return ""
	}
	return "anonymous-session\x00" + sessionID
}

// deviceActorKeyPrefix 命名空间化派生设备标识，避免与账号 personaID 维度冲突。
// 注意：不得含 ':'，否则会破坏 shareActorID 的 ':' 分段解析（分享 key 形如
// "direct:<actorKey>"）。真实账号 ID 不会以此前缀开头，故键空间天然不相交。
const DeviceActorKeyPrefix = "devactor_"

// ShareActorKey 解析分享去重与计数维度键：
//   - 真实账号优先用 userID（账号维度）；
//   - 否则用隐私安全的派生设备标识 deviceActorID（设备维度，命名空间化）；
//   - 两者都为空时回落到单一匿名常量（无设备标识的极端兜底）。
//
// 账号维度与设备维度因键空间不相交而天然独立计数，登录后不并账、不迁移。
func ShareActorKey(userID, deviceActorID string) string {
	if u := strings.TrimSpace(userID); u != "" {
		return u
	}
	if d := strings.TrimSpace(deviceActorID); d != "" {
		return DeviceActorKeyPrefix + d
	}
	return AnonymousFallbackPersonaID
}
