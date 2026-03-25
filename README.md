# GitHub Organization Activity Tracker

A 3D visualization tool for tracking GitHub organization activity - open PRs, CI status, and repository health. Originally forked from the Conductor Worktree Tracker, this version works with any GitHub organization and can be hosted on GitHub Pages.

**[View BreadchainCoop Dashboard](https://breadchaincoop.github.io/org-activity-tracker/)** (once deployed)

## Features

- **3D Visualization**: Interactive Three.js scene showing repositories and PRs as interconnected nodes
- **PR Hierarchy**: Stacked PRs are visualized as connected trees
- **CI/CD Status**: Live status indicators for GitHub Actions (green=pass, red=fail, yellow=pending)
- **PR Freshness**: Color-coded nodes based on last update time
- **Static Hosting**: Works on GitHub Pages with periodic data updates via GitHub Actions
- **No Server Required**: Pure client-side rendering with pre-generated JSON data

## Quick Start

### View Locally

```bash
# Generate data
python3 fetch_org_data.py

# Serve locally (Python 3)
python3 -m http.server 8000

# Open http://localhost:8000 in browser
```

### Deploy to GitHub Pages

1. Fork this repository
2. Update `org_config.json` with your organization name
3. Enable GitHub Pages in repository settings (Settings > Pages > Source: GitHub Actions)
4. The data will auto-update every 15 minutes via GitHub Actions

## Configuration

All settings are configured in `org_config.json`:

```json
{
  "organization": "BreadchainCoop",
  "stale_minutes": 60,
  "max_repos": 50,
  "fetch_prs": true,
  "fetch_ci": true,
  "refresh_interval_minutes": 15,
  "repo_filters": {
    "exclude": [],
    "include_archived": false,
    "min_pushed_days_ago": 365
  }
}
```

### Configuration Options

| Variable | Type | Default | Description |
|----------|------|---------|-------------|
| `organization` | string | `"BreadchainCoop"` | GitHub organization to track |
| `stale_minutes` | int | `60` | Minutes before a PR is considered stale |
| `max_repos` | int | `50` | Maximum repositories to process |
| `fetch_prs` | bool | `true` | Fetch open PRs for each repository |
| `fetch_ci` | bool | `true` | Fetch CI status for each PR |
| `refresh_interval_minutes` | int | `15` | How often GitHub Actions refreshes data |
| `repo_filters.exclude` | array | `[]` | Repository names to exclude |
| `repo_filters.include_archived` | bool | `false` | Include archived repositories |
| `repo_filters.min_pushed_days_ago` | int | `365` | Only include repos pushed within this many days |

## Data Generation

The `fetch_org_data.py` script generates `data/org_data.json` containing:

- Organization metadata
- Repository information
- Open PRs with CI status
- PR hierarchy (stacked PRs)

```bash
# Run with defaults from org_config.json
python3 fetch_org_data.py

# Override organization
python3 fetch_org_data.py --org MyOrganization

# Custom output path
python3 fetch_org_data.py --output ./custom-path/data.json
```

## GitHub Actions Workflows

### Data Update (`update-data.yml`)

Runs every 15 minutes to refresh PR and CI data:
- Fetches latest organization data
- Only commits if data has changed
- Uses `[skip ci]` to avoid deploy loops

### Deploy (`deploy.yml`)

Deploys to GitHub Pages on every push to main:
- Uses GitHub Pages artifact deployment
- `index.html` redirects to `tracker3d.html?org=breadchaincoop` which loads from `data/` directory

## Visual Indicators

### Node Colors (Freshness)

| Color | Time Since Last Update |
|-------|----------------------|
| Green | 0-15 minutes |
| Yellow | 15-30 minutes |
| Orange | 30-60 minutes |
| Red | 60+ minutes |

### CI Status

| Color | Status |
|-------|--------|
| Green | All checks passed |
| Red | One or more checks failed |
| Yellow | Checks in progress |

### Node Types

- **Large sphere**: Repository center (default branch)
- **Medium sphere**: PR with checks
- **Small/transparent sphere**: Draft PR
- **Lines**: PR hierarchy connections

## Controls

| Control | Action |
|---------|--------|
| Drag | Rotate camera |
| Shift+Drag | Pan camera |
| Scroll | Zoom in/out |
| Click node | Open PR on GitHub |
| T | Toggle light/dark theme |
| F | Fit all nodes to screen |

## Dependencies

- Python 3.8+
- `gh` CLI (GitHub CLI): `brew install gh` or `apt install gh`
- Modern browser with WebGL support

## Original Project

This project was forked from the [Conductor Worktree Tracker](https://github.com/anthropics/conductor), which provides real-time tracking for Conductor workspaces. The original terminal-based tracker (`tracker.py`) and 3D server version (`tracker_server.py`, `tracker3d.html`) are still included for Conductor users.

## License

MIT License
