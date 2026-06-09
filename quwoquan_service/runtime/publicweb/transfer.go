package publicweb

import "strings"

type TransferRequest struct {
	UserAgent    string
	TargetEntity string
	TargetID     string
	Token        string
}

type TransferDecision struct {
	Mode         string
	TargetEntity string
	TargetID     string
	Token        string
	LaunchMethod string
	FallbackURL  string
}

func ResolveTransfer(req TransferRequest) TransferDecision {
	ua := strings.ToLower(req.UserAgent)
	decision := TransferDecision{
		Mode:         "web_preview",
		TargetEntity: strings.TrimSpace(req.TargetEntity),
		TargetID:     strings.TrimSpace(req.TargetID),
		Token:        strings.TrimSpace(req.Token),
		LaunchMethod: "preview",
		FallbackURL:  "/download",
	}
	switch {
	case strings.Contains(ua, "micromessenger") && strings.Contains(ua, "android"):
		decision.Mode = "wechat_android_launch"
		decision.LaunchMethod = "wx-open-launch-app"
	case strings.Contains(ua, "micromessenger") && (strings.Contains(ua, "iphone") || strings.Contains(ua, "ipad")):
		decision.Mode = "wechat_ios_universal_link"
		decision.LaunchMethod = "universal_link"
	case strings.Contains(ua, "iphone") || strings.Contains(ua, "ipad"):
		decision.Mode = "ios_universal_link"
		decision.LaunchMethod = "universal_link"
	case strings.Contains(ua, "android") || strings.Contains(ua, "harmony") || strings.Contains(ua, "openharmony"):
		decision.Mode = "android_app_links"
		decision.LaunchMethod = "app_links"
	case strings.Contains(ua, "windows") || strings.Contains(ua, "macintosh") || strings.Contains(ua, "linux"):
		decision.Mode = "pc_preview"
		decision.LaunchMethod = "qr_install"
	}
	if decision.TargetEntity == "" || decision.TargetID == "" {
		decision.Mode = "fallback_home"
		decision.LaunchMethod = "home"
		decision.FallbackURL = "/"
	}
	return decision
}
