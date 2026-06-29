package impact

import "testing"

func TestPrimaryTextCircleActions(t *testing.T) {
	tests := []struct {
		name     string
		helpType string
		action   string
		count    int64
		want     string
	}{
		{name: "members", helpType: HelpRelationship, action: "establish_connection", count: 12, want: "一位用户等12人在这里建立了新连接"},
		{name: "posts", helpType: HelpCommunity, action: "start_discussion", count: 5, want: "一位用户等5人带起了新的讨论"},
		{name: "weekly active", helpType: HelpSpread, action: "active_participation", count: 3, want: "一位用户等3人最近参与了这里"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := PrimaryText(tt.helpType, tt.action, tt.count, ActorTA); got != tt.want {
				t.Fatalf("PrimaryText() = %q, want %q", got, tt.want)
			}
		})
	}
}

func TestPrimaryTextAuthorPerspective(t *testing.T) {
	if got := PrimaryText(HelpDecision, "", 7, ActorTA); got != "一位用户等7人通过TA的记录关注了相关对象" {
		t.Fatalf("TA perspective = %q", got)
	}
	if got := PrimaryText(HelpDecision, "", 7, ActorSelf); got != "一位用户等7人通过你的记录关注了相关对象" {
		t.Fatalf("self perspective = %q", got)
	}
}
