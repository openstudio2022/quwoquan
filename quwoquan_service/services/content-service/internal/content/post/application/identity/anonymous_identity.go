package identity

import "strings"

const (
	AnonymousFallbackOwnerID      = "uo_01_ad_0000_00000000000000000000000000"
	AnonymousFallbackSubAccountID = "us_01_0000_00000000000000000000000000"
)

func NormalizeAnonymousSubAccountID(subAccountID string) string {
	trimmed := strings.TrimSpace(subAccountID)
	if trimmed == "" {
		return AnonymousFallbackSubAccountID
	}
	return trimmed
}

func IsAnonymousFallbackSubAccountID(subAccountID string) bool {
	return NormalizeAnonymousSubAccountID(subAccountID) == AnonymousFallbackSubAccountID
}

// deviceActorKeyPrefix 命名空间化派生设备标识，避免与账号 subAccountID 维度冲突。
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
	return AnonymousFallbackSubAccountID
}
