#!/usr/bin/python3
"""
hypr-scroll-indicator — a thin bottom bar showing viewport position on the
window tape for Hyprland's scrolling layout, like a browser scrollbar.

Uses GTK4 + gtk4-layer-shell for a pixel-perfect Wayland overlay.
Requires: LD_PRELOAD=/usr/lib64/libgtk4-layer-shell.so.0
"""

import argparse
import json
import math
import os
import signal
import socket
import threading
import time

import cairo
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gdk, GLib, Gtk, Gtk4LayerShell as LayerShell

# ── CLI ─────────────────────────────────────────────────────


def parse_args():
    p = argparse.ArgumentParser(
        description="Hyprland scroll-indicator bar",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  hypr-scroll-indicator
  hypr-scroll-indicator --bar-height 10 --margin-bottom 8
  hypr-scroll-indicator --color-primary "#91D59B" --color-secondary "#65946B"
  hypr-scroll-indicator --colors-file ~/.config/hypr/colors.conf
  hypr-scroll-indicator --hyprland-conf ~/.config/hypr/hyprland.conf
""",
    )
    # Geometry
    p.add_argument("--bar-height", type=int, default=14, help="bar height in px (default: 14)")
    p.add_argument("--thumb-radius", type=int, default=6, help="corner radius in px (default: 6)")
    p.add_argument("--thumb-inset", type=int, default=3, help="thumb inset from track edges in px (default: 3)")
    p.add_argument("--margin-bottom", type=int, default=10, help="bottom margin in px (default: 10)")
    p.add_argument("--margin-side", type=int, default=64, help="left/right margin in px (default: 64)")

    # Colors
    p.add_argument("--color-primary", type=str, default="#91D59B", help='primary/thumb color (default: "#91D59B")')
    p.add_argument("--color-secondary", type=str, default=None, help="secondary/thumb-end color (default: darkened primary)")
    p.add_argument("--color-track", type=str, default=None, help="track color (default: very dark primary)")
    p.add_argument(
        "--colors-file",
        type=str,
        default=None,
        help="path to matugen-style colors.conf (overrides --color-* flags)",
    )

    # Animation
    p.add_argument("--bezier", type=str, default="0.25,1.0,0.5,1.0", help='cubic bezier control points (default: "0.25,1.0,0.5,1.0")')
    p.add_argument("--anim-duration", type=int, default=600, help="animation duration in ms (default: 600)")
    p.add_argument(
        "--hyprland-conf",
        type=str,
        default=None,
        help="path to hyprland.conf to auto-detect bezier/duration",
    )

    # Behavior
    p.add_argument(
        "--hide-threshold",
        type=float,
        default=1.05,
        help="tape/viewport ratio below which bar hides (default: 1.05)",
    )

    return p.parse_args()


# ── Color helpers ───────────────────────────────────────────


def hex_to_rgb(h):
    """Parse '#RRGGBB' or 'RRGGBB' into (r, g, b) floats 0-1."""
    h = h.strip().lstrip("#")
    if len(h) != 6 or not all(c in "0123456789abcdefABCDEF" for c in h):
        raise ValueError(f"Invalid hex color: '{h}' (expected 6-digit hex like '#FF8800')")
    return (int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255)


def parse_hypr_colors(path):
    """Read matugen-generated colors.conf; return dict name->(r,g,b)."""
    colors = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("$") and "= rgb(" in line:
                    name, _, val = line.partition("=")
                    name = name.strip().lstrip("$")
                    hex_str = val.strip().removeprefix("rgb(").removesuffix(")")
                    colors[name] = hex_to_rgb(hex_str)
    except Exception:
        pass
    return colors


def resolve_colors(args):
    """Return (track_rgba, thumb_start_rgba, thumb_end_rgba)."""
    if args.colors_file:
        c = parse_hypr_colors(os.path.expanduser(args.colors_file))
        pr, pg, pb = c.get("primary", hex_to_rgb(args.color_primary))
        sr, sg, sb = c.get("secondary", (pr * 0.7, pg * 0.7, pb * 0.7))
    else:
        pr, pg, pb = hex_to_rgb(args.color_primary)
        if args.color_secondary:
            sr, sg, sb = hex_to_rgb(args.color_secondary)
        else:
            sr, sg, sb = pr * 0.7, pg * 0.7, pb * 0.7

    if args.color_track:
        tr, tg, tb = hex_to_rgb(args.color_track)
        track = (tr, tg, tb, 1.0)
    else:
        track = (pr * 0.15, pg * 0.15, pb * 0.15, 1.0)

    thumb_start = (pr, pg, pb, 1.0)
    thumb_end = (sr, sg, sb, 1.0)
    return track, thumb_start, thumb_end


# ── Animation helpers ───────────────────────────────────────


def parse_bezier_string(s):
    """Parse '0.25,1.0,0.5,1.0' into a 4-tuple of floats."""
    parts = [float(x.strip()) for x in s.split(",")]
    if len(parts) != 4:
        raise ValueError("bezier must have exactly 4 values")
    return tuple(parts)


def parse_bezier_from_hyprland(conf_path):
    """Read workspace animation bezier and speed from hyprland.conf."""
    try:
        beziers = {}
        ws_bezier = "default"
        ws_speed = 6
        with open(os.path.expanduser(conf_path)) as f:
            for line in f:
                line = line.strip()
                if line.startswith("bezier") and "=" in line:
                    _, _, rest = line.partition("=")
                    parts = [p.strip() for p in rest.split(",")]
                    if len(parts) == 5:
                        beziers[parts[0]] = tuple(float(x) for x in parts[1:])
                if line.startswith("animation") and "workspaces" in line:
                    parts = [p.strip() for p in line.partition("=")[2].split(",")]
                    if len(parts) >= 4:
                        ws_speed = float(parts[2])
                        ws_bezier = parts[3]
        points = beziers.get(ws_bezier, (0.25, 1.0, 0.5, 1.0))
        return points, int(ws_speed * 100)
    except Exception:
        return None, None


def resolve_animation(args):
    """Return (bezier_points, duration_ms)."""
    bezier = parse_bezier_string(args.bezier)
    duration = args.anim_duration

    if args.hyprland_conf:
        bp, dur = parse_bezier_from_hyprland(args.hyprland_conf)
        if bp is not None:
            bezier = bp
        if dur is not None:
            duration = dur

    return bezier, duration


# ── Bezier easing ───────────────────────────────────────────


def cubic_bezier_y(t, _x1, y1, _x2, y2):
    return 3 * (1 - t) ** 2 * t * y1 + 3 * (1 - t) * t**2 * y2 + t**3


def cubic_bezier_x(t, x1, x2):
    return 3 * (1 - t) ** 2 * t * x1 + 3 * (1 - t) * t**2 * x2 + t**3


def bezier_ease(progress, x1, y1, x2, y2):
    t = progress
    for _ in range(8):
        bx = cubic_bezier_x(t, x1, x2)
        dx = 3 * (1 - t) ** 2 * x1 + 6 * (1 - t) * t * (x2 - x1) + 3 * t**2 * (1 - x2)
        if abs(dx) < 1e-6:
            break
        t -= (bx - progress) / dx
        t = max(0.0, min(1.0, t))
    return cubic_bezier_y(t, x1, y1, x2, y2)


def lerp(a, b, t):
    return a + (b - a) * t


# ── Hyprland IPC ────────────────────────────────────────────


def hyprctl_sock(sock_path, cmd):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.settimeout(1)
        s.connect(sock_path)
        s.send(f"j/{cmd}".encode())
        chunks = []
        while True:
            data = s.recv(8192)
            if not data:
                break
            chunks.append(data)
    finally:
        s.close()
    return json.loads(b"".join(chunks))


def get_hypr_sock_path():
    sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "")
    runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return f"{runtime}/hypr/{sig}/.socket.sock"


def get_hypr_event_sock_path():
    sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "")
    runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    return f"{runtime}/hypr/{sig}/.socket2.sock"


# ── Application ─────────────────────────────────────────────


class ScrollIndicator:
    ANIM_TICK_MS = 16  # ~60 fps

    def __init__(self, args):
        self.args = args
        self.track_color, self.thumb_start, self.thumb_end = resolve_colors(args)
        self.bezier_points, self.anim_duration_ms = resolve_animation(args)
        self.sock_path = get_hypr_sock_path()

        self.state = None  # target (start_frac, end_frac)
        self.display_state = None  # currently rendered
        self.win = None
        self.drawing_area = None
        self.anim_id = None
        self._monitors_cache = None

    # ── Scroll state ────────────────────────────────────────

    def get_scroll_state(self):
        try:
            workspace = hyprctl_sock(self.sock_path, "activeworkspace")
        except Exception:
            return None

        if not workspace or workspace.get("tiledLayout") != "scrolling":
            return None

        ws_id = workspace["id"]
        mon_id = workspace.get("monitorID", 0)

        try:
            if self._monitors_cache is None:
                self._monitors_cache = hyprctl_sock(self.sock_path, "monitors")
            mon = next((m for m in self._monitors_cache if m["id"] == mon_id), None)
            if not mon:
                return None
            clients = hyprctl_sock(self.sock_path, "clients")
        except Exception:
            return None

        ws_wins = [
            c
            for c in (clients or [])
            if c["workspace"]["id"] == ws_id and not c["floating"] and c["mapped"] and not c["hidden"]
        ]
        if not ws_wins:
            return None

        tape_left = min(w["at"][0] for w in ws_wins)
        tape_right = max(w["at"][0] + w["size"][0] for w in ws_wins)
        tape_width = tape_right - tape_left

        scale = mon.get("scale", 1.0) or 1.0
        vp_left = mon["x"]
        vp_width = mon["width"] / scale

        if tape_width <= vp_width * self.args.hide_threshold:
            return None

        start = max(0.0, (vp_left - tape_left) / tape_width)
        end = min(1.0, start + vp_width / tape_width)
        return (start, end)

    # ── Animation ───────────────────────────────────────────

    def ease(self, progress):
        return bezier_ease(progress, *self.bezier_points)

    def start_animation(self):
        if self.anim_id is not None:
            GLib.source_remove(self.anim_id)
            self.anim_id = None

        anim_start = time.monotonic()
        origin = self.display_state

        def tick():
            if self.state is None or origin is None:
                self.anim_id = None
                return False

            elapsed = time.monotonic() - anim_start
            progress = min(1.0, elapsed / (self.anim_duration_ms / 1000))
            t = self.ease(progress)

            self.display_state = (
                lerp(origin[0], self.state[0], t),
                lerp(origin[1], self.state[1], t),
            )

            if self.drawing_area:
                self.drawing_area.queue_draw()

            if progress >= 1.0:
                self.display_state = self.state
                self.anim_id = None
                return False
            return True

        self.anim_id = GLib.timeout_add(self.ANIM_TICK_MS, tick)

    # ── Drawing ─────────────────────────────────────────────

    def draw_func(self, _area, cr, width, height):
        if not self.display_state:
            return

        start_frac, end_frac = self.display_state
        inset = self.args.thumb_inset
        radius = self.args.thumb_radius

        cr.set_operator(cairo.OPERATOR_SOURCE)

        # Track
        cr.set_source_rgba(*self.track_color)
        rounded_rect(cr, 0, 0, width, height, radius)
        cr.fill()

        # Thumb
        usable_w = width - 2 * inset
        thumb_x = inset + start_frac * usable_w
        thumb_w = max(1.0, (end_frac - start_frac) * usable_w)
        thumb_y = inset
        thumb_h = height - 2 * inset
        thumb_r = min(radius, thumb_h / 2, thumb_w / 2)

        gradient = cairo.LinearGradient(thumb_x, 0, thumb_x + thumb_w, 0)
        gradient.add_color_stop_rgba(0.0, *self.thumb_start)
        gradient.add_color_stop_rgba(1.0, *self.thumb_end)
        cr.set_source(gradient)
        rounded_rect(cr, thumb_x, thumb_y, thumb_w, thumb_h, thumb_r)
        cr.fill()

    # ── Refresh / IPC ───────────────────────────────────────

    def refresh(self):
        new_state = self.get_scroll_state()

        if self.win is None:
            return False

        if new_state:
            LayerShell.set_exclusive_zone(self.win, self.args.bar_height)
            self.win.set_visible(True)

            if self.display_state is None:
                self.display_state = new_state
                self.state = new_state
                if self.drawing_area:
                    self.drawing_area.queue_draw()
            else:
                self.state = new_state
                self.start_animation()
        else:
            self.state = None
            self.display_state = None
            LayerShell.set_exclusive_zone(self.win, 0)
            self.win.set_visible(False)

        return False

    def ipc_listener(self):
        event_sock = get_hypr_event_sock_path()
        while True:
            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.connect(event_sock)
                buf = b""
                while True:
                    data = sock.recv(4096)
                    if not data:
                        break
                    buf += data
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        event = line.decode("utf-8", errors="replace")
                        if any(
                            event.startswith(e)
                            for e in (
                                "workspace",
                                "openwindow",
                                "closewindow",
                                "movewindow",
                                "activewindow",
                                "fullscreen",
                                "monitoradded",
                                "monitorremoved",
                            )
                        ):
                            if event.startswith("monitor"):
                                self._monitors_cache = None
                            GLib.idle_add(self.refresh)
            except Exception:
                pass
            time.sleep(1)

    # ── GTK setup ───────────────────────────────────────────

    def on_activate(self, app):
        self.win = Gtk.ApplicationWindow(application=app)

        LayerShell.init_for_window(self.win)
        LayerShell.set_layer(self.win, LayerShell.Layer.OVERLAY)
        LayerShell.set_anchor(self.win, LayerShell.Edge.BOTTOM, True)
        LayerShell.set_anchor(self.win, LayerShell.Edge.LEFT, True)
        LayerShell.set_anchor(self.win, LayerShell.Edge.RIGHT, True)
        LayerShell.set_margin(self.win, LayerShell.Edge.BOTTOM, self.args.margin_bottom)
        LayerShell.set_margin(self.win, LayerShell.Edge.LEFT, self.args.margin_side)
        LayerShell.set_margin(self.win, LayerShell.Edge.RIGHT, self.args.margin_side)
        LayerShell.set_exclusive_zone(self.win, 0)
        LayerShell.set_keyboard_mode(self.win, LayerShell.KeyboardMode.NONE)
        LayerShell.set_namespace(self.win, "hypr-scroll-indicator")

        self.drawing_area = Gtk.DrawingArea()
        self.drawing_area.set_content_height(self.args.bar_height)
        self.drawing_area.set_draw_func(self.draw_func)
        self.win.set_child(self.drawing_area)

        css = Gtk.CssProvider()
        css.load_from_string("window, window.background { background: transparent; }")
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        self.win.present()
        self.refresh()

        t = threading.Thread(target=self.ipc_listener, daemon=True)
        t.start()

    def run(self):
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        signal.signal(signal.SIGTERM, signal.SIG_DFL)
        app = Gtk.Application(application_id="dev.hypr.scroll-indicator")
        app.connect("activate", self.on_activate)
        app.run(None)


# ── Geometry util ───────────────────────────────────────────


def rounded_rect(cr, x, y, w, h, r):
    r = min(r, w / 2, h / 2)
    cr.new_path()
    cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
    cr.arc(x + w - r, y + r, r, 1.5 * math.pi, 2 * math.pi)
    cr.arc(x + w - r, y + h - r, r, 0, 0.5 * math.pi)
    cr.arc(x + r, y + h - r, r, 0.5 * math.pi, math.pi)
    cr.close_path()


# ── Entry point ─────────────────────────────────────────────


def main():
    args = parse_args()
    indicator = ScrollIndicator(args)
    indicator.run()


if __name__ == "__main__":
    main()
