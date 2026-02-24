# content-service

Run locally:

```bash
go run ./services/content-service/cmd/api
```

Default address: `:18080` (override with `CONTENT_SERVICE_ADDR`).

Available endpoints:

- `GET /healthz`
- `GET /v1/content/feed`
- `GET /v1/orch/discovery/feed` (alias for app integration)
- `GET /v1/content/posts/{postId}`

Codegen commands:

- `make -C quwoquan_service codegen-content-service` (generate domain models + route contracts)
- `make -C quwoquan_service codegen-app` (generate app metadata contracts)
