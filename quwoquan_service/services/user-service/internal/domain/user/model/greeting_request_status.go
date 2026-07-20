package model

// GreetingRequest 状态值必须与 metadata
// _shared/types.yaml#GreetingRequestStatus 保持单轨。
const (
	GreetingStatusPending   = "pending"
	GreetingStatusReplied   = "replied"
	GreetingStatusIgnored   = "ignored"
	GreetingStatusBlocked   = "blocked"
	GreetingStatusCancelled = "cancelled"
	GreetingStatusExpired   = "expired"
)

// IsGreetingRequestStatus 判断输入是否属于 canonical
// GreetingRequestStatus 闭集。
func IsGreetingRequestStatus(value string) bool {
	switch value {
	case GreetingStatusPending,
		GreetingStatusReplied,
		GreetingStatusIgnored,
		GreetingStatusBlocked,
		GreetingStatusCancelled,
		GreetingStatusExpired:
		return true
	default:
		return false
	}
}
