package runtimemedia

import "context"

const (
	DefaultGroupAvatarPublicSliceKey = "media/avatar/s/default/group/v1/default.png"
	DefaultGroupAvatarVersion        = 1
)

func BuildDefaultGroupAvatarURL(cdnBaseURL string) string {
	return BuildPublicMediaURL(cdnBaseURL, DefaultGroupAvatarPublicSliceKey, DefaultGroupAvatarVersion)
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
	return WriteDerivedMediaFile(localRoot, DefaultGroupAvatarPublicSliceKey, pngBytes)
}
