"""Static gate for the Hot Potato in-game settings panel (v2.2, 2026-08-29).

The panel is a stock-style BeamNG UI app shipped at the ZIP ROOT
(ui/modules/apps/hotPotatoTuner/) via the SHIP_ROOT_ASSETS mechanism this
round added to prop_builder. Its controls are built at runtime from the GE
extension's hotPotatoGetOptionSchema hook, so OPTION_RANGE stays the single
source of truth — which leaves exactly three drift surfaces for a static
gate to pin:

- the authored files are valid (app.json parses and carries the fields the
  game's app scanner reads),
- the staging law holds (every SHIP_ROOT_ASSETS source exists, every
  destination is in the built mod tree AND in the shipped zip), and
- every extension hook the JavaScript calls actually exists in the shipped
  runtime.lua, under the DOUBLED extension name BeamNG resolves.
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
import subprocess
import sys
import zipfile
from html.parser import HTMLParser
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PACK_ROOT = REPO / "examples" / "giant_props"
MOD_DIR = PACK_ROOT / "hot_potato"


def _spec():
    if str(PACK_ROOT) not in sys.path:
        sys.path.insert(0, str(PACK_ROOT))
    location = MOD_DIR / "spec.py"
    loader = importlib.util.spec_from_file_location("hot_potato_spec_uiapp", location)
    module = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(module)
    return module


def test_app_json_is_a_valid_app_manifest():
    manifest = json.loads(
        (MOD_DIR / "assets" / "ui" / "hotPotatoTuner" / "app.json").read_text(
            encoding="utf-8"
        )
    )
    # The fields the game's UI app scanner actually reads (stock app.json
    # shape: simpleGear et al.).
    for key in ("name", "directive", "domElement", "css", "version", "author"):
        assert key in manifest, f"app.json lacks {key}"
    assert manifest["directive"] == "hotPotatoTuner"
    assert "hot-potato-tuner" in manifest["domElement"]
    # v2.3: a real category so the app browser files it with the stock apps
    # instead of under "unknown" (ui/apps.lua defaults absent types there).
    assert manifest.get("types") == ["ui.apps.categories.utility"]
    # v2.4, measured against the Add-App browser's actual backend
    # (ui/appSelector/general.lua): "category" names the grid group
    # (unknown strings land in a stray group at the bottom), isAuxiliary
    # true would HIDE the app behind a default-off display option, and
    # "interactive" earns the mouse badge for the literal strings
    # yes/required. "preserveSpace" appears nowhere in the game source and
    # is gone.
    assert manifest.get("category") in {
        "Dashboard", "Telemetry", "General", "Gameplay", "Debug"
    }
    assert manifest.get("isAuxiliary") is False
    assert manifest.get("interactive") in {"yes", "required"}
    assert "preserveSpace" not in manifest
    # The browser tile: without app.png the grid shows the generic
    # appDefault.png — part of why the player could not find the app.
    icon = MOD_DIR / "assets" / "ui" / "hotPotatoTuner" / "app.png"
    assert icon.is_file() and icon.stat().st_size > 1000


def test_ship_root_assets_exist_and_are_staged_and_shipped():
    spec = _spec()
    entries = getattr(spec, "SHIP_ROOT_ASSETS", ())
    assert entries, "the settings panel entries vanished from SHIP_ROOT_ASSETS"
    archive = MOD_DIR / "dist" / spec.ZIP_BASENAME
    members = set(zipfile.ZipFile(archive).namelist())
    for source_rel, dest_rel in entries:
        source = MOD_DIR / "assets" / source_rel
        assert source.is_file(), f"SHIP_ROOT_ASSETS source missing: {source}"
        staged = MOD_DIR / "mod" / dest_rel
        assert staged.is_file(), f"not staged into mod/: {dest_rel}"
        assert staged.read_bytes() == source.read_bytes(), (
            f"staged copy differs from authored source: {dest_rel}"
        )
        zip_member = dest_rel.replace("\\", "/")
        assert zip_member in members, f"not in the shipped zip: {zip_member}"


def test_the_directive_injects_only_angular_builtins():
    # v2.4.3, the blank-panel bug: bngApi exists ONLY as a window global in
    # the 0.38 Vue shell (ui/lib/int/vueService.js: window.bngApi =
    # window.bridge.api) — it was never registered as an Angular service.
    # A DI token for it throws "Unknown provider: bngApiProvider" at
    # instantiation and the placed app renders as an empty box. Working mod
    # apps (jump-button) use the bare global. So: every DI token in the
    # directive's annotation array must be an Angular built-in ($-prefixed).
    app_js = (MOD_DIR / "assets" / "ui" / "hotPotatoTuner" / "app.js").read_text(
        encoding="utf-8"
    )
    match = re.search(
        r"directive\('hotPotatoTuner',\s*\[(.*?)function", app_js, re.S
    )
    assert match, "cannot find the directive's DI annotation array"
    tokens = re.findall(r"['\"]([^'\"]+)['\"]", match.group(1))
    assert tokens, "the annotation array lost its explicit DI tokens"
    for token in tokens:
        assert token.startswith("$"), (
            f"DI token {token!r} is not an Angular built-in — the Vue shell "
            "provides no such service and the app will render blank"
        )
    # And the code still reaches the engine: through the global, not DI.
    assert "bngApi.engineLua" in app_js


def test_the_directive_instantiates_under_the_vue_shell_contract(tmp_path):
    # v2.4.3, the executable version of the DI pin: load the REAL app.js in
    # Node under a faithful stub of the 0.38 Vue shell — bngApi exists only
    # as a window global, and DI can resolve ONLY Angular built-ins — then
    # instantiate the directive factory and run its link function. The
    # pre-fix code dies here with the player's exact failure ("Unknown
    # provider: bngApiProvider"); anything that compiles and links under
    # this harness survives the real shell's mount path.
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed; the JS instantiation gate needs it")
    harness = tmp_path / "harness.js"
    harness.write_text(
        """
'use strict';
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const registered = {};
global.angular = { module: () => ({
  directive: (name, factory) => { registered[name] = factory; },
})};
// The shell's real surface: bngApi is a WINDOW GLOBAL, never a provider.
global.window = global;
global.bngApi = { engineLua: function () {} };
const providers = {
  '$interval': Object.assign(function (fn, ms) { return { fn, ms }; },
                             { cancel: function () {} }),
  '$timeout': Object.assign(function (fn) { return 0; },
                            { cancel: function () {} }),
};
function fail(why) { console.log(JSON.stringify({ ok: false, why })); process.exit(0); }
try { eval(src); } catch (e) { fail('app.js failed to evaluate: ' + e); }
const entry = registered['hotPotatoTuner'];
if (!entry) fail('directive hotPotatoTuner never registered');
const arr = Array.isArray(entry) ? entry : [entry];
const factory = arr[arr.length - 1];
const args = [];
for (const token of arr.slice(0, -1)) {
  if (!(token in providers)) fail('Unknown provider: ' + token + 'Provider');
  args.push(providers[token]);
}
let ddo;
try { ddo = factory.apply(null, args); } catch (e) { fail('factory threw: ' + e); }
if (!ddo || typeof ddo.link !== 'function') fail('no link function');
if (typeof ddo.templateUrl !== 'string') fail('no templateUrl');
const scope = {
  $on: function () {}, $evalAsync: function (f) { if (f) f(); },
  $applyAsync: function (f) { if (f) f(); },
};
try { ddo.link(scope); } catch (e) { fail('link threw: ' + e); }
console.log(JSON.stringify({ ok: true, templateUrl: ddo.templateUrl }));
""",
        encoding="utf-8",
    )
    app_js = MOD_DIR / "assets" / "ui" / "hotPotatoTuner" / "app.js"
    result = subprocess.run(
        [node, str(harness), str(app_js)],
        capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stderr
    verdict = json.loads(result.stdout.strip())
    assert verdict.get("ok") is True, verdict
    assert verdict["templateUrl"] == "/ui/modules/apps/hotPotatoTuner/app.html"


def test_app_html_has_one_root_element_for_replace_true():
    # replace:true requires exactly one root element; Angular throws at
    # $compile otherwise and the placed app renders blank.
    html = (MOD_DIR / "assets" / "ui" / "hotPotatoTuner" / "app.html").read_text(
        encoding="utf-8"
    )

    class RootCounter(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.depth = 0
            self.roots = 0

        def handle_starttag(self, tag, attrs):
            if self.depth == 0:
                self.roots += 1
            if tag not in ("input", "br", "img", "hr", "meta", "link"):
                self.depth += 1

        def handle_endtag(self, tag):
            if tag not in ("input", "br", "img", "hr", "meta", "link"):
                self.depth -= 1

    counter = RootCounter()
    counter.feed(html)
    assert counter.roots == 1, f"app.html has {counter.roots} root elements"


def test_shipped_hud_layout_puts_the_app_in_the_layouts_list():
    # v2.4.2, measured against the game's ui/appLayouts.lua: the HUD
    # Layouts list is fed by getAvailableLayouts(), which re-scans the
    # virtual /settings/ui_apps/originalLayouts/ on every call — no cache —
    # and mod zips overlay that VFS root. Shipping this file means the
    # player picks "Hot Potato" from the layouts list they already found,
    # instead of digging through a layout's Add App browser.
    raw = (
        MOD_DIR / "assets" / "ui" / "hotPotatoTuner" / "hot_potato.uilayout.json"
    ).read_bytes()
    assert b"\r" not in raw, "layout file must ship LF-only"
    layout = json.loads(raw.decode("utf-8"))
    assert layout["title"] == "Hot Potato"
    # Type "freeroam" makes it selectable for freeroam sessions; the
    # filename stem "hot_potato" != "freeroam" keeps the STOCK layout the
    # type default (findDefaultLayoutByType prefers stem == type), so
    # installing the mod never hijacks anyone's HUD uninvited.
    assert layout["type"] == "freeroam"
    assert isinstance(layout.get("version"), (int, float))
    apps = {entry["appName"]: entry for entry in layout["apps"]}
    assert "hotPotatoTuner" in apps, "the layout must actually place the tuner"
    tuner = apps["hotPotatoTuner"]
    assert isinstance(tuner.get("appVersion"), int), (
        "appVersion drives the game's original->user layout merge; without "
        "it a future update never propagates into saved user copies"
    )
    assert "placement" in tuner
    # Every other app must be a stock freeroam app (copied verbatim from
    # the game's freeroam.uilayout.json) — a typo'd appName renders as a
    # dead placeholder box in game.
    stock = {
        "damageApp", "tacho2", "simplePowertrainControl", "inputHints",
        "topLeftApps", "topCenterApps",
    }
    assert set(apps) - {"hotPotatoTuner"} <= stock
    # And the staging law covers it: it must ride SHIP_ROOT_ASSETS to
    # settings/ui_apps/originalLayouts/ at the ZIP ROOT.
    spec = _spec()
    dests = {dest for _, dest in getattr(spec, "SHIP_ROOT_ASSETS", ())}
    assert "settings/ui_apps/originalLayouts/hot_potato.uilayout.json" in dests


def test_every_hook_the_panel_calls_exists_in_the_shipped_runtime():
    app_js = (MOD_DIR / "assets" / "ui" / "hotPotatoTuner" / "app.js").read_text(
        encoding="utf-8"
    )
    runtime = (
        MOD_DIR / "mod" / "lua" / "ge" / "extensions" / "ericrolph_hot_potato"
        / "runtime.lua"
    ).read_text(encoding="utf-8")
    # The doubled extension name is load-bearing: BeamNG doubles literal
    # underscores when it resolves lua/ge/extensions paths.
    assert "extensions.ericrolph__hot__potato_runtime" in app_js
    hooks = set(re.findall(r"EXT \+ '\.(\w+)\(", app_js)) | set(
        re.findall(r"engineLua\(EXT \+ '\.(\w+)\(", app_js)
    )
    assert "hotPotatoGetOptionSchema" in hooks, (
        "the panel no longer builds itself from the schema hook"
    )
    assert "hotPotatoGetStats" in hooks, (
        "the HUD readout no longer polls the stats hook"
    )
    for hook in sorted(hooks):
        assert f"{hook} = function" in runtime, (
            f"app.js calls {hook} but the shipped runtime does not export it"
        )
