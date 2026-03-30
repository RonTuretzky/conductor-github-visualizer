# Conductor Tracker — visionOS Native App Spec

## Overview

A native visionOS app that renders the Conductor Tracker visualization as a **spatial environment** using RealityKit. The user is surrounded by their GitHub organization's repos and PRs as glowing nodes in space, while still being able to use other apps and windows (mixed immersion).

This is a port of the existing Three.js web tracker (`tracker3d-visionpro.html`) to native Swift/RealityKit, specifically to unlock the visionOS **ImmersiveSpace** API — which allows rendering 3D content around the user without hiding other windows.

---

## Target Platform

- visionOS 2.0+
- Swift 6 / SwiftUI
- RealityKit (not SceneKit, not Unity)
- No Conductor app dependency — standalone app that fetches data over HTTP or reads a static JSON file

---

## Data Model

The app consumes the same JSON schema as the web tracker. Data is fetched from one of:

1. **HTTP API**: `http://<host>:8765/api/tracker` (live Conductor server)
2. **Static JSON file**: bundled or user-provided URL via `?data=` equivalent
3. **Local file**: loaded from app documents directory

### Root JSON Structure

```json
{
  "organization": "string",
  "generated_at": "ISO 8601",
  "stale_minutes": 30,
  "stats": {
    "total_repos": 39,
    "repos_with_prs": 20,
    "total_open_prs": 80,
    "total_open_issues": 181
  },
  "trees": {
    "repo-name": {
      "name": "repo-name",
      "branch": "main",
      "repo_name": "repo-name",
      "github_url": "https://github.com/org/repo-name",
      "last_updated": "ISO 8601",
      "children": [ /* PR nodes */ ]
    }
  }
}
```

### PR Node Structure

```json
{
  "name": "Display Name",
  "branch": "author/feature-branch",
  "repo_name": "repo-name",
  "pr_number": 95,
  "pr_title": "Fix the thing",
  "pr_url": "https://github.com/org/repo/pull/95",
  "pr_author": "username",
  "last_updated": "ISO 8601",
  "ci_status": "pass" | "fail" | "pending" | "",
  "is_draft": false,
  "labels": [],
  "parent_branch_name": "main",
  "children": [ /* stacked PRs */ ]
}
```

### Swift Types

```swift
struct TrackerData: Codable {
    let organization: String?
    let generatedAt: String?
    let staleMinutes: Int?
    let stats: Stats?
    let trees: [String: RepoTree]

    struct Stats: Codable {
        let totalRepos: Int?
        let reposWithPrs: Int?
        let totalOpenPrs: Int?
        let totalOpenIssues: Int?
    }
}

struct RepoTree: Codable {
    let name: String
    let branch: String?
    let repoName: String?
    let githubUrl: String?
    let lastUpdated: String?
    let children: [PRNode]?
}

struct PRNode: Codable, Identifiable {
    var id: String { workspaceId ?? "org-\(repoName ?? "")-\(prNumber ?? 0)" }
    let workspaceId: String?
    let name: String?
    let branch: String?
    let repoName: String?
    let prNumber: Int?
    let prTitle: String?
    let prUrl: String?
    let prAuthor: String?
    let lastUpdated: String?
    let ciStatus: String?
    let isDraft: Bool?
    let labels: [String]?
    let parentBranchName: String?
    let children: [PRNode]?
}
```

Use `CodingKeys` with `snake_case` conversion or `JSONDecoder.keyDecodingStrategy = .convertFromSnakeCase`.

---

## Architecture

```
ConductorTracker/
├── ConductorTrackerApp.swift          // App entry, WindowGroup + ImmersiveSpace
├── Models/
│   ├── TrackerData.swift              // Codable types above
│   └── TrackerViewModel.swift         // ObservableObject, data fetching, scoring
├── Views/
│   ├── ContentView.swift              // 2D window: settings, status, data URL config
│   ├── ImmersiveView.swift            // RealityKit immersive space
│   └── NodeDetailView.swift           // Attachment: PR detail popover
├── Entities/
│   ├── RepoNodeEntity.swift           // RealityKit entity for repo spheres
│   ├── PRNodeEntity.swift             // RealityKit entity for PR spheres
│   ├── ConnectionLineEntity.swift     // Lines between nodes
│   └── TextBillboard.swift            // 3D text labels (MeshResource.generateText)
├── Utilities/
│   ├── FreshnessColor.swift           // Score → color mapping
│   └── SphereLayout.swift             // Fibonacci sphere distribution
└── Resources/
    └── sample_data.json               // Bundled fallback data for demo
```

---

## App Entry Point

```swift
@main
struct ConductorTrackerApp: App {
    @State private var immersionStyle: ImmersionStyle = .mixed

    var body: some Scene {
        // 2D window for settings/status
        WindowGroup {
            ContentView()
        }

        // Spatial environment
        ImmersiveSpace(id: "tracker-environment") {
            ImmersiveView()
        }
        .immersionStyle(selection: $immersionStyle, in: .mixed)
    }
}
```

Key: `.mixed` immersion style means the 3D content renders in the user's space alongside their other windows. This is the critical difference from the web version.

---

## Scene Layout

### Surround Mode (Primary)

Repos are placed on a **Fibonacci sphere shell** around the user's head position.

```swift
func fibonacciSpherePosition(index: Int, total: Int, radius: Float) -> SIMD3<Float> {
    let golden = (1.0 + sqrt(5.0)) / 2.0
    let theta = 2.0 * .pi * Float(index) / Float(golden)
    let phi = acos(1.0 - 2.0 * (Float(index) + 0.5) / Float(total))

    // Clamp to a band ±40° from horizon (don't put repos above/below head)
    let clampedPhi = 0.5 + (phi / .pi) * (.pi - 1.0)

    return SIMD3<Float>(
        radius * sin(clampedPhi) * cos(theta),
        radius * cos(clampedPhi),
        radius * sin(clampedPhi) * sin(theta)
    )
}
```

**Parameters:**
- Sphere radius: **2.5 meters** (comfortable arm's-length viewing in spatial)
- Repo sphere diameter: **8 cm**
- PR node diameter: **5 cm**
- Connection line thickness: **2 mm**

PR nodes branch **outward** from their repo, away from center. Stacked PRs extend further out.

---

## Visual Design

### Freshness Color Gradient

Same 4-stop gradient as web version:

| Score Range | Color | Hex |
|-------------|-------|-----|
| 0.0–0.33 | Fresh green | `#39FF14` |
| 0.33–0.66 | Recent yellow → aging orange | `#EAB308` → `#F97316` |
| 0.66–1.0 | Stale red | `#EF4444` |

Score = `min(1, minutesSinceUpdate / staleMinutes)`

Linear interpolation between stops.

### Materials

Use **PhysicallyBasedMaterial** with emissive for glow:

```swift
var material = PhysicallyBasedMaterial()
material.baseColor = .init(tint: freshnessColor)
material.emissiveColor = .init(color: freshnessColor)
material.emissiveIntensity = 0.5
```

For extra glow, add a slightly larger, transparent sphere behind each node (bloom effect).

### Labels

Use `MeshResource.generateText()` for repo names. For PR status badges, use small billboard attachments or text meshes.

Labels should **face the user** (billboard behavior). RealityKit supports this via `BillboardComponent`.

### CI Status Indicators

Small colored ring or badge near each PR node:
- **Pass**: green ring + checkmark
- **Fail**: red ring + X
- **Pending**: yellow ring + dots
- **Unknown**: gray, no indicator

### Connection Lines

Thin cylinders or `MeshResource` lines from each PR node back to its parent repo/PR. Semi-transparent, colored to match the repo's average freshness.

### Ambient Effects

- Subtle particle system around the space (RealityKit `ParticleEmitterComponent`)
- Very slow rotation of the entire constellation (~0.3°/sec) for liveliness
- Optional: faint starfield on a large inverted sphere behind everything

---

## Interaction

### Gaze + Tap (Primary on Vision Pro)

- **Look at a node**: Highlight (scale up slightly, increase emissive glow). Show a floating detail card as a SwiftUI **attachment** anchored to the entity.
- **Tap a node**: Open the PR URL in Safari via `openURL` environment action.
- **Pinch + drag**: Rotate the entire constellation around the user.
- **Zoom pinch**: Scale the constellation closer/further.

### Detail Card (SwiftUI Attachment)

When gazing at a PR node, show a small floating card:

```
┌──────────────────────────┐
│ Fix the thing         #95│
│ author/feature-branch    │
│ Author: username         │
│ CI: ✓ pass   Updated: 1d│
│ [Open in GitHub →]       │
└──────────────────────────┘
```

Use RealityKit's attachment API to anchor SwiftUI views to entities.

### System Window (2D)

The `WindowGroup` provides a small settings/control panel:
- Data source URL input
- Refresh button / auto-refresh toggle (interval: 60s)
- Organization name display
- Stats summary (repos, PRs, issues)
- "Enter Environment" button to open the ImmersiveSpace

---

## Data Flow

```
┌──────────────────┐
│ ContentView      │  ← User sets data URL
│ (2D Window)      │
└────────┬─────────┘
         │ opens
         ▼
┌──────────────────┐     ┌─────────────────────┐
│ ImmersiveView    │────▶│ TrackerViewModel     │
│ (RealityKit)     │     │ @Observable          │
└──────────────────┘     │ - fetchData()        │
                         │ - trackerData        │
                         │ - autoRefreshTimer   │
                         └──────────┬──────────┘
                                    │ HTTP GET
                                    ▼
                         ┌─────────────────────┐
                         │ JSON endpoint        │
                         │ localhost:8765 or    │
                         │ bundled file         │
                         └─────────────────────┘
```

Use `URLSession` for fetching. Decode with `JSONDecoder` (snake_case strategy). Auto-refresh every 60 seconds. On data update, diff the tree and animate node position/color changes rather than rebuilding the whole scene.

---

## Settings Persistence

Use `@AppStorage` or `UserDefaults` for:
- `dataSourceURL: String` — last used API/data URL
- `autoRefresh: Bool` — whether to poll
- `refreshInterval: TimeInterval` — polling interval (default 60s)
- `surroundRadius: Float` — user-preferred constellation size
- `rotationSpeed: Float` — ambient rotation speed (0 = off)

---

## Networking

The app does NOT require Conductor to be running. It just needs access to the JSON data. Options:

1. **Local network**: Conductor server on Mac at `http://<mac-ip>:8765/api/tracker`
2. **Static file**: Host `org_data.json` anywhere (GitHub Pages, S3, local nginx)
3. **Bundled demo**: Include `sample_data.json` in app bundle for offline demo
4. **Paste/share**: Accept a shared JSON file via the visionOS share sheet

For local network access, the app needs the **Local Network** entitlement and `NSLocalNetworkUsageDescription` in Info.plist. For HTTP (non-HTTPS), add an App Transport Security exception for the local IP.

---

## Performance Considerations

- Target: 90 fps (visionOS requirement for comfort)
- Current dataset: ~80 PRs + 39 repos = ~120 entities — well within budget
- Use instanced rendering (`ModelComponent` with shared `MeshResource`) for node spheres
- Text labels: generate once, update only on data refresh
- Connection lines: use a single mesh with all line segments batched
- Particle effects: use built-in `ParticleEmitterComponent` (GPU-accelerated)

---

## Build & Test

### Requirements
- Xcode 16+
- visionOS 2.0 SDK
- Apple Developer account (for device deployment)
- visionOS Simulator works for layout testing

### Quick Start
```bash
# Clone the repo
git clone <repo-url>
cd ConductorTracker

# Open in Xcode
open ConductorTracker.xcodeproj

# Build for visionOS Simulator
# Product → Destination → Apple Vision Pro (Designed for visionOS)
# Cmd+R to run

# For real device: connect via Developer Strap or wireless deployment
```

### Testing Without Live Data
The app bundles `sample_data.json` (snapshot of real org data). On first launch with no configured URL, it loads the bundled data so you can see the visualization immediately.

---

## Future Extensions (Out of Scope for V1)

- **SharePlay**: Multiple people viewing the same tracker in a shared space
- **Spatial audio**: Subtle chime when a PR's CI status changes
- **Hand gestures**: Grab and rearrange nodes, pin repos closer
- **Widget**: visionOS ornament showing stale PR count
- **Deep link**: `conductortracker://open?pr=org/repo/123` to highlight a specific PR
- **SQLite direct read**: Mount Conductor's local DB instead of HTTP (requires shared app group or file provider)
