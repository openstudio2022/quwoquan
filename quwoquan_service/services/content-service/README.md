# content-service

Run locally:

```bash
go run ./services/content-service/cmd/api
```

Default address: `:18080` (override with `CONTENT_SERVICE_ADDR`).

Available endpoints:

- `GET /healthz`
- `GET /content/feed`
- `GET /content/posts/{postId}`

Codegen commands:

- `make -C quwoquan_service codegen-content-service` (generate domain models + route contracts)
- `make -C quwoquan_service codegen-app` (generate app metadata contracts)
