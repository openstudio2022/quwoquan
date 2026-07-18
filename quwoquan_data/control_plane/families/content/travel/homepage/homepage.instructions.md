# Travel Homepage Family

This reusable family produces one entity homepage per selected target.  It has
no province, date, entity, batch, or execution instance values.

Use the single content facade:

```bash
python3 quwoquan_data/scripts/cli.py task execute \
  --execution-id YYYYMMDD--travel-homepage-coverage--cn-scope--canary-001 \
  --milestone canary --province <province> --discovery <coverage-path>
```

The same `executionId` resumes only immutable matching input.  A retry uses a
new sequence and `--retry-of <executionId>`. `task preflight` accepts only the
external `QWQ_CURSOR_API_KEY_FILE` source; no token, fingerprint, or token
fragment may enter a command log or execution manifest.
