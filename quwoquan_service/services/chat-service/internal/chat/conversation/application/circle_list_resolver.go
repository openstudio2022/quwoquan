package application

import "context"

// ContactHomeCircleHit 是联系人 Tab「圈子」行的服务端投影。
type ContactHomeCircleHit struct {
	CircleID    string
	DisplayName string
	AvatarURL   string
	Subtitle    string
}

// CircleListResolver 从 circle-service 拉取用户可见圈子列表。
type CircleListResolver interface {
	ListCircles(ctx context.Context, userID string, limit int) ([]ContactHomeCircleHit, error)
}

type noopCircleListResolver struct{}

func (noopCircleListResolver) ListCircles(context.Context, string, int) ([]ContactHomeCircleHit, error) {
	return nil, nil
}
