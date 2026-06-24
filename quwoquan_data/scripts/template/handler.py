"""qwq-data template subcommands."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from template.coverage import coverage_summary
from template.creator import validate_creators
from template.lint import lint_templates, validate_audiences
from template.recommend import validate_recommendation_contract
from template.registry import TemplateRegistry, write_yaml


def handle_template(args: argparse.Namespace) -> None:
    registry = TemplateRegistry.load()
    if args.template_command == "lint":
        _print_errors(lint_templates(registry), "template lint")
        return
    if args.template_command == "rec-contract":
        _print_errors(validate_recommendation_contract(registry), "template rec-contract")
        return
    if args.template_command == "creator-lint":
        _print_errors(validate_creators(registry), "template creator-lint")
        return
    if args.template_command == "audience-lint":
        _print_errors(validate_audiences(registry), "template audience-lint")
        return
    if args.template_command == "coverage":
        print(json.dumps(coverage_summary(registry, args.vertical), ensure_ascii=False, indent=2))
        return
    if args.template_command == "show":
        blueprint = registry.blueprints.get(args.template_id)
        if blueprint is None:
            print(f"[template] missing template: {args.template_id}", file=sys.stderr)
            sys.exit(1)
        print(json.dumps(blueprint, ensure_ascii=False, indent=2))
        return
    if args.template_command == "new":
        source_path = registry.blueprint_paths.get(args.from_template)
        if source_path is None:
            print(f"[template] missing source template: {args.from_template}", file=sys.stderr)
            sys.exit(1)
        data = registry.blueprints[args.from_template].copy()
        data["templateId"] = args.to_template
        target = source_path.with_name(f"{args.to_template}.tmpl.yaml")
        if target.exists() and not args.force:
            print(f"[template] target exists: {target}", file=sys.stderr)
            sys.exit(1)
        write_yaml(target, data)
        print(f"[template] created: {target}")
        return
    raise ValueError(f"Unknown template command: {args.template_command}")


def register_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("template", help="Template library tools")
    sub = p.add_subparsers(dest="template_command", required=True)

    p_lint = sub.add_parser("lint", help="Validate template blueprints")
    p_lint.set_defaults(handler=handle_template)

    p_rec = sub.add_parser("rec-contract", help="Validate recommendation-facing manifest contract")
    p_rec.set_defaults(handler=handle_template)

    p_creator = sub.add_parser("creator-lint", help="Validate system builtin creators")
    p_creator.set_defaults(handler=handle_template)

    p_aud = sub.add_parser("audience-lint", help="Validate audience catalog has no orphan audiences")
    p_aud.set_defaults(handler=handle_template)

    p_cov = sub.add_parser("coverage", help="Print template coverage summary")
    p_cov.add_argument("--vertical", choices=["travel", "campus"], default=None)
    p_cov.set_defaults(handler=handle_template)

    p_show = sub.add_parser("show", help="Show a template blueprint")
    p_show.add_argument("template_id")
    p_show.set_defaults(handler=handle_template)

    p_new = sub.add_parser("new", help="Scaffold a blueprint from an existing template")
    p_new.add_argument("--from", dest="from_template", required=True)
    p_new.add_argument("--to", dest="to_template", required=True)
    p_new.add_argument("--force", action="store_true")
    p_new.set_defaults(handler=handle_template)


def _print_errors(errors: list[str], label: str) -> None:
    if errors:
        print(f"[{label}] FAILED ({len(errors)} issue(s))", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        sys.exit(1)
    print(f"[{label}] PASSED")
