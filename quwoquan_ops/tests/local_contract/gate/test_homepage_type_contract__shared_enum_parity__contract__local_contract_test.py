from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
VERIFIER_PATH = ROOT / "quwoquan_ops/gate/verify_homepage_type_contract.py"
SPEC = importlib.util.spec_from_file_location("homepage_type_contract", VERIFIER_PATH)
assert SPEC is not None and SPEC.loader is not None
verifier = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = verifier
SPEC.loader.exec_module(verifier)


def _repository_inputs() -> dict[str, tuple[str, ...]]:
    return {
        "shared_values": verifier.load_shared_values(verifier.TYPES_PATH),
        "go_admission": verifier.load_go_admission(verifier.GO_PATH),
        "dart_labelled": verifier.load_dart_labelled(verifier.DART_LABEL_PATH),
        "wishlist_types": verifier.load_wishlist_types(verifier.UI_CONFIG_PATH),
        "location_types": verifier.load_dart_location_types(
            verifier.DART_LOCATION_PATH
        ),
        "importer_targets": verifier.load_go_importer_targets(verifier.LOADER_PATH),
        "intersection_bound_types": verifier.load_intersection_bound_types(
            verifier.INTERSECTION_REGISTRY_PATH
        ),
    }


class HomepageTypeContractTest(unittest.TestCase):
    def test_repository_contract_is_aligned(self) -> None:
        self.assertEqual(verifier.validate(**_repository_inputs()), [])

    def test_travel_drilldown_types_are_declared(self) -> None:
        shared = verifier.load_shared_values(verifier.TYPES_PATH)

        # 这四类是旅行交集的下钻宾语；缺任一个，对应交集句就没有可点击的落点。
        for value in ("transport_hub", "city", "route", "photo_spot"):
            self.assertIn(value, shared)

    def test_declared_type_without_a_label_fails_closed(self) -> None:
        # 复现整改前的真实形态：枚举里有值，label map 里没有，用户只看到通用「对象」。
        failures = verifier.validate(
            shared_values=("sight", "photo_spot"),
            go_admission=("sight", "photo_spot"),
            dart_labelled=("sight", "poi"),
            wishlist_types=("sight",),
            location_types=("sight",),
            importer_targets=("sight",),
            intersection_bound_types=("sight", "photo_spot"),
        )

        self.assertEqual(len(failures), 1)
        self.assertIn("photo_spot", failures[0])
        self.assertIn("generic label", failures[0])

    def test_type_missing_from_go_admission_fails_closed(self) -> None:
        failures = verifier.validate(
            shared_values=("sight", "city"),
            go_admission=("sight",),
            dart_labelled=("sight", "city"),
            wishlist_types=(),
            location_types=(),
            importer_targets=(),
            intersection_bound_types=("sight", "city"),
        )

        self.assertEqual(len(failures), 1)
        self.assertIn("Go admission set drift", failures[0])

    def test_subset_lists_may_be_smaller_but_not_invented(self) -> None:
        aligned = verifier.validate(
            shared_values=("sight", "city", "route"),
            go_admission=("sight", "city", "route"),
            dart_labelled=("sight", "city", "route"),
            wishlist_types=("city",),
            location_types=("sight",),
            importer_targets=("sight",),
            intersection_bound_types=("sight", "city", "route"),
        )
        self.assertEqual(aligned, [])

        invented = verifier.validate(
            shared_values=("sight", "city", "route"),
            go_admission=("sight", "city", "route"),
            dart_labelled=("sight", "city", "route"),
            wishlist_types=("citty",),
            location_types=("sight",),
            importer_targets=("sight",),
            intersection_bound_types=("sight", "city", "route"),
        )
        self.assertEqual(len(invented), 1)
        self.assertIn("homepage_wishlist_types", invented[0])
        self.assertIn("citty", invented[0])

    def test_label_aliases_do_not_count_as_undeclared(self) -> None:
        # poi/place/author/circle 不是 HomepageType，但共用同一个 label 函数。
        failures = verifier.validate(
            shared_values=("sight",),
            go_admission=("sight",),
            dart_labelled=("sight", "poi", "place", "author", "circle"),
            wishlist_types=(),
            location_types=(),
            importer_targets=(),
            intersection_bound_types=("sight",),
        )

        self.assertEqual(failures, [])

    def test_importer_target_must_be_a_declared_type(self) -> None:
        failures = verifier.validate(
            shared_values=("sight",),
            go_admission=("sight",),
            dart_labelled=("sight",),
            wishlist_types=(),
            location_types=(),
            importer_targets=("sight", "travel_photo"),
            intersection_bound_types=("sight",),
        )

        self.assertEqual(len(failures), 1)
        self.assertIn("entityTypeToHomepageType", failures[0])
        self.assertIn("travel_photo", failures[0])

    def test_type_without_an_intersection_binding_fails_closed(self) -> None:
        # 整改前的真实形态：museum 有枚举、有 label、能入库，但交集注册表没登记，
        # 于是查表落空被当成人物，用户点「共同点」跳进了个人主页。
        failures = verifier.validate(
            shared_values=("sight", "museum"),
            go_admission=("sight", "museum"),
            dart_labelled=("sight", "museum"),
            wishlist_types=(),
            location_types=(),
            importer_targets=(),
            intersection_bound_types=("sight",),
        )

        self.assertEqual(len(failures), 1)
        self.assertIn("objectTypeBindings", failures[0])
        self.assertIn("museum", failures[0])

    def test_bindings_may_cover_types_outside_the_enum(self) -> None:
        # 注册表还要收口 user/circle/homepage 这些非 HomepageType 的 objectType，
        # 所以只按覆盖校验，不能反过来要求 bindings 是枚举的子集。
        failures = verifier.validate(
            shared_values=("sight",),
            go_admission=("sight",),
            dart_labelled=("sight",),
            wishlist_types=(),
            location_types=(),
            importer_targets=(),
            intersection_bound_types=("sight", "user", "circle", "homepage"),
        )

        self.assertEqual(failures, [])

    def test_every_declared_type_is_bound_in_the_repository_registry(self) -> None:
        shared = set(verifier.load_shared_values(verifier.TYPES_PATH))
        bound = set(
            verifier.load_intersection_bound_types(verifier.INTERSECTION_REGISTRY_PATH)
        )

        self.assertEqual(sorted(shared - bound), [])


if __name__ == "__main__":
    unittest.main()
