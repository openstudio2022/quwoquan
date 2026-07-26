package model

// IsMissedFor 判断该通话对 userID 而言是否为「未接来电」：
// 通话已结束，结束原因为无人接听/超时/被取消，且 userID 是被叫方（非发起人）。
func (c *CallSession) IsMissedFor(userID string) bool {
	if c == nil || c.Status != StatusEnded {
		return false
	}
	if c.InitiatorID == userID {
		return false
	}
	switch c.EndReason {
	case EndReasonNoAnswer, EndReasonTimeout, EndReasonCancelled:
		return true
	default:
		return false
	}
}
