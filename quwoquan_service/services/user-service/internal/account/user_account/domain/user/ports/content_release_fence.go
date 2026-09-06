package ports

import "context"

// UnavailableContentReleaseFenceReader keeps the production composition seam
// fail-closed until the cross-service Content active-tuple adapter is wired.
type UnavailableContentReleaseFenceReader struct{}

func (UnavailableContentReleaseFenceReader) ActiveContentReleaseFence(context.Context) (ContentReleaseFence, bool, error) {
	return ContentReleaseFence{}, false, nil
}
