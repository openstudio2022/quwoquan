package ports

import "context"

// GatheringParticipationStatus 是 Circle owner 对「某 persona 在某 Gathering 的
// 当前参与状态」的最小断言投影。Content 不复制名单、申请答案或私密事实。
type GatheringParticipationStatus struct {
	GatheringID        string
	PersonaID          string
	LifecycleStatus    string
	ParticipationState string
}

// GatheringParticipationReader 是 Content 侧唯一的 Gathering 参与状态防腐端口。
// Post 携带 gatheringRef（共同经历回流引用）发布前，application 必须经本端口向
// Circle owner 确认作者持有 active Participation；端口未装配或依赖失败一律
// fail-closed，禁止本地合成通过。
type GatheringParticipationReader interface {
	GetParticipationStatus(
		ctx context.Context,
		gatheringID string,
		personaID string,
	) (GatheringParticipationStatus, error)
}
