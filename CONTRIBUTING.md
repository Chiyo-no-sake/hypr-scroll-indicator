# Contributing

Thanks for your interest in hypr-scroll-indicator!

## Workflow

1. Fork the repo and create a feature branch from `main`.
2. Make your changes, keeping commits focused and atomic.
3. Open a pull request against `main` with a clear description of what changed and why.

## Testing

There are no automated tests yet. Please test manually on a running Hyprland session with the **scrolling layout** enabled. Verify basic behavior:

- Indicator appears/hides correctly when scrolling.
- Color arguments and colors file are applied.
- Monitor hot-plug is handled gracefully.

## Guidelines

- **KISS** -- keep changes small and purposeful. Avoid unnecessary abstractions.
- Match the existing code style (Black-formatted Python, ~100 char line length).
- If adding a dependency, justify it in the PR description.

## Dependencies

To develop locally you need:

- Python 3.10+
- GTK4 (`gi.repository.Gtk` via PyGObject)
- gtk4-layer-shell (`gi.repository.Gtk4LayerShell`)
- Hyprland with the scrolling layout
