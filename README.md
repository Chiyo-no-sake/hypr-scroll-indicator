# hypr-scroll-indicator

A browser-like scrollbar overlay for [Hyprland](https://hyprland.org/)'s scrolling layout. Shows a thin bar at the bottom of the screen indicating your viewport position on the window tape.

<!-- Add a screenshot: place it in the repo as screenshot.png and uncomment below -->
<!-- ![screenshot](screenshot.png) -->

## Features

- Smooth animated scrollbar that follows your viewport position
- Configurable bezier easing (matches your Hyprland animations)
- Customizable colors via CLI flags or Hyprland-format colors file
- Auto-hides when the window tape fits in the viewport
- Monitor hot-plug detection (cache invalidation on add/remove)
- Lightweight GTK4 layer-shell overlay

## Dependencies

| Dependency | Purpose |
|---|---|
| Python 3.10+ | Runtime |
| GTK4 | UI toolkit |
| [gtk4-layer-shell](https://github.com/wmww/gtk4-layer-shell) | Wayland layer surface |
| PyGObject | Python GTK4 bindings |
| PyCairo | 2D drawing |
| Hyprland | Compositor (scrolling layout required) |

### Fedora

```sh
sudo dnf install python3-gobject gtk4 gtk4-layer-shell python3-cairo
```

### Arch Linux

```sh
sudo pacman -S python-gobject gtk4 gtk4-layer-shell python-cairo
```

### Ubuntu / Debian

```sh
sudo apt install libgtk-4-1 libgtk4-layer-shell0 python3-gi python3-gi-cairo gir1.2-gtk-4.0
```

## Installation

```sh
git clone https://github.com/Chiyo-no-sake/hypr-scroll-indicator.git
cd hypr-scroll-indicator
sudo make install
```

This installs to `/usr/local/bin/`. The included wrapper script automatically finds `libgtk4-layer-shell` on your system — no manual `LD_PRELOAD` needed.

Custom prefix:

```sh
sudo make install PREFIX=/usr
```

Uninstall:

```sh
sudo make uninstall
```

## Usage

```sh
hypr-scroll-indicator [OPTIONS]
```

### Geometry

| Flag | Default | Description |
|------|---------|-------------|
| `--bar-height` | `14` | Bar height in pixels |
| `--thumb-radius` | `6` | Corner radius in pixels |
| `--thumb-inset` | `3` | Thumb inset from track edges in pixels |
| `--margin-bottom` | `10` | Bottom margin in pixels |
| `--margin-side` | `64` | Left/right margin in pixels |

### Colors

| Flag | Default | Description |
|------|---------|-------------|
| `--color-primary` | `#91D59B` | Primary / thumb gradient start color |
| `--color-secondary` | *(darkened primary)* | Thumb gradient end color |
| `--color-track` | *(very dark primary)* | Track background color |
| `--colors-file` | *(none)* | Path to Hyprland-format `colors.conf` (overrides `--color-*` flags) |

### Animation

| Flag | Default | Description |
|------|---------|-------------|
| `--bezier` | `0.25,1.0,0.5,1.0` | Cubic bezier control points for easing |
| `--anim-duration` | `600` | Animation duration in milliseconds |
| `--hyprland-conf` | *(none)* | Path to `hyprland.conf` to auto-detect bezier and duration |

### Behavior

| Flag | Default | Description |
|------|---------|-------------|
| `--hide-threshold` | `1.05` | Tape-to-viewport width ratio below which the bar hides |

### Examples

```sh
# Default green theme
hypr-scroll-indicator

# Custom colors
hypr-scroll-indicator --color-primary "#E0A0FF" --color-secondary "#A060CC"

# Use matugen dynamic colors
hypr-scroll-indicator --colors-file ~/.config/hypr/colors.conf

# Match Hyprland animation config
hypr-scroll-indicator --hyprland-conf ~/.config/hypr/hyprland.conf

# Compact bar with fast animation
hypr-scroll-indicator --bar-height 8 --margin-bottom 4 --anim-duration 300
```

## Hyprland Integration

Add to your `~/.config/hypr/hyprland.conf`:

```conf
# Layer rules
layerrule = noanim, hypr-scroll-indicator
layerrule = blur, hypr-scroll-indicator

# Autostart
exec-once = hypr-scroll-indicator
```

See [`examples/hyprland.conf`](examples/hyprland.conf) for more integration examples.

## Running Without the Wrapper

If you prefer to run the Python script directly (e.g. during development):

```sh
LD_PRELOAD=/usr/lib64/libgtk4-layer-shell.so.0 ./hypr-scroll-indicator.py
```

The library path varies by distro. Check with `find /usr -name 'libgtk4-layer-shell*'`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
