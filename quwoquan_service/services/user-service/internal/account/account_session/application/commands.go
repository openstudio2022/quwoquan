package account_session

import "time"

// IssueCommand 是登录编排交给 AccountSession 的瞬时签发输入。
// RefreshToken 只允许在本次 application 调用期间存在，不得记录或持久化。
type IssueCommand struct {
	AccountID             string
	DeviceID              string
	AuthenticationSubject string
	IdentityOrigin        string
	RefreshToken          []byte
	ExpiresAt             time.Time
}

// RotateCommand 持有本次轮换所需的两个瞬时明文 token。调用 Facet 后，
// application 只把各自的 SHA-256 指纹传给对象 Store。
type RotateCommand struct {
	CurrentRefreshToken []byte
	NextRefreshToken    []byte
	ExpiresAt           time.Time
}

// LogoutCommand 精确吊销 refresh token 对应会话；未知或已吊销 token 为 no-op。
type LogoutCommand struct {
	RefreshToken []byte
}

// RevokeCommand 吊销账号的全部可用会话，供安全事件或全设备登出使用。
type RevokeCommand struct {
	AccountID string
	Reason    string
}

// SessionResult 是签发或轮换后的脱敏应用结果，不包含 token 明文或 hash。
type SessionResult struct {
	SessionID string
	AccountID string
	DeviceID  string
	LineageID string
	ExpiresAt time.Time
}
