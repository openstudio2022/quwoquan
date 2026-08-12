// Package testobject builds deterministic, test-only User objects.
package testobject

import "fmt"

// User is the smallest shared shape required by User API integration tests.
type User struct {
	UserID              string
	DisplayName         string
	AvatarObjectKey     string
	BackgroundObjectKey string
	Bio                 string
	PersonaRefs         []string
}

// BuildUserPool replaces the former 1.5 MiB JSON dump. Named examples remain
// stable; additional boundary rows are derived from the fixed index.
func BuildUserPool(count int) []User {
	if count < 7 {
		count = 7
	}
	named := []struct{ id, name string }{
		{"fixture_user_current", "新同学"},
		{"fixture_user_photo", "契约摄影师"},
		{"fixture_user_travel", "契约旅行家"},
		{"fixture_user_article", "契约撰稿人"},
		{"fixture_user_friend", "契约好友"},
		{"fixture_user_weekend_1", "契约同伴一"},
		{"fixture_user_weekend_2", "契约同伴二"},
	}
	users := make([]User, 0, count)
	for index := 0; index < count; index++ {
		id := fmt.Sprintf("fixture_user_generated_%03d", index+1)
		name := fmt.Sprintf("固定种子用户 %03d", index+1)
		if index < len(named) {
			id, name = named[index].id, named[index].name
		}
		users = append(users, User{
			UserID:              id,
			DisplayName:         name,
			AvatarObjectKey:     "media/avatar/s/archived-avatar/user/" + id + "/v1/avatar.png",
			BackgroundObjectKey: "media/background/s/archived-avatar/user/" + id + "/v1/background.png",
			Bio:                 "固定 seed 用户档案",
			PersonaRefs:         []string{"fixture_persona_" + id},
		})
	}
	return users
}
