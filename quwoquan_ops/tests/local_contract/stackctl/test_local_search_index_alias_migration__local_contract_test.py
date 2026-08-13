from __future__ import annotations

import unittest

from quwoquan_ops.cli.lib import local_search_index_alias_migration as migration


class _RollbackElasticsearch:
    def __init__(self, hits: list[dict[str, object]]) -> None:
        self.hits = hits
        self.calls: list[tuple[object, ...]] = []

    def delete_index(self, index: str) -> None:
        self.calls.append(("delete", index))

    def index_exists(self, index: str) -> bool:
        self.calls.append(("exists", index))
        return False

    def create_index(self, index: str, body: dict[str, object]) -> None:
        self.calls.append(("create", index, body))

    def reindex(self, source: str, destination: str) -> dict[str, int]:
        self.calls.append(("reindex", source, destination))
        return {"created": len(self.hits)}

    def documents(self, index: str) -> list[dict[str, object]]:
        self.calls.append(("documents", index))
        return self.hits


class LocalSearchIndexAliasMigrationContractTest(unittest.TestCase):
    def test_canonical_names_match_search_index_lifecycle(self) -> None:
        self.assertEqual(migration.READ_ALIAS, "quwoquan_objects")
        self.assertEqual(migration.WRITE_ALIAS, "quwoquan_objects-write")
        self.assertEqual(migration.FIRST_GENERATION, "quwoquan_objects-v1")

    def test_inventory_detects_content_or_id_drift(self) -> None:
        before = migration._document_inventory(
            [
                {
                    "_id": "a",
                    "_source": {"title": "大理"},
                    "_seq_no": 2,
                    "_primary_term": 1,
                    "_version": 3,
                }
            ]
        )
        changed = migration._document_inventory(
            [
                {
                    "_id": "a",
                    "_source": {"title": "丽江"},
                    "_seq_no": 3,
                    "_primary_term": 1,
                    "_version": 4,
                }
            ]
        )
        self.assertEqual(before["idSetDigest"], changed["idSetDigest"])
        self.assertNotEqual(before["contentDigest"], changed["contentDigest"])
        with self.assertRaisesRegex(RuntimeError, "contentDigest"):
            migration._assert_inventory(before, changed, label="target")

    def test_backup_schema_drops_elasticsearch_generated_settings(self) -> None:
        body = migration._source_create_body(
            {
                "settings": {
                    "index": {
                        "analysis": {"analyzer": {"legacy": {"type": "standard"}}},
                        "number_of_shards": "1",
                        "number_of_replicas": "1",
                        "uuid": "must-not-be-reused",
                        "version": {"created": "8130499"},
                    }
                },
                "mappings": {"properties": {"title": {"type": "text"}}},
            }
        )
        self.assertNotIn("uuid", body["settings"])
        self.assertNotIn("version", body["settings"])
        self.assertEqual(body["settings"]["number_of_shards"], "1")

    def test_loopback_endpoint_is_mandatory(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "loopback"):
            migration._Elasticsearch("https://search.example.com:9200")

    def test_rollback_recreates_legacy_physical_index_from_backup(self) -> None:
        hits = [
            {
                "_id": "object-1",
                "_source": {"objectType": "content.post"},
                "_seq_no": 0,
                "_primary_term": 1,
                "_version": 1,
            }
        ]
        expected = migration._document_inventory(hits)
        es = _RollbackElasticsearch(hits)
        report = migration._rollback(
            es,  # type: ignore[arg-type]
            source_body={"settings": {}, "mappings": {}},
            backup="quwoquan_objects-legacy-backup-final",
            target=migration.FIRST_GENERATION,
            expected_inventory=expected,
        )
        self.assertEqual(report["inventory"]["count"], 1)
        self.assertIn(("delete", migration.FIRST_GENERATION), es.calls)
        self.assertIn(
            (
                "reindex",
                "quwoquan_objects-legacy-backup-final",
                migration.READ_ALIAS,
            ),
            es.calls,
        )


if __name__ == "__main__":
    unittest.main()
