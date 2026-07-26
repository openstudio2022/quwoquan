package application

import "context"

// SocialContactSeed 是社交关系聚合的原始条目。
// MemberService 会在此基础上补 profile 快照并生成联系人行。
type SocialContactSeed struct {
	UserID          string
	DisplayName     string
	AvatarURL       string
	Bio             string
	MetFrom         string
	LastInteraction string
	RelationState   string
	Source          string
	IsStarred       bool
}

type SocialContactPage struct {
	Items      []SocialContactSeed
	NextCursor string
}

// SocialContactResolver 负责从 user-service 聚合 follow / discovery 等社交来源。
type SocialContactResolver interface {
	ListContacts(ctx context.Context, userID string, limit int) ([]SocialContactSeed, error)
	ListContactPage(
		ctx context.Context,
		userID string,
		limit int,
		cursor string,
	) (SocialContactPage, error)
}

type noopSocialContactResolver struct{}

func (noopSocialContactResolver) ListContacts(context.Context, string, int) ([]SocialContactSeed, error) {
	return nil, nil
}

func (noopSocialContactResolver) ListContactPage(
	context.Context,
	string,
	int,
	string,
) (SocialContactPage, error) {
	return SocialContactPage{}, nil
}
