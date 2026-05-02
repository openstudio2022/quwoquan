# iOS Migration & Pollution Prevention Guide

## Core Principle: Cupertino-First

The application is migrating to a strict iOS-first design. All new UI code must use Cupertino widgets. Material widgets are strictly banned unless absolutely necessary and wrapped in a "Material Tunnel".

## 1. Component Mapping (Strict Allowlist)

| Category | ❌ Banned (Material) | ✅ Required (iOS/Custom) | Notes |
| :--- | :--- | :--- | :--- |
| **Page Skeleton** | `Scaffold` | `AppScaffold` | Wrapper for `CupertinoPageScaffold` |
| **Navbar** | `AppBar` | `AppNavigationBar` | Wrapper for `CupertinoNavigationBar` |
| **Feedback** | `SnackBar`, `ScaffoldMessenger` | `AppToast.show` | Overlay-based toast |
| **Loading** | `CircularProgressIndicator` | `CupertinoActivityIndicator` | |
| **Switch** | `Switch` | `CupertinoSwitch` | Must set `activeColor: AppColors.primary` |
| **Button** | `ElevatedButton`, `TextButton`, `IconButton` | `CupertinoButton` | Use `.filled` for primary actions |
| **Inputs** | `TextField` | `CupertinoTextField` | |
| **List Item** | `ListTile` | `CupertinoListTile` | Custom implementation required |
| **Icons** | `Icons.arrow_back` | `CupertinoIcons.back` | |
| **Modals** | `showModalBottomSheet` | `showCupertinoModalPopup` | |

## 2. The "Material Tunnel" Pattern

When a Material widget is unavoidable (e.g., `TextFormField` for validation, or a 3rd party library widget), you must use the "Material Tunnel" pattern to isolate it from the visual tree.

**Rule:** Wrap the Material widget in a `Material` widget with `type: MaterialType.transparency`.

```dart
// ✅ Correct: Material Tunnel
child: Material(
  type: MaterialType.transparency, // 1. Transparent background
  child: TextFormField(
    decoration: InputDecoration(
      border: InputBorder.none, // 2. Remove Material visual artifacts
      // ...
    ),
    // ...
  ),
)
```

**Why?**
*   Prevent `Material` background color from leaking.
*   Provide necessary `Material` ancestor for widgets that require it.
*   Explicitly mark the code as "current/exception".

## 3. Automated Enforcement

We use `scripts/verify_dart_semantic.py` to enforce these rules.
*   **Global Bans:** `Scaffold`, `AppBar`, `SnackBar`, etc. are banned globally.
*   **Visual Constants:** Hardcoded `Color(0x...)`, `width: 10`, etc. are banned in favor of `AppSpacing`, `AppColors`.

**To bypass (use sparingly):**
Add `// ignore: verify_dart_semantic` to the specific line.

## 4. Migration Strategy

1.  **Stop the Bleeding:** No new Material code.
2.  **Isolate:** Wrap existing Material code in Tunnels if not refactoring immediately.
3.  **Replace:** Systematically replace components (Phase 2 & 3 of Migration Plan).
