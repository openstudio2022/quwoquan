package releaseimport

import (
	"fmt"
	"strings"
)

// BindPostAuthorSnapshots projects the canonical creator profile display name
// and avatar onto each imported Post. Avatar delivery uses its own typed
// topology and never reuses the image-delivery endpoint.
func BindPostAuthorSnapshots(
	posts []PostDoc,
	creators map[string]CreatorAuthorSnapshot,
) error {
	for index := range posts {
		post := &posts[index]
		authorID := strings.TrimSpace(post.AuthorID)
		creator, exists := creators[authorID]
		if !exists || creator.DisplayName == "" {
			return fmt.Errorf("%s: canonical creator snapshot is unavailable for authorId %q", post.PostRef, authorID)
		}
		post.AuthorDisplayName = creator.DisplayName
		post.AuthorAvatarURL = creator.AvatarURL
	}
	return nil
}
