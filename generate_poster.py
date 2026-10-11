#!/usr/bin/env python3
"""generate_poster.py - build a 1920x1080 poster live in Photoshop via ps_bridge.

Each design step is a separate JSX command sent through the bridge, so the
poster assembles itself on screen one layer at a time:

    1. canvas      1920x1080 RGB, 72 DPI, dark solid background
    2. glow        radial gradient fill layer (violet -> transparent)
    3. shapes      cyan ring, coral accent bars, corner dots
    4. title       "AI x PHOTOSHOP BRIDGE"
    5. subtitle    "Automated via Claude Code Bridge" + footer
    6. styles      drop shadows, outer glow, opacity adjustments
    7. export      PNG + PSD into ./output

Usage:
    python3 generate_poster.py            # run with a short pause between steps
    python3 generate_poster.py --delay 0  # run as fast as possible
"""

import argparse
import os
import sys
import time

from ps_bridge import PhotoshopBridge, PhotoshopError, js_string_literal

DOC_NAME = "AI_x_Photoshop_Poster"
WIDTH, HEIGHT = 1920, 1080
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")

# Shared helpers prepended to every step. Each bridge call is stateless, so
# the helpers are re-declared each time. Action Manager code is used where
# the DOM has no equivalent (gradient fill layers, ellipse selections, layer
# effects).
PRELUDE = r"""
var DOC_NAME = "%(doc)s";
var W = %(w)d, H = %(h)d;

function rgb(r, g, b) {
    var c = new SolidColor();
    c.rgb.red = r; c.rgb.green = g; c.rgb.blue = b;
    return c;
}
function doc() {
    return app.activeDocument = app.documents.getByName(DOC_NAME);
}
function withPixels(fn) {
    var ru = app.preferences.rulerUnits, tu = app.preferences.typeUnits;
    app.preferences.rulerUnits = Units.PIXELS;
    app.preferences.typeUnits = TypeUnits.PIXELS;
    try { return fn(); }
    finally {
        app.preferences.rulerUnits = ru;
        app.preferences.typeUnits = tu;
        app.refresh();
    }
}
function cID(s) { return charIDToTypeID(s); }
function sID(s) { return stringIDToTypeID(s); }
function rgbDesc(r, g, b) {
    var c = new ActionDescriptor();
    c.putDouble(cID("Rd  "), r); c.putDouble(cID("Grn "), g); c.putDouble(cID("Bl  "), b);
    return c;
}
function newLayer(name) {
    var l = doc().artLayers.add();
    l.name = name;
    return l;
}
function rectSel(x, y, w, h) {
    doc().selection.select([[x, y], [x + w, y], [x + w, y + h], [x, y + h]]);
}
function ellipseSel(cx, cy, r) {
    var d = new ActionDescriptor(), ref = new ActionReference();
    ref.putProperty(cID("Chnl"), cID("fsel"));
    d.putReference(cID("null"), ref);
    var e = new ActionDescriptor();
    e.putUnitDouble(cID("Top "), cID("#Pxl"), cy - r);
    e.putUnitDouble(cID("Left"), cID("#Pxl"), cx - r);
    e.putUnitDouble(cID("Btom"), cID("#Pxl"), cy + r);
    e.putUnitDouble(cID("Rght"), cID("#Pxl"), cx + r);
    d.putObject(cID("T   "), cID("Elps"), e);
    d.putBoolean(cID("AntA"), true);
    executeAction(cID("setd"), d, DialogModes.NO);
}
// Apply layer effects to the active layer. opts.shadow / opts.glow are
// optional; setting effects replaces any existing ones on the layer.
function applyEffects(opts) {
    var d = new ActionDescriptor(), ref = new ActionReference();
    ref.putProperty(cID("Prpr"), cID("Lefx"));
    ref.putEnumerated(cID("Lyr "), cID("Ordn"), cID("Trgt"));
    d.putReference(cID("null"), ref);
    var fx = new ActionDescriptor();
    fx.putUnitDouble(cID("Scl "), cID("#Prc"), 100);
    if (opts.shadow) {
        var s = opts.shadow, ds = new ActionDescriptor();
        ds.putBoolean(cID("enab"), true);
        ds.putEnumerated(cID("Md  "), cID("BlnM"), cID("Mltp"));
        ds.putObject(cID("Clr "), cID("RGBC"), rgbDesc(s.color[0], s.color[1], s.color[2]));
        ds.putUnitDouble(cID("Opct"), cID("#Prc"), s.opacity);
        ds.putBoolean(cID("uglg"), false);
        ds.putUnitDouble(cID("lagl"), cID("#Ang"), s.angle);
        ds.putUnitDouble(cID("Dstn"), cID("#Pxl"), s.distance);
        ds.putUnitDouble(cID("Ckmt"), cID("#Pxl"), s.spread || 0);
        ds.putUnitDouble(cID("blur"), cID("#Pxl"), s.size);
        fx.putObject(cID("DrSh"), cID("DrSh"), ds);
    }
    if (opts.glow) {
        var g = opts.glow, gl = new ActionDescriptor();
        gl.putBoolean(cID("enab"), true);
        gl.putEnumerated(cID("Md  "), cID("BlnM"), cID("Scrn"));
        gl.putObject(cID("Clr "), cID("RGBC"), rgbDesc(g.color[0], g.color[1], g.color[2]));
        gl.putUnitDouble(cID("Opct"), cID("#Prc"), g.opacity);
        gl.putEnumerated(cID("GlwT"), cID("BETE"), cID("SfBL"));
        gl.putUnitDouble(cID("Ckmt"), cID("#Pxl"), g.spread || 0);
        gl.putUnitDouble(cID("blur"), cID("#Pxl"), g.size);
        fx.putObject(cID("OrGl"), cID("OrGl"), gl);
    }
    d.putObject(cID("T   "), cID("Lefx"), fx);
    executeAction(cID("setd"), d, DialogModes.NO);
}
""" % {"doc": DOC_NAME, "w": WIDTH, "h": HEIGHT}


STEP_CANVAS = r"""
withPixels(function () {
    // Close a previous run's poster so the script can be re-run cleanly.
    try { app.documents.getByName(DOC_NAME).close(SaveOptions.DONOTSAVECHANGES); } catch (e) {}
    var d = app.documents.add(W, H, 72, DOC_NAME, NewDocumentMode.RGB, DocumentFill.WHITE);
    d.selection.selectAll();
    d.selection.fill(rgb(10, 12, 30));          // deep midnight navy
    d.selection.deselect();
    return "canvas " + d.width.as("px") + "x" + d.height.as("px") + " @ " + d.resolution + " DPI";
});
"""

STEP_GLOW = r"""
withPixels(function () {
    doc();
    // Radial gradient fill layer: violet core fading to transparent.
    var desc = new ActionDescriptor(), ref = new ActionReference();
    ref.putClass(sID("contentLayer"));
    desc.putReference(cID("null"), ref);

    var grad = new ActionDescriptor();
    grad.putEnumerated(cID("Type"), cID("GrdT"), cID("Rdl "));
    grad.putUnitDouble(cID("Angl"), cID("#Ang"), 90);
    grad.putUnitDouble(cID("Scl "), cID("#Prc"), 130);
    grad.putBoolean(cID("Dthr"), true);          // dither to reduce banding

    var g = new ActionDescriptor();
    g.putString(cID("Nm  "), "Violet Glow");
    g.putEnumerated(cID("GrdF"), cID("GrdF"), cID("CstS"));
    g.putDouble(cID("Intr"), 4096);

    var stops = [[0, [124, 58, 237]], [4096, [10, 12, 30]]];
    var colors = new ActionList();
    for (var i = 0; i < stops.length; i++) {
        var cs = new ActionDescriptor();
        cs.putObject(cID("Clr "), cID("RGBC"), rgbDesc(stops[i][1][0], stops[i][1][1], stops[i][1][2]));
        cs.putEnumerated(cID("Type"), cID("Clry"), cID("UsrS"));
        cs.putInteger(cID("Lctn"), stops[i][0]);
        cs.putInteger(cID("Mdpn"), 50);
        colors.putObject(cID("Clrt"), cs);
    }
    g.putList(cID("Clrs"), colors);

    var alphas = [[0, 100], [4096, 0]];
    var trans = new ActionList();
    for (var j = 0; j < alphas.length; j++) {
        var ts = new ActionDescriptor();
        ts.putUnitDouble(cID("Opct"), cID("#Prc"), alphas[j][1]);
        ts.putInteger(cID("Lctn"), alphas[j][0]);
        ts.putInteger(cID("Mdpn"), 50);
        trans.putObject(cID("TrnS"), ts);
    }
    g.putList(cID("Trns"), trans);
    grad.putObject(cID("Grad"), cID("Grdn"), g);

    var layerDesc = new ActionDescriptor();
    layerDesc.putObject(cID("Type"), sID("gradientLayer"), grad);
    desc.putObject(cID("Usng"), sID("contentLayer"), layerDesc);
    executeAction(cID("Mk  "), desc, DialogModes.NO);

    var l = doc().activeLayer;
    l.name = "Violet Glow";
    l.opacity = 70;
    return "added gradient layer '" + l.name + "'";
});
"""

STEP_SHAPES = r"""
withPixels(function () {
    var d = doc();
    var cx = W / 2, cy = H / 2;

    // Cyan ring: fill a circle, then cut out a smaller concentric one.
    newLayer("Accent Ring");
    ellipseSel(cx, cy, 400);
    d.selection.fill(rgb(34, 211, 238));
    ellipseSel(cx, cy, 384);
    d.selection.clear();
    d.selection.deselect();

    // Coral accent bars framing the title.
    newLayer("Accent Bars");
    rectSel(cx - 160, 330, 320, 8);
    d.selection.fill(rgb(251, 113, 133));
    rectSel(cx - 160, 742, 320, 8);
    d.selection.fill(rgb(251, 113, 133));
    d.selection.deselect();

    // Small dot grids in two opposite corners.
    newLayer("Corner Dots");
    var corners = [[90, 90], [W - 90 - 4 * 36, H - 90 - 4 * 36]];
    for (var k = 0; k < corners.length; k++) {
        for (var row = 0; row < 5; row++) {
            for (var col = 0; col < 5; col++) {
                ellipseSel(corners[k][0] + col * 36, corners[k][1] + row * 36, 4);
                d.selection.fill(rgb(148, 163, 184));
            }
        }
    }
    d.selection.deselect();
    return "drew ring, accent bars and corner dots";
});
"""

STEP_TITLE = r"""
withPixels(function () {
    var d = doc();
    var l = d.artLayers.add();
    l.kind = LayerKind.TEXT;
    l.name = "Title";
    var t = l.textItem;
    t.contents = "AI x PHOTOSHOP BRIDGE";
    t.font = "Futura-Bold";
    t.size = 118;
    t.tracking = 40;
    t.color = rgb(255, 255, 255);
    t.justification = Justification.CENTER;
    t.position = [W / 2, 560];
    return "added title text layer";
});
"""

STEP_SUBTITLE = r"""
withPixels(function () {
    var d = doc();
    var s = d.artLayers.add();
    s.kind = LayerKind.TEXT;
    s.name = "Subtitle";
    var t = s.textItem;
    t.contents = "Automated via Claude Code Bridge";
    t.font = "AvenirNext-DemiBold";
    t.size = 46;
    t.tracking = 120;
    t.color = rgb(34, 211, 238);
    t.justification = Justification.CENTER;
    t.position = [W / 2, 660];

    var f = d.artLayers.add();
    f.kind = LayerKind.TEXT;
    f.name = "Footer";
    var ft = f.textItem;
    ft.contents = "python3 ps_bridge.py  →  osascript  →  do javascript  →  Photoshop DOM";
    ft.font = "Menlo-Regular";
    ft.size = 22;
    ft.color = rgb(148, 163, 184);
    ft.justification = Justification.CENTER;
    ft.position = [W / 2, H - 70];
    return "added subtitle and footer text layers";
});
"""

STEP_STYLES = r"""
withPixels(function () {
    var d = doc();
    d.activeLayer = d.artLayers.getByName("Title");
    applyEffects({ shadow: { color: [0, 0, 0], opacity: 75, angle: 120, distance: 10, size: 18 } });

    d.activeLayer = d.artLayers.getByName("Subtitle");
    applyEffects({ shadow: { color: [0, 0, 0], opacity: 60, angle: 120, distance: 5, size: 10 } });

    d.activeLayer = d.artLayers.getByName("Accent Ring");
    applyEffects({ glow: { color: [34, 211, 238], opacity: 65, size: 40 } });
    d.activeLayer.opacity = 85;

    d.activeLayer = d.artLayers.getByName("Accent Bars");
    applyEffects({ glow: { color: [251, 113, 133], opacity: 55, size: 20 } });

    d.artLayers.getByName("Corner Dots").opacity = 45;
    d.artLayers.getByName("Footer").opacity = 80;
    return "applied drop shadows, outer glows and opacity";
});
"""

STEP_EXPORT = r"""
withPixels(function () {
    var d = doc();
    var png = new PNGSaveOptions();
    d.saveAs(new File(%(png)s), png, true, Extension.LOWERCASE);
    var psd = new PhotoshopSaveOptions();
    psd.layers = true;
    d.saveAs(new File(%(psd)s), psd, true, Extension.LOWERCASE);
    var names = [];
    for (var i = 0; i < d.layers.length; i++) names.push(d.layers[i].name);
    return "exported PNG + PSD | layers (top to bottom): " + names.join(", ");
});
"""

STEPS = [
    ("Create 1920x1080 canvas with dark background", STEP_CANVAS),
    ("Add radial violet gradient glow", STEP_GLOW),
    ("Draw geometric accent shapes", STEP_SHAPES),
    ("Add title text layer", STEP_TITLE),
    ("Add subtitle and footer text layers", STEP_SUBTITLE),
    ("Apply layer styles and opacity", STEP_STYLES),
    ("Export PNG and PSD", STEP_EXPORT),
]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate a poster in Photoshop via ps_bridge.")
    parser.add_argument("--delay", type=float, default=1.0,
                        help="seconds to pause between steps so each is visible (default: 1)")
    args = parser.parse_args(argv)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    paths = {
        "png": js_string_literal(os.path.join(OUTPUT_DIR, "poster.png")),
        "psd": js_string_literal(os.path.join(OUTPUT_DIR, "poster.psd")),
    }

    ps = PhotoshopBridge()
    print("Connected: %s" % ps.health_check())
    for i, (label, jsx) in enumerate(STEPS, 1):
        if jsx is STEP_EXPORT:
            jsx = jsx % paths
        print("[%d/%d] %s ..." % (i, len(STEPS), label), end=" ", flush=True)
        start = time.time()
        try:
            result = ps.run(PRELUDE + jsx)
        except PhotoshopError as exc:
            print("FAILED\n  %s" % exc, file=sys.stderr)
            return 1
        print("ok (%.2fs) - %s" % (time.time() - start, result))
        if i < len(STEPS):
            time.sleep(args.delay)
    print("Done. Output written to %s" % OUTPUT_DIR)
    return 0


if __name__ == "__main__":
    sys.exit(main())
