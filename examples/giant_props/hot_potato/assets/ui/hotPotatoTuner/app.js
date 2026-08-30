// Hot Potato — in-game HUD app for the Hot Potato prop.
//
// Two faces in one panel (v2.3): a live STATUS readout polled from the
// runtime's hotPotatoGetStats hook (who is hot, fuse urgency — the numeric
// countdown only when the show_countdown option allows it — and the wins
// ledger toward Champion of the Arch), and the TUNING drawer, whose
// controls are built FROM the runtime (hotPotatoGetOptionSchema returns
// OPTION_RANGE as {key: {kind, min, max, values}}), so the Lua table stays
// the single source of truth: a new option lands here with no app change.
// Values round-trip through hotPotatoGetOptions/hotPotatoSetOption, which
// clamp, persist to settings/ericrolph_hot_potato.json and apply on the
// next tick. BeamNG doubles literal underscores in extension names, hence
// ericrolph__hot__potato_runtime.
// v2.4.3, measured in the 0.38 UI source: bngApi is ONLY a window global
// (ui/lib/int/vueService.js sets window.bngApi = window.bridge.api) — it is
// never registered as an Angular service. Injecting 'bngApi' via DI throws
// "Unknown provider: bngApiProvider" the moment the directive is
// instantiated, the $compile dies, and the placed app renders as an EMPTY
// BOX (the 2026-08-29 player report). Working mod apps (jump-button) use
// the bare global; so do we. Only Angular built-ins ($interval) may be
// injected here — the static gate pins this.
// v2.5, two more measured shell laws (the 2026-08-30 player report):
// - The legacy app shell ships AngularJS 1.5.8 (ui/lib/ext/angular), and
//   ngModel support for input[type=range] only exists from Angular 1.6 —
//   under 1.5.8 a range input falls back to the TEXT binding, which writes
//   the dragged value into the model as a STRING. The paired number input
//   then throws ngModel:numfmt and its view freezes: the slider moved, the
//   engine got the value, the box stayed stale. Sliders therefore bind by
//   hand (the hptSlider directive below) and the model stays a Number.
// - NO stock legacy app uses a native <select> anywhere in ui/modules/apps:
//   the game's offscreen CEF never renders the dropdown popup (the player's
//   "clicking it doesn't drop down any further options"). Enums render as
//   segmented buttons instead.
angular.module('beamng.apps').directive('hotPotatoTuner', ['$interval', function ($interval) {
  'use strict';

  var EXT = 'extensions.ericrolph__hot__potato_runtime';
  var POLL_MS = 500;

  // Known keys get human names and a section; anything the schema sends
  // that is not listed lands in "Other" so the panel never hides an option.
  var SECTIONS = [
    { title: 'Game mode', keys: ['game_mode', 'hoard_target_points'] },
    { title: 'Fuse', keys: ['fuse_base_seconds', 'fuse_sigma_seconds', 'fuse_min_seconds', 'fuse_max_seconds', 'grace_seconds', 'camp_burn_multiplier', 'camp_speed_kmh', 'show_countdown'] },
    { title: 'Transfer', keys: ['transfer_mode', 'touch_margin', 'radius_m', 'impact_kmh', 'tagback_immunity_seconds', 'tagback_min_hold_seconds', 'tagback_separation_m', 'join_immunity_seconds', 'min_players', 'pass_knockback_mps'] },
    { title: 'Pickup & carry', keys: ['pickup_radius', 'pickup_height', 'carrier_boost_mps2', 'carrier_boost_max_mps', 'carry_clearance_m', 'bounce_enabled', 'bounce_amplitude_m', 'attach_sink', 'attach_wobble'] },
    { title: 'Audio cues', keys: ['audio_enabled', 'audio_volume', 'tick_style', 'silence_gap_seconds', 'steam_hiss_enabled', 'whistle_enabled', 'whistle_volume', 'cue_window_seconds', 'beep_slow_interval', 'beep_fast_interval', 'beep_pitch_rise'] },
    { title: 'AI drivers', keys: ['ai_enabled', 'ai_aggression', 'ai_speed_kmh'] },
    { title: 'Beacon & glow', keys: ['beacon_enabled', 'glow_ramp_enabled', 'beacon_brightness', 'beacon_radius', 'beacon_ray_range', 'beacon_pulse_seconds', 'beacon_spin_rate'] },
    { title: 'Detonation', keys: ['detonate_enabled', 'detonate_break', 'detonate_crush', 'detonate_fire', 'detonate_launch_mps', 'crush_dv_mps', 'crush_min_z', 'crush_inward', 'blast_radius_m', 'blast_push_mps', 'fire_seconds', 'mash_enabled', 'mash_seconds'] },
    { title: 'Pacing & show', keys: ['round_idle_seconds', 'wins_to_champion', 'fireworks_enabled', 'smoke_enabled', 'spin_rate', 'bob_amplitude', 'bob_rate', 'safety_enabled', 'safety_extent_max'] }
  ];

  // The hardcore preset (one button, five options): the tick plays steady —
  // no audio, light, bounce or HUD tell that the end is near. Silence is
  // the only warning you get, and you do not get it.
  var HARDCORE = {
    tick_style: 'steady', show_countdown: false, glow_ramp_enabled: false,
    bounce_enabled: false, beacon_enabled: false
  };
  var CLASSIC = {
    tick_style: 'escalating', show_countdown: false, glow_ramp_enabled: true,
    bounce_enabled: true, beacon_enabled: true
  };

  function label(key) {
    return key.replace(/_/g, ' ').replace(/\bmps2\b/, 'm/s²')
      .replace(/\bmps\b/, 'm/s').replace(/\bkmh\b/, 'km/h')
      .replace(/\bm\b$/, 'metres');
  }

  // bngApi.engineLua hands the callback whatever the Lua expression
  // returned; wrapping in jsonEncode makes that a JSON string on every
  // engine build, and the parse below tolerates either shape.
  function luaCall(expr, done) {
    bngApi.engineLua('jsonEncode(' + expr + ')', function (resp) {
      var data = resp;
      if (typeof resp === 'string') {
        try { data = JSON.parse(resp); } catch (e) { data = null; }
      }
      done(data || null);
    });
  }

  return {
    templateUrl: '/ui/modules/apps/hotPotatoTuner/app.html',
    replace: true,
    restrict: 'EA',
    scope: true,
    link: function (scope) {
      scope.sections = [];
      scope.missing = false;
      scope.showTuning = false;
      scope.status = { phase: 'none', banner: 'Waiting for the Hot Potato prop…', wins: [] };

      function slider(key, spec, value) {
        var range = (spec.max - spec.min) || 1;
        return {
          key: key,
          label: label(key),
          kind: spec.kind,
          min: spec.min,
          max: spec.max,
          // Fine steps on small ranges, whole numbers on big ones.
          step: range <= 2 ? 0.01 : (range <= 30 ? 0.1 : 1),
          values: spec.values || [],
          value: value
        };
      }

      function build(schema, values) {
        var placed = {};
        var sections = [];
        SECTIONS.forEach(function (section) {
          var controls = [];
          section.keys.forEach(function (key) {
            if (!schema[key]) { return; }
            controls.push(slider(key, schema[key], values[key]));
            placed[key] = true;
          });
          if (controls.length) { sections.push({ title: section.title, controls: controls }); }
        });
        var leftovers = Object.keys(schema).filter(function (key) { return !placed[key]; }).sort();
        if (leftovers.length) {
          sections.push({
            title: 'Other',
            controls: leftovers.map(function (key) { return slider(key, schema[key], values[key]); })
          });
        }
        scope.$evalAsync(function () { scope.sections = sections; scope.missing = false; });
      }

      function digestStats(data) {
        var status = { phase: 'none', banner: 'Waiting for the Hot Potato prop…', wins: [], scores: [] };
        if (data && data.phase) {
          status.phase = data.phase;
          status.urgency = Number(data.urgency) || 0;
          status.countdown = (typeof data.countdown === 'number' && data.countdown >= 0)
            ? Math.ceil(data.countdown) : null;
          status.transfers = Number(data.transfers) || 0;
          status.wins = (data.wins && data.wins.length) ? data.wins : [];
          status.winsTarget = Number(data.wins_to_champion) || 0;
          status.isPlayer = data.carrier_is_player === true;
          status.gameMode = data.game_mode || 'classic';
          status.hoarder = status.gameMode === 'hoarder';
          status.scores = (data.scores && data.scores.length) ? data.scores : [];
          status.hoardTarget = Number(data.hoard_target) || 0;
          if (data.phase === 'live') {
            if (status.hoarder) {
              status.banner = status.isPlayer
                ? 'YOU ARE EARNING — hold on!'
                : ((data.carrier_name || 'someone') + ' is hoarding');
            } else {
              status.banner = status.isPlayer
                ? 'YOU ARE HOT — pass it on!'
                : ((data.carrier_name || 'someone') + ' is hot');
            }
          } else if (data.phase === 'boom') {
            status.banner = 'BOOM!';
          } else if (data.phase === 'return') {
            status.banner = 'The potato returns to its perch…';
          } else {
            status.banner = 'Potato at the arch — drive the medallion';
          }
        }
        scope.$evalAsync(function () { scope.status = status; });
      }

      var poller = $interval(function () {
        luaCall(EXT + '.hotPotatoGetStats()', digestStats);
      }, POLL_MS);
      scope.$on('$destroy', function () { $interval.cancel(poller); });

      scope.refresh = function () {
        luaCall(EXT + '.hotPotatoGetOptionSchema()', function (schema) {
          if (!schema) { scope.$evalAsync(function () { scope.missing = true; }); return; }
          luaCall(EXT + '.hotPotatoGetOptions()', function (values) {
            build(schema, values || {});
          });
        });
      };

      scope.toggleTuning = function () {
        scope.showTuning = !scope.showTuning;
        if (scope.showTuning) { scope.refresh(); }
      };

      scope.apply = function (control) {
        var value = control.value;
        if (control.kind === 'number') { value = Number(value); if (isNaN(value)) { return; } }
        var encoded = control.kind === 'enum' ? JSON.stringify(String(value)) : JSON.stringify(value);
        bngApi.engineLua(EXT + '.hotPotatoSetOption(' + JSON.stringify(control.key) + ', ' + encoded + ')');
      };

      // Enum controls are segmented buttons (v2.5): the offscreen CEF never
      // renders a native select popup, so a click picks directly.
      scope.choose = function (control, option) {
        control.value = option;
        scope.apply(control);
      };

      scope.reset = function () {
        bngApi.engineLua(EXT + '.hotPotatoResetOptions()');
        scope.refresh();
      };

      function applyPreset(preset) {
        Object.keys(preset).forEach(function (key) {
          bngApi.engineLua(EXT + '.hotPotatoSetOption(' + JSON.stringify(key)
            + ', ' + JSON.stringify(preset[key]) + ')');
        });
        scope.refresh();
      }
      scope.hardcore = function () { applyPreset(HARDCORE); };
      scope.classicCues = function () { applyPreset(CLASSIC); };

      scope.refresh();
    }
  };
}]);

// The slider binding, by hand (v2.5). Angular 1.5.8 has no input[range]
// ngModel support (added in 1.6): under the text-binding fallback a drag
// writes a STRING into the model and the paired number input dies on
// ngModel:numfmt. This directive owns both directions itself — model to
// element on $watch, element to model as parseFloat on the 'input' event —
// so the shared control.value is always a Number and the number box tracks
// the slider live. The engine apply debounces so a drag lands once.
// Registered as its own statement (no chaining): only Angular built-ins in
// the DI array, same law as above.
angular.module('beamng.apps').directive('hptSlider', ['$timeout', function ($timeout) {
  'use strict';
  return {
    restrict: 'A',
    link: function (scope, element, attrs) {
      var el = element[0];
      var control = scope.$eval(attrs.hptSlider);
      if (!control) { return; }
      // min/max/step before value, so the browser clamps against the real
      // range instead of its 0..100 default.
      el.min = control.min;
      el.max = control.max;
      el.step = control.step;
      el.value = control.value;
      var pending = null;
      el.addEventListener('input', function () {
        var value = parseFloat(el.value);
        if (isNaN(value)) { return; }
        scope.$applyAsync(function () {
          control.value = value;
          if (pending) { $timeout.cancel(pending); }
          pending = $timeout(function () {
            pending = null;
            scope.apply(control);
          }, 150);
        });
      });
      // The number box (or a Refresh) moved the model: track it.
      scope.$watch(function () { return control.value; }, function (value) {
        if (typeof value === 'number' && value !== parseFloat(el.value)) {
          el.value = value;
        }
      });
      scope.$on('$destroy', function () {
        if (pending) { $timeout.cancel(pending); }
      });
    }
  };
}]);
