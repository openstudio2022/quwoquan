from pathlib import Path

from quwoquan_ops.gate.verify_domain_model_storage_governance import (
    collect_storage_governance_issues,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_storage_governance_rejects_undeclared_duplicate_and_cross_service(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path
        / "quwoquan_service/services/alpha-service/contracts/domain/item/storage.yaml",
        """backend: mongodb
collections:
  alpha_items: {entity: Item}
  duplicated: {entity: Item}
""",
    )
    _write(
        tmp_path
        / "quwoquan_service/services/beta-service/contracts/domain/item/storage.yaml",
        """backend: mongodb
collections:
  duplicated: {entity: Item}
""",
    )
    _write(
        tmp_path
        / "quwoquan_service/services/beta-service/internal/domain/item/store.go",
        """package item
func use(db interface{ Collection(string) any }) {
  _ = db.Collection("alpha_items")
  _ = db.Collection("missing_items")
}
""",
    )

    issues = collect_storage_governance_issues(tmp_path)

    assert any("duplicated" in issue and "multiple owners" in issue for issue in issues)
    assert any("alpha_items" in issue and "owned by alpha-service" in issue for issue in issues)
    assert any("missing_items" in issue and "undeclared" in issue for issue in issues)


def test_storage_governance_accepts_object_local_declared_collection(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path
        / "quwoquan_service/services/alpha-service/contracts/domain/item/storage.yaml",
        """backend: mongodb
collections:
  alpha_items: {entity: Item}
""",
    )
    _write(
        tmp_path
        / "quwoquan_service/services/alpha-service/internal/domain/item/store.go",
        'package item\nfunc use(db interface{ Collection(string) any }) { _ = db.Collection("alpha_items") }\n',
    )

    assert collect_storage_governance_issues(tmp_path) == []


def test_storage_governance_scans_python_stream_redis_and_lookup(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path
        / "quwoquan_service/services/alpha-service/contracts/domain/item/storage.yaml",
        """backend: mongodb
collections:
  alpha_items: {entity: Item}
  joined_items: {entity: JoinedItem}
streams:
  events.alpha.items: {entity: ItemEvent}
  events.alpha.trimmed: {entity: TrimmedItemEvent}
redis_cache:
  - key: 'alpha:item:{itemId}'
""",
    )
    _write(
        tmp_path
        / "quwoquan_service/services/alpha-service/internal/domain/item/store.py",
        '''STREAM = "events.alpha.items"

def use(database, redis, item_id):
    database["alpha_items"].aggregate([
        {"$lookup": {"from": "joined_items", "localField": "id", "foreignField": "id"}}
    ])
    redis.xadd(STREAM, {"eventId": "event-1"})
    redis.xreadgroup("group", "consumer", {STREAM: ">"})
    redis.xtrim("events.alpha.trimmed", minid="1-0")
    redis.set(f"alpha:item:{item_id}", "value")
''',
    )

    assert collect_storage_governance_issues(tmp_path) == []


def test_storage_governance_rejects_python_dynamic_prefix_without_owner(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path
        / "quwoquan_service/services/alpha-service/contracts/domain/item/storage.yaml",
        "collections: {alpha_items: {entity: Item}}\n",
    )
    _write(
        tmp_path
        / "quwoquan_service/services/alpha-service/internal/domain/item/store.py",
        '''def use(redis, item_id):
    redis.set(f"missing:item:{item_id}", "value")
''',
    )

    issues = collect_storage_governance_issues(tmp_path)

    assert any("missing:item:" in issue and "undeclared" in issue for issue in issues)


def test_storage_governance_does_not_treat_mapping_or_uri_as_redis_key(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path
        / "quwoquan_service/services/alpha-service/contracts/domain/item/storage.yaml",
        "collections: {alpha_items: {entity: Item}}\n",
    )
    _write(
        tmp_path
        / "quwoquan_service/services/alpha-service/internal/domain/item/store.py",
        '''def use(database, document):
    database["alpha_items"].find_one({"_id": document.get("item:id")})
    document.get("mongoUri", "mongodb://127.0.0.1:27017")
''',
    )

    assert collect_storage_governance_issues(tmp_path) == []


def test_storage_governance_accepts_declared_cross_service_stream_writer(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path
        / "quwoquan_service/services/alpha-service/contracts/domain/fact/storage.yaml",
        """streams:
  events.alpha.fact:
    entity: AlphaFact
    writers: [beta-service]
""",
    )
    _write(
        tmp_path
        / "quwoquan_service/services/beta-service/internal/domain/fact/publisher.py",
        '''STREAM = "events.alpha.fact"

def publish(redis_client):
    redis_client.xadd(STREAM, {"eventId": "event-1"})
''',
    )

    assert collect_storage_governance_issues(tmp_path) == []


def test_storage_governance_scans_gateway_service_names(tmp_path: Path) -> None:
    _write(
        tmp_path
        / "quwoquan_service/services/realtime-gateway/contracts/realtime/presence_view/storage.yaml",
        """backend: redis
role: projection
redis_cache:
  - key: 'realtime:presence:{accountId}'
""",
    )
    _write(
        tmp_path
        / "quwoquan_service/services/realtime-gateway/internal/realtime/presence_view/infrastructure/store.py",
        '''def save(redis_client, account_id):
    redis_client.set(f"realtime:presence:{account_id}", "online")
''',
    )

    assert collect_storage_governance_issues(tmp_path) == []
