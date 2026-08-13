import subprocess
from pathlib import Path

import pytest

from quwoquan_ops.cli.lib.storage_contract_view import (
    STORAGE_DOCUMENT_KEYS,
    StorageContractViewError,
    load_storage_contract_view,
)
from quwoquan_ops.gate.verify_domain_model_storage_governance import (
    collect_storage_governance_issues,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _view_result(
    stdout: str,
    *,
    returncode: int = 0,
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        args=("storage_contract_view",),
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


def test_storage_contract_view_accepts_only_the_canonical_consumer_keyset(
    tmp_path: Path,
) -> None:
    storage = tmp_path / "storage.yaml"
    storage.write_text("backend: mongodb\nrole: primary\n", encoding="utf-8")

    payload = load_storage_contract_view(
        storage,
        runner=lambda *args, **kwargs: _view_result(
            '{"backend":"mongodb","role":"primary","collections":{}}\n'
        ),
    )

    assert payload == {
        "backend": "mongodb",
        "role": "primary",
        "collections": {},
    }
    assert set(payload) <= STORAGE_DOCUMENT_KEYS


@pytest.mark.parametrize(
    ("result", "message"),
    (
        (_view_result("", returncode=2, stderr="decode failed"), "exited 2"),
        (_view_result(""), "empty stdout"),
        (_view_result("not-json\n"), "invalid JSON"),
        (_view_result("[]\n"), "must return a JSON object"),
        (
            _view_result('{"backend":"mongodb","role":"primary","future":1}\n'),
            "unknown keys",
        ),
        (_view_result('{"backend":"mongodb"}\n'), "omitted required keys"),
    ),
)
def test_storage_contract_view_fail_closes_invalid_cli_results(
    tmp_path: Path,
    result: subprocess.CompletedProcess[str],
    message: str,
) -> None:
    storage = tmp_path / "storage.yaml"
    storage.write_text("backend: mongodb\nrole: primary\n", encoding="utf-8")

    with pytest.raises(StorageContractViewError, match=message):
        load_storage_contract_view(
            storage,
            runner=lambda *args, **kwargs: result,
        )


def test_storage_contract_view_fail_closes_timeout(tmp_path: Path) -> None:
    storage = tmp_path / "storage.yaml"
    storage.write_text("backend: mongodb\nrole: primary\n", encoding="utf-8")

    def timeout(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd="storage_contract_view", timeout=1)

    with pytest.raises(StorageContractViewError, match="timed out"):
        load_storage_contract_view(storage, timeout_seconds=1, runner=timeout)


def test_storage_contract_view_fail_closes_source_toctou(tmp_path: Path) -> None:
    storage = tmp_path / "storage.yaml"
    storage.write_text("backend: mongodb\nrole: primary\n", encoding="utf-8")

    def mutate(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        storage.write_text("backend: redis\nrole: primary\n", encoding="utf-8")
        return _view_result('{"backend":"mongodb","role":"primary"}\n')

    with pytest.raises(StorageContractViewError, match="changed while"):
        load_storage_contract_view(storage, runner=mutate)


def test_storage_contract_view_fail_closes_consumer_keyset_drift(
    tmp_path: Path,
) -> None:
    storage = tmp_path / "storage.yaml"
    storage.write_text("backend: mongodb\nrole: primary\n", encoding="utf-8")

    with pytest.raises(StorageContractViewError, match="keyset drifted"):
        load_storage_contract_view(
            storage,
            expected_keys={"backend", "role", "collections"},
            runner=lambda *args, **kwargs: _view_result(
                '{"backend":"mongodb","role":"primary"}\n'
            ),
        )


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


def test_storage_governance_rejects_go_redis_helper_key_without_owner(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path
        / "quwoquan_service/services/alpha-service/contracts/domain/item/storage.yaml",
        "collections: {alpha_items: {entity: Item}}\n",
    )
    _write(
        tmp_path
        / "quwoquan_service/services/alpha-service/internal/domain/item/cache.go",
        '''package item

import "fmt"

func quotaKey(subject string) string { return fmt.Sprintf("missing:quota:%s", subject) }

func increment(client interface{ Incr(any, string) (int64, error) }) {
    _, _ = client.Incr(nil, quotaKey("subject-1"))
}
''',
    )

    issues = collect_storage_governance_issues(tmp_path)

    assert any("missing:quota:" in issue and "undeclared" in issue for issue in issues)


def test_storage_governance_rejects_python_attribute_database_collection(
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
        '''class Store:
    def __init__(self, database):
        self._db = database

    def find(self):
        return self._db["missing_items"].find_one({})
''',
    )

    issues = collect_storage_governance_issues(tmp_path)

    assert any("missing_items" in issue and "undeclared" in issue for issue in issues)


def test_storage_governance_scans_sql_outbox_inbox_and_checkpoint_tables(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path
        / "quwoquan_service/services/alpha-service/contracts/domain/item/storage.yaml",
        '''backend: postgresql
tables:
  alpha_outbox: {entity: ItemOutbox}
  alpha_inbox: {entity: ItemInbox}
''',
    )
    _write(
        tmp_path
        / "quwoquan_service/services/alpha-service/internal/domain/item/store.go",
        '''package item

import "database/sql"

func persist(db *sql.DB) {
    _, _ = db.Exec(`INSERT INTO alpha_outbox (event_id) VALUES ($1)`, "event-1")
    _, _ = db.Exec(`SELECT event_id FROM alpha_inbox WHERE event_id = $1`, "event-1")
    _, _ = db.Exec(`UPDATE alpha_projector_checkpoints SET cursor = $1`, "cursor-1")
}
''',
    )

    issues = collect_storage_governance_issues(tmp_path)

    assert not any("alpha_outbox" in issue for issue in issues)
    assert not any("alpha_inbox" in issue for issue in issues)
    assert any(
        "alpha_projector_checkpoints" in issue and "undeclared" in issue
        for issue in issues
    )
