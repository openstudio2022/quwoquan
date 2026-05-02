package runtimemedia

import "context"

const (
	DefaultGroupAvatarObjectKey = "media/avatar/default/group/v1/default.png"
	DefaultGroupAvatarVersion   = 1
)

func BuildDefaultGroupAvatarURL(cdnBaseURL string) string {
	return BuildPublicMediaURL(cdnBaseURL, DefaultGroupAvatarObjectKey, DefaultGroupAvatarVersion)
}

func EnsureDefaultGroupAvatarFile(localRoot string) error {
	pngBytes, err := RenderGroupAvatarPNG(
		context.Background(),
		nil,
		[]string{"", ""},
		groupAvatarCanvasSize,
	)
	if err != nil {
		return err
	}
	return WriteDerivedMediaFile(localRoot, DefaultGroupAvatarObjectKey, pngBytes)
}
