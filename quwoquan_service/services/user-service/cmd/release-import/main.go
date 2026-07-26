// Command release-import imports immutable-release public creators into user-service.
package main

import releaseimport "quwoquan_service/services/user-service/internal/account/user_account/infrastructure/releaseimport"

func main() {
	releaseimport.Run()
}
