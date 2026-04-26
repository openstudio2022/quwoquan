# Pageflip Milestone Freeze

## Purpose

This document freezes the pageflip refactor boundary before implementation continues.
The goal is to make the new `pageflip` component converge on the same rendering
contract as the long-form article pageflip implementation, while explicitly
discarding any remaining alternative mainline routes.

## Canonical Reference Scope

The long-form page-flip pipeline is treated as the target contract.
Forward motion remains the canonical baseline, and backward motion is accepted
only as the mirrored replay of that same rendering pipeline.

Canonical references for the freeze:

- `lib/ui/content/widgets/article_paged_canvas.dart`
- `lib/ui/content/pageflip/curl_renderer.dart`
- `lib/ui/content/pageflip/backward_leaf_renderer.dart`
- `lib/ui/content/pageflip/page_surface_snapshot.dart`
- `lib/ui/content/pageflip/render_frame.dart`
- `lib/ui/content/pageflip/geometry.dart`
- `lib/ui/content/pageflip/release_policy.dart`

Reference behavior from `@react-pageflip` is used only as an industry comparator
for shared single-page flip semantics. It does not justify a separate runtime
route for backward motion.

## Freeze Decisions

1. `pageflip` must keep only one main rendering line: the long-form article
   rendering contract that is already validated by forward motion.
2. Any soft-flip simplification, mesh-only fallback, or independent page-turn
   overlay route is considered legacy and must not be treated as a primary path.
3. Backward motion must reuse that same rendering line as the mirrored replay
   of forward motion; it is not allowed to keep a separate runtime route.
4. Page selection, texture binding, and render order must be defined by the
   long-form article pipeline, not by `pageflip`-local heuristics.
5. The new component must not keep a second compatibility implementation once
   the long-form path is selected.

## Milestone 1 Definition

Milestone 1 freezes the architectural boundary only.
It does not claim visual parity yet; it locks the implementation target so the
next steps can be written against one contract.

### Milestone 1 tasks

- Freeze the role mapping for forward flips: current page, turning page, and
  bottom page must follow the long-form semantic split.
- Freeze the scene contract: `pageRect`, `pageSize`, and texture windowing must
  be derived from the article page pipeline, not from a separate `pageflip`
  coordinate model.
- Freeze the render order: bottom page, bottom projection, back surface, front
  surface, and ambient/spine shading must be preserved as the only accepted
  ordering model.
- Freeze the source-of-truth list for page snapshots and binding selection.
- Freeze backward page-turn behavior as the mirrored replay of the long-form
  forward reference, sharing the same renderer and texture-selection contract.

## Current State

The current `pageflip` component is still in a mixed transitional state.
That means:

- the component has already been redirected away from the old soft-flip-only
  route,
- but it still needs full alignment with the article pipeline for page
  selection, texture binding, and layer composition,
- and the backward path still needs final cleanup so it fully rejoins that same
  canonical pipeline without legacy branches.

In short, the route is chosen, but the freeze is about ensuring there is no
second route left alive.

## Milestone 1 Acceptance Criteria

Milestone 1 is accepted only when all of the following are true:

- The long-form article pipeline is the only declared mainline for `pageflip`.
- The component documentation explicitly rejects a second runtime route.
- The forward render contract is mapped to the long-form article pipeline.
- The backward route is explicitly defined as the mirrored replay of the same
  canonical pipeline, not as diagnostic-only material.
- There is a clear file-level migration plan for page selection, texture
  binding, and render ordering.
- No milestone note or implementation note still treats soft-flip simplification
  as a valid primary path.

## Exit Criteria For Development Entry

Development can start when this freeze is stable and the following are locked:

- one canonical render route
- one page-role semantic mapping
- one render-order contract
- one texture-binding contract
- one migration list for remaining cleanup

## Out Of Scope

- Reintroducing a second mainline rendering route
- Reintroducing a backward-only runtime route outside the canonical pipeline
- Keeping compatibility shims that can route rendering away from the long-form
  forward pipeline
- Trying to preserve both the simplified route and the article route in parallel

