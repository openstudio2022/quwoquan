"""Canonical taxonomy generation and governance CLI."""
from __future__ import annotations

import argparse
from pathlib import Path


def _forward(args: argparse.Namespace, names: tuple[str, ...]) -> list[str]:
    output: list[str] = []
    for name in names:
        value = getattr(args, name, None)
        flag = "--" + name.replace("_", "-")
        if isinstance(value, bool):
            if value:
                output.append(flag)
        elif value is not None:
            output.extend([flag, str(value)])
    return output


def handle_taxonomy(args: argparse.Namespace) -> None:
    command = args.taxonomy_command
    if command == "bootstrap-tags":
        from governance.taxonomy.bootstrap_tags import main

        main(_forward(args, ("dry_run", "group")))
        return
    if command == "bootstrap-admin-regions":
        from governance.taxonomy.bootstrap_admin_regions import main

        main(_forward(args, ("country", "province", "dry_run", "stats")))
        return
    if command == "bootstrap-event-topics":
        from governance.taxonomy.bootstrap_event_topics import main

        main(_forward(args, ("dry_run",)))
        return
    if command == "bootstrap-geo-landmarks":
        from governance.taxonomy.bootstrap_geo_landmarks import main

        main(_forward(args, ("dry_run",)))
        return
    if command == "stats":
        from governance.taxonomy.stats import main

        main(_forward(args, ("json", "group")))
        return
    if command == "discover":
        from governance.taxonomy.discover import main

        main(_forward(args, ("dry_run",)))
        return
    if command == "graph":
        from governance.taxonomy.graph import main

        main(_forward(args, ("min_cooccur", "dry_run")))
        return
    if command == "merge-candidates":
        from governance.taxonomy.candidate_merge import main

        raise SystemExit(main(_forward(args, ("dry_run", "min_freq", "reviews"))))
    raise SystemExit("[taxonomy] subcommand required")


def register_taxonomy_parser(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser("taxonomy", help="Generate and govern the control-plane taxonomy")
    commands = parser.add_subparsers(dest="taxonomy_command", required=True)

    bootstrap_tags = commands.add_parser("bootstrap-tags")
    bootstrap_tags.add_argument("--dry-run", action="store_true")
    bootstrap_tags.add_argument("--group", choices=["Topic", "Audience", "Format", "Entity"])

    admin = commands.add_parser("bootstrap-admin-regions")
    admin.add_argument("--country")
    admin.add_argument("--province")
    admin.add_argument("--dry-run", action="store_true")
    admin.add_argument("--stats", action="store_true")

    for name in ("bootstrap-event-topics", "bootstrap-geo-landmarks", "discover"):
        command = commands.add_parser(name)
        command.add_argument("--dry-run", action="store_true")

    stats = commands.add_parser("stats")
    stats.add_argument("--json", action="store_true")
    stats.add_argument("--group", choices=["Topic", "Audience", "Format", "Entity"])

    graph = commands.add_parser("graph")
    graph.add_argument("--min-cooccur", type=int, default=1)
    graph.add_argument("--dry-run", action="store_true")

    merge = commands.add_parser("merge-candidates")
    merge.add_argument("--dry-run", action="store_true")
    merge.add_argument("--min-freq", type=int, default=3)
    merge.add_argument("--reviews", type=Path)

    for command in commands.choices.values():
        command.set_defaults(handler=handle_taxonomy)
