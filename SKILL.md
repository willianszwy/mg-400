---
name: nux-mg400
description: Build and load guitar tones on a NUX MG-400 multi-effects pedal over USB MIDI - pick amps, cabs (IR), drives, mods, delays, reverbs and EQ, tweak params, then save the result to a preset slot with a name. Use when the user wants a tone/preset on their MG-400 (an artist's or song's tone, "make a thrash rhythm preset", "more gain", "save it to 12A").
---

# NUX MG-400 tone builder

`scripts/mg400.py` (in this skill's directory) talks to the pedal over USB MIDI. `data/mg400.json` is the full map of blocks, models, params, CC numbers and value scales, verified on firmware V3.0.3.

## Setup (once)

```
pip install mido python-rtmidi
```

The pedal must be connected by USB. NUX QuickTone does not need to be open, and it is better **closed** while you apply tones:
- QuickTone only reads the pedal when it connects, so it does not show changes made over MIDI.
- If the user touches anything in a stale QuickTone window, it can resend its old state and undo your edits.
- To see the real state, reopen QuickTone or look at the pedal screen.
- On systems where a MIDI port can only be opened by one app at a time, QuickTone must be closed.

Check the connection with `python scripts/mg400.py ports`. Both `NUX MG-400 MIDI IN` and `MIDI OUT` should be listed.

## Workflow

1. **Understand the tone.** Ask about the guitar and pickups and the song or artist, if it isn't clear. Think about the real rig: amp, cab, pedals and their order.
2. **Look up models and params.** Do not guess names. Pick models by the real gear they are based on, which `list` shows as `<- based on`. Prefer `official` references. `inferred` ones are hints to check by ear. Some names mislead: SUPER RVB is a Fender **Super-Sonic**, not a Super Reverb, and CALI CRUNCH is a Mesa **Mark I**.
   - `python scripts/mg400.py list` lists the blocks.
   - `list AMP` lists the models in a block.
   - `list AMP "super rvb"` lists a model's params, with CCs, ranges and defaults.
3. **Write a preset JSON.** See the format below. Save it somewhere the user can reuse; `presets/` holds examples.
4. **Dry run, then apply:**
   - `python scripts/mg400.py apply preset.json --dry-run` shows every CC without sending anything.
   - `python scripts/mg400.py apply preset.json` sends it to the edit buffer. Nothing is stored yet.
5. **Iterate with the user playing.**
   - `set AMP GAIN 60 --model "SUPER RVB"` changes a single param.
   - `set IR HIGH_CUT 6.5khz` changes an IR param. IR params don't need `--model`.
   - Re-apply the JSON for bigger changes. Keep the JSON in sync with what the user liked.
6. **Save only with explicit consent.** Saving **overwrites** a slot. Ask which slot to use and confirm it may be overwritten. Run `name` first to tell the user what is in the slot now. Then:
   - `python scripts/mg400.py name` shows what is in the edit buffer now.
   - `python scripts/mg400.py save 12A --name "BLUES TX" --same-scenes --yes` saves a one-tone preset.
   - `python scripts/mg400.py save 12A --name "PROG MIX" --yes` saves a preset with a `scenes` section.
   - The pedal acknowledges each chunk.
   - Suggest a QuickTone backup (export) before overwriting presets the user cares about.
7. **Verify.** Switch to another slot and back, then run `name` to confirm the save.

Always pass `--name` when saving. The user may have switched presets on the pedal while playing, and then the edit buffer holds another slot's name and tone. Before saving, run `program SLOT` and re-apply the JSON so the buffer is certainly the tone you mean.

**Always include `PL` in full presets**, as `"PL": {"params": {"LEVEL": 50, "MIN": 25, "MAX": 100}}`. The MG-400 has a built-in expression pedal that controls volume between MIN and MAX. Factory presets can have MIN 0, which is silence with the pedal heel down, and a preset that leaves PL alone inherits it. PL is CC74 LEVEL (50 = 0 dB), CC75 MIN, and CC76 MAX (inferred).

## Preset files and names

- **Files that go to the repo** (`presets/*.json`) use **neutral codes**: initials plus a short tag, e.g. `jm_cnt`, `dg_cn`, `evh_pn_nam`.
  - Their `name` and `notes` describe the **style, era and gear**, never the artist, song or album names.
  - Gear brand and model names are fine, because they identify the MG-400's own models.
- **Names saved on the user's pedal** are the user's choice and can be anything, e.g. "VH PANAMA". Only what is committed has to stay neutral.

## Standard reply format

When you deliver a tone, always answer in the user's language with these sections, in this order. Skip a section only when it doesn't apply.

1. **Title**: `## <Artist> — <song or album> (<year>)`
2. **Original rig**: one or two lines with the real gear used on the record, and a source.
3. **On the MG-400**: a table, `real gear → MG-400 model (official/inferred reference)`.
4. **NAM capture** (when one is suggested): a table with these rows:
   - capture name and creator
   - type: Full Rig or amp only
   - downloads and favorites
   - **A2-Lite ESR** and its rating
   - calibrated or not
   - amp settings used in the capture

   After the table, give:
   - the **tone page link**
   - the **direct `.nam` link**
   - the **local file path** already downloaded with `tone3000.py`
   - the instruction: "load it in QuickTone into NAM slot N"
5. **Scenes**: a table, `SCN1 rhythm / SCN2 solo / SCN3 intro`, saying what each is for and what changes.
6. **How to play**: pickup, guitar volume and picking, in one or two lines.
7. **Status and next step**: say clearly what is **loaded but not saved**, what is **saved** (slot and name), and what you need from the user, e.g. "which slot should I save to?" or "tell me when the NAM is loaded".
8. **Sources**: markdown links for every page you used.

## Suggesting NAM captures from TONE3000

A good NAM capture of the real amp often sounds more authentic than the built-in model. When you build a tone, you can suggest one from [TONE3000](https://www.tone3000.com), the main free library of NAM captures:

1. **Identify the target amp** precisely: model, channel and mode, and roughly the settings and boosts used on the record. For example, a Dual Rectifier on the Red channel in Modern mode, pushed by a TS.
2. **Search TONE3000 ranked by popularity.** The search page is rendered with JavaScript, so WebFetch sees no results. Use a real browser (Playwright MCP, if available) on:

   ```
   https://www.tone3000.com/search?q=<amp name>&format=nam&order=downloads-all-time&architecture=2&calibrated=true
   ```

   | URL param | Values |
   |---|---|
   | `q` | search text, e.g. `dual rectifier` |
   | `order` | `downloads-all-time` (best quality proxy), `trending`, `newest`, `oldest`; omit for best match |
   | `format` | `nam` or `ir` |
   | `architecture` | `2` (A2, the current default) or `1` (legacy) |
   | `calibrated` | `true`: only captures with input/output level metadata |
   | `gears` | `amp` (head only), `amp-cab` (full rig), `pedal`, `cab` |

   Each result card shows the title, gear type, downloads and the creator. Read the top 10 and open the 2-3 best tone pages. If no browser is available, fall back to WebSearch with `site:tone3000.com <amp>`.
3. **Judge quality on the tone page, then pick 1-3 captures and explain why.** Read the description and the per-model list. Weigh these:
   - **Popularity:** downloads and favorites. Thousands of downloads and hundreds of favorites mean the community has vetted it.
   - **ESR**, the training error per model: lower is more faithful to the real amp. **Judge the `A2-Lite` ESR**, since that is the version the MG-400 runs. Lite ESR is always higher than Full: one capture showed Full 0.0097 and Lite 0.0388. For **A2-Lite: below 0.03 is excellent, 0.03-0.08 is good, above 0.12 is doubtful.** Prefer the model with the lowest Lite ESR among the settings you want.
   - **Documentation:** good creators list knob settings, the signal chain, the cab, the mic and the speaker position. Model names often encode them, e.g. `FR MBDR MW Red Mdn - 1 - 4FB LL SM57a` = full rig, setting 1, Mesa 4x12, lower-left speaker, SM57 position a.
   - **Calibrated** captures (marked `cal.`) and the epoch count (500-1000 is typical).
   - **Amp, channel and mode match**, and settings close to the record. TONE3000 names often encode knob values, e.g. `G-7 Ma-2 P-4`.
   - **Full Rig ("FR") vs amp-only ("DI").**
     - Full Rig already includes cab and mic, so the IR stays off.
     - Amp-only needs an MG-400 IR. Pick the cab from `list IR`.
     - Full Rig is simpler. DI allows choosing the cab.
   - **Compatibility.** The MG-400 runs **A2-Lite** models. This is the user's understanding from loading captures, not an official NUX statement. Tone pages list `A2-Full` and `A2-Lite` per model: tell the user to download the **A2-Lite** file, and skip tones that have no A2 version.
   - **Boosted or not.** If the capture already includes a TS or boost, don't add another drive in front.
4. **Download the file for the user, then the user loads it with QuickTone.** Uploading over MIDI is not mapped yet.
   - `python scripts/tone3000.py models <tone page URL>` lists the page's models with their **direct `.nam` links**. These are the public files behind the page's "Download Tone" button, and no login is needed.
   - `python scripts/tone3000.py download <tone page URL> --model "<part of the name>"` saves the file to `Documents/NUX/NAM downloads/<tone title>/`.
   - A2 files are a `SlimmableContainer`: Full and Lite in one file. Give the user that file; the MG-400 runs the Lite part.
   - Don't call TONE3000's internal search RPC. The official API needs the user's own key; use the browser search instead.
   - Ask which NAM slot (1-10) they loaded it into, and add it to `nam_slots.json` with the name, amp and `full_rig` flag.
5. **Build the preset around it:**
   - Set `"AMP": {"model": "NAM <slot>", ...}` with GAIN, BASS, MIDDLE, TREB and MASTER, starting at 50, since the capture already holds the amp's voicing.
   - Set IR off for Full Rig captures, or an IR for DI ones.
   - Keep the gate first.
   - Remember the preset only works on pedals with that capture in that slot. Note this in the preset's `notes`, and keep a built-in-model version when the preset is meant to be shared.

Always include the TONE3000 links you used in your reply.

## Chain order and switchable slots

**Order.** Add `"order"` with all 10 blocks to reorder the chain. The order is one per preset, shared by every scene. You can also set it live with `order GATE CMP EFX AMP IR EQ DLY MOD RVB PL`, or run `order` with no args for the default. Typical uses:
- Delay before the amp, for a dirty "in front" echo.
- MOD after DLY, for a modulated delay.
- Drive after the amp.

**Switchable slots.** Some slots can host another block type, which allows two drives or two delays. Add `"as"` to the slot:

| Slot | can become | use |
|---|---|---|
| CMP | EFX | second drive, e.g. a boost into a drive |
| MOD | EFX | second drive later in the chain |
| EFX | MOD | modulation before the amp, e.g. a Uni-Vibe in front |
| RVB | DLY | two delays. There is no way to get two reverbs: DLY has no alternate type. |

```json
"order": ["GATE", "CMP", "EFX", "AMP", "IR", "EQ", "DLY", "MOD", "RVB", "PL"],
"blocks": {
  "CMP": {"as": "EFX", "model": "HORSEMAN OD", "on": true, "params": {"GAIN": 20, "TREBLE": 55, "OUTPUT": 70}},
  "EFX": {"model": "T SCREAMER", "params": {"DRIVE": 30, "TONE": 55, "LEVEL": 75}}
}
```

- Params of the hosted model use the slot's own CCs. A model whose params do not fit the slot is rejected.
- Each slot has its own model list: the CMP slot has **no TOUCH WAH**, so later drives shift down. The tool handles this.
- Never send model CC value +32 to the DLY slot. It has no alternate type, and doing so corrupts the edit buffer: the user heard a huge, silent preset. Reload the slot to recover.

Every preset holds **3 scenes**. Each scene is a full copy of all blocks, and the user switches between them with the footswitches. `CC79` (0-2) selects the scene, and CC edits only change the **active** scene.

- **Preset without `scenes`:** `apply` writes the same tone to all 3 scenes. Save it with `--same-scenes`, which makes SCN2 and SCN3 exact copies of SCN1. Without it, SCN2 and SCN3 can keep stale sounds from whatever was in the slot before.
- **Preset with `scenes`:** `blocks` is the base. Each scene overrides blocks or params on top of the base. A block with a different model does not inherit the base params. Scenes that are not listed get the base.
- `apply preset.json --scene 2` applies only one scene. `scene 2` switches to SCN2.

```json
{
  "name": "Prog Mix",
  "blocks": { "...": "full base tone (scene 1)" },
  "scenes": {
    "2": {"blocks": {"AMP": {"params": {"GAIN": 62, "MIDDLE": 62}}, "DLY": {"model": "DIGI DELAY", "on": true}}},
    "3": {"blocks": {"AMP": {"params": {"GAIN": 80}}, "RVB": {"model": "HALL", "params": {"LEVEL": 20}}}}
  }
}
```

**Scene layout convention.** Use it for every multi-scene preset so the footswitches always mean the same thing:

| Scene | Role | Typical content |
|---|---|---|
| SCN1 | **Rhythm** (ritmo) | the base tone for chords and riffs |
| SCN2 | **Solo** | more gain, mids and volume, with delay |
| SCN3 | **Intro** | clean or ambient, with more reverb and delay and the drive off |

Put the rhythm tone in `blocks` (SCN1) and write SCN2 and SCN3 as overrides. See `presets/jm_cnt.json`.

Other commands:
- `copy 15A 2A --yes` copies a stored preset to another slot, byte for byte, with all scenes and the order. It overwrites the target, so check the target's name first and ask.
- `program 15B` switches slots. Slots run 1A..32D, or 0-127.
- `model BLOCK MODEL [--off]` selects a model.
- `onoff BLOCK on|off --model M` turns a block on or off.
- `monitor 30` prints what the pedal sends for 30 seconds.

## Preset JSON

```json
{
  "name": "Blues TX",
  "blocks": {
    "EFX": {"model": "T SCREAMER", "on": true, "params": {"DRIVE": 25, "TONE": 60, "LEVEL": 80}},
    "AMP": {"model": "SUPER RVB", "params": {"GAIN": 55, "BRIGHT": 0, "LEVEL": 70, "BASS": 45, "MIDDLE": 65, "TREB": 60}},
    "IR":  {"model": "TWEED 410", "params": {"MIC": "SM57", "LOW_CUT": "80hz", "HIGH_CUT": "7khz", "LEVEL": "0db"}},
    "EQ":  {"model": "10-EQ", "params": {"1KHZ": "+2db", "4KHZ": "-1db"}},
    "DLY": {"model": "ANALOG DELAY", "on": false},
    "RVB": {"model": "SPRING", "params": {"DECAY": 40, "LEVEL": 22}}
  }
}
```

- **Blocks:** GATE, CMP, EFX, AMP, IR, EQ, MOD, DLY, RVB, PL. The default chain order is GATE → CMP → EFX → AMP → IR → EQ → MOD → DLY → RVB → PL. Blocks left out of the JSON are not touched.
- **Model:** use the name or the number from `list`. `"on": false` sends the model in bypass. To turn a block off you must name a model, because on/off lives in the model CC.
- **Params:** plain numbers are the pedal's 0-100 values, the same numbers the pedal screen shows. Switches take 0/1, for example the AMP `BRIGHT` param. Scaled params also accept units:
  - EQ bands and EQ VOL/GAIN, and IR LEVEL, take `dB`:
    - 6-EQ: ±15 dB
    - 10-EQ and IR LEVEL: ±12 dB
  - IR `LOW_CUT` takes Hz, from 20 Hz to 1 kHz.
  - IR `HIGH_CUT` takes Hz, from 5 kHz to 20 kHz.
  - IR `MIC` takes one of `C414`, `E906`, `U87`, `SM57`.
  - IR `MIC_POS` takes one of these:
    - `EDGE`: edge of the cone, darker and smoother
    - `MIDDLE`
    - `CENTER`: center of the cone, brighter and more aggressive
- **Values are absolute.** Selecting a model resets that block to the model's defaults. Params you don't list end up at the default, not at their previous value. The tool waits for the pedal to finish loading defaults before it sends your params.
- **Selecting an AMP also switches the IR** to that amp's matching cab. The tool always sends AMP before IR, so an IR in the JSON wins.

## Known limits

- PL MAX (CC76) is inferred from the CC order and has not been checked on the pedal.
- **Always set the delay subdivision.** DIGI DELAY has `SUBDIV` (CC57) with these values, confirmed on the pedal:
  - `1/32`, `1/8T`, `1/16`, `1/4T`, `1/8`, `1/8D` (dotted eighth, the classic ambient-lead delay), `1/4`
  - The JSON accepts these names.
  - Factory presets can leave it on 1/32, which turns the repeats into a glitchy smear the user described as "bugging".
  - Use `"SUBDIV": "1/4"` unless the part asks for another value.
  - Subdivision on other delay models is not mapped yet.
- The pedal screen shows names in uppercase, and names are up to 16 ASCII characters.
- AMP models 30-32 (I DELUXE RVB, I CLASS A30, I FIREMAN) are NUX **Deep Image** amps: captures ("images") of a real Deluxe Reverb, AC30 and Friedman HBE. They are confirmed on the pedal (fw V3.0.3), and they are worth trying when the modeled version sounds off. AMP models 26-29 (MLD bass, STAGEMAN acoustic, VIVO, L STAR) come from QuickTone's tables and have not been individually checked.
- **NAM captures.** The 10 NAM slots are AMP models `NAM 1` to `NAM 10`, which is CC3 values 33-42. Their params are GAIN, BASS, MIDDLE, TREB and MASTER, on CC24-28.
  - Each pedal holds different captures. Read `nam_slots.json`, which is local and not committed (see `nam_slots.example.json`), to know what is loaded. Ask the user to fill it if it is missing.
  - When a NAM is selected, the pedal switches the IR block off by itself.
  - Full Rig captures ("FR", "Full Rig") already include the cab and mic, so keep `"IR": {"model": "...", "on": false}`. Amp-only ("DI") captures need an IR.
  - A real capture often beats the modeled amp. When the user has one of the target amp, offer it, e.g. a Dual Rectifier capture for a prog-metal rhythm.
  - Loading new NAM or IR files over MIDI is not mapped yet. The user loads them with QuickTone.
- `save` stores the current edit buffer. Make sure the buffer holds the tone you want: apply, let the user confirm, then save.
- If the USB cable drops mid-run, the result can be half-applied. You may see "No reply from pedal" or a missing port. Reconnect, re-apply the whole preset, and only then save.
- **Never run two pedal commands at the same time.** A full 3-scene `apply` takes about 30 s or more because it waits for the pedal after each model change. Give the shell a long timeout, about 5 min, and don't start another `apply` or `save` while one is still running, even one moved to the background. Two writers interleave and the saved preset can come out mixed. If a run seems stuck, check that the process is gone before retrying.

## Tone tips

- **Clean or edge-of-breakup amp plus a drive pedal as a boost**: low drive, high level. This is the Texas blues approach. Drive straight into a high-gain amp is the metal approach; tighten it with a T SCREAMER at drive 0-15 and level 80-100.
- **IR**: LOW_CUT around 70-100 Hz tightens the low end. HIGH_CUT around 6-8 kHz removes fizz.
- **Effects**: modulation, delay and reverb go after the amp, which is the default order.
- **Keep the noise gate first** in the chain (the default order). Measured on the pedal with a Big Muff, a booster and an edge-of-breakup amp, guitar volume at 0:
  - gate first: silent (-97 dBFS) from SENS 25
  - gate after the amp: about -42 dBFS of roar up to SENS 75, and it only closed at SENS 85+, which also chops sustain

  With stacked drives, also keep the booster's gain modest, because it added about 8 dB of noise.
