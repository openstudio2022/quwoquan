package publicweb

import "testing"

func TestResolveTransferRoutesByUserAgent(t *testing.T) {
	cases := []struct {
		name   string
		ua     string
		mode   string
		method string
	}{
		{
			name:   "wechat android",
			ua:     "Mozilla/5.0 Linux Android MicroMessenger",
			mode:   "wechat_android_launch",
			method: "wx-open-launch-app",
		},
		{
			name:   "wechat ios",
			ua:     "Mozilla/5.0 iPhone MicroMessenger",
			mode:   "wechat_ios_universal_link",
			method: "universal_link",
		},
		{
			name:   "pc",
			ua:     "Mozilla/5.0 Macintosh",
			mode:   "pc_preview",
			method: "qr_install",
		},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			got := ResolveTransfer(TransferRequest{
				UserAgent:    tc.ua,
				TargetEntity: "post",
				TargetID:     "post_1",
			})
			if got.Mode != tc.mode || got.LaunchMethod != tc.method {
				t.Fatalf("decision=%#v", got)
			}
		})
	}
}

func TestResolveTransferFallsBackWhenTargetMissing(t *testing.T) {
	got := ResolveTransfer(TransferRequest{UserAgent: "Mozilla/5.0 iPhone"})
	if got.Mode != "fallback_home" || got.FallbackURL != "/" {
		t.Fatalf("decision=%#v", got)
	}
}
