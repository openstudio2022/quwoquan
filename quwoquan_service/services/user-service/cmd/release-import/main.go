// Command release-import imports immutable-release public creators into user-service.
package main

import releaseimport "quwoquan_service/services/user-service/internal/profile_projection/creator_runtime_profile/infrastructure/releaseimport"

func main() {
	releaseimport.Run(newCreatorPersonaMaterializer)
}
