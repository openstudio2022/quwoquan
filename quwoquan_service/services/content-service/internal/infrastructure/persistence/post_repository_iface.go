package persistence

import "quwoquan_service/services/content-service/internal/application/ports"

// PostRepository remains the infrastructure-facing alias while the ownership of
// the application port lives in internal/application/ports.
type PostRepository = ports.PostRepository
