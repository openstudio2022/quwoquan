# Design: Privacy & UI Config Contract

## Privacy Policy

```
privacy.yaml → codegen → ContentPrivacyPolicy.sanitizeForLog()
```

Fields with `SECRET` or `PII` classification get mask/truncate/drop treatment when logging.
Driven entirely from metadata — no hardcoded field names in business logic.

## UI Configuration

```
ui_config.yaml → codegen → ContentUIConfig (Dart const)
```

`ContentUIConfig.discoveryTabs` drives tab count, order, layout type, and content type.
`discovery_page.dart` reads tab config at runtime — adding/reordering tabs requires only a YAML edit + codegen.

Feature flags provide runtime toggles without code changes.
