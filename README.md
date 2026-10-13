# 🎸 NUX MG-400 × Claude Code

> **"Give me that late-70s prog anthem solo, Big Muff into a Hiwatt, save it to 1C."** Thirty seconds later it's on your pedal, with rhythm, solo and intro scenes on the footswitches.

This is a [Claude Code](https://claude.com/claude-code) skill that turns your **NUX MG-400** into a tone assistant. You describe a sound in plain words (an artist, an album, a song, or "less fizz, more mids"). Claude then:

- looks up the gear that was really used;
- maps it to the MG-400's models;
- loads the result into the pedal over USB while you play;
- tweaks it from your feedback;
- saves it to a slot with a name.

You don't need QuickTone, cables to a laptop editor, or preset menus.

## What a session looks like

```
you    › make the fuzzy outro solo tone of that 2021 soft-rock single
claude › That solo uses a Shin-ei Psychedelic Machine fuzz into a cranked small Fender,
         not his usual Dumble sound. On the MG-400: RED FUZZ (low tone) → TWEEDY → TWEED 112,
         with a honky +4 dB at 1 kHz. Loaded on SCN2. Play it.
you    › the delay is smearing
claude › Your slot still had a 1/32 delay subdivision from the factory preset. Set it to 1/4.
you    › perfect, save it to 1B
claude › Saved to 1B "FUZZ SOLO". The pedal acknowledged all 3 scenes.
```

## What it can do

| | |
|---|---|
| 🎛️ **Every block** | GATE, CMP, EFX, AMP, IR, EQ, MOD, DLY, RVB and PL: all 126 models and their params, with real units (`80hz`, `7khz`, `-3db`) |
| 🎬 **Scenes** | Three scenes per preset with a fixed layout: **SCN1 rhythm · SCN2 solo · SCN3 intro**. The footswitches mean the same thing in every preset. |
| 🔀 **Chain order** | Move blocks anywhere: delay before the amp, drive after it… |
| ➕ **Two drives / two delays** | Put a second drive in the CMP or MOD slot, or a second delay in the RVB slot |
| 🏷️ **Save & name** | Writes the slot over SysEx with a name of up to 16 characters, then reads it back to check |
| 📋 **Copy** | Move presets between slots byte for byte |
| 🧠 **NAM from TONE3000** | Finds the best-rated capture of the real amp (by downloads, A2-Lite ESR and calibration), **downloads the `.nam` for you**, and builds the preset around it. You load it into a NAM slot with QuickTone. |
| 🔎 **Real gear references** | Every model shows what it is based on, so `SUPER RVB` is a Fender **Super-Sonic** and not a Super Reverb. Taken from NUX's official model list. |

## Preset library

Built and tuned on a real pedal, by ear, with the guitarist in the loop:

| Preset | Gear on the MG-400 | Scenes |
|---|---|---|
| `jm_cnt` · 2000s blues-pop | Vibro-King, Horseman OD (Klon), TS808 | rhythm · solo · intro |
| `jm_igf` · 80s-flavoured soft rock | Deluxe Reverb + ST Singer (Dumble), fuzz solo | rhythm · fuzz solo · intro |
| `dg_cn` · late-70s prog anthem lead | Hiwatt, Dyna Comp, Big Muff + RC Boost | rhythm · solo · intro |
| `dg_soy` · 70s British prog lead | Hiwatt, Dyna Comp, Power Boost, Tape Echo | one tone |
| `mtl_fw` · early-80s thrash | JCM800 + TS808, 1960 4x12 | rhythm · solo · intro |
| `srv_se` · Texas blues shuffle | Twin + ST Singer (Dumble) + TS808 | rhythm · solo · intro |
| `jp_mix` · prog metal multi-tone | Dual Rectifier, V-shaped EQ | three tones in one preset |
| `jp_aw` · mid-90s dark prog metal | Dual Rect + Mark-style EQ, JC clean | rhythm · solo · intro |
| `jp_sf` · late-90s prog metal | Dual Rect + Mark-style EQ, JC clean | rhythm · solo · intro |
| `evh_pn_nam` · early-80s brown sound | 1968 Super Lead **NAM capture**, RC BST, tape echo | rhythm · solo · intro |
| `evh_un_nam` · darker brown sound + flanger | Super Lead NAM, flanger **before** the amp | rhythm · solo · intro |

The presets are plain JSON files in [`presets/`](presets/), so they are easy to read, diff and share.

## Install

```bash
pip install mido python-rtmidi
git clone https://github.com/willianszwy/mg-400 ~/.claude/skills/nux-mg400
```

On Windows, clone it to `%USERPROFILE%\.claude\skills\nux-mg400`.

Then connect the MG-400 by USB, open Claude Code and ask for a tone. **Keep QuickTone closed while Claude works.** QuickTone doesn't see MIDI edits, and a stale QuickTone window can push old settings back to the pedal.

> ⚠️ Saving overwrites the slot. Claude reads the slot's current name and asks before saving. Still, export a backup in QuickTone first if you care about your presets.

## Command line

Claude drives this tool for you, but you can also use it directly:

```bash
python scripts/mg400.py list AMP                          # 32 amps, each with its real-world reference
python scripts/mg400.py list EFX "t screamer"             # params, CCs, ranges, defaults
python scripts/mg400.py apply presets/srv_se.json # load all 3 scenes into the edit buffer
python scripts/mg400.py set IR HIGH_CUT 7khz              # tweak one param live
python scripts/mg400.py set CMP GAIN 30 --as EFX --model "RC BST"   # param of a drive placed in the CMP slot
python scripts/mg400.py scene 2                           # jump to the solo scene
python scripts/mg400.py order GATE CMP EFX AMP IR EQ DLY MOD RVB PL
python scripts/mg400.py save 2B --name "TX SHUFFLE" --yes
python scripts/mg400.py copy 15A 2A --yes
```

See [SKILL.md](SKILL.md) for the preset JSON format, scenes and every option.

## Under the hood

NUX doesn't publish the MG-400's MIDI protocol. Everything here was **reverse-engineered on a real pedal** (firmware V3.0.3):

- listening to the pedal's MIDI output;
- USB captures of QuickTone (USBPcap);
- the model tables embedded in QuickTone;
- recording the pedal's audio output to measure noise.

The protocol works like this:

| What | How |
|---|---|
| Select a model | the block's type CC = model number. **+64** bypasses the block, **+32** selects the slot's alternate block type |
| Params | each block has a base CC, and its params follow from there (CMP 14, EFX 18, AMP 24, EQ 32, GATE 44, MOD 48, DLY 54, RVB 62, IR 66, PL 74) |
| Scenes | **CC79** = 0-2. CC edits only change the active scene |
| Chain order | SysEx `F0 43 58 70 0D 01 <10 block ids> 00 00 F7` |
| Read / save | SysEx `0C` (edit buffer) and `0B` (slots): 3 chunks of 219 bytes, one per scene, with the name packed as 2 chars per 3 bytes |

Some lessons learned the hard way are written into the skill so Claude doesn't repeat them:

- **The noise gate must stay first in the chain.** Measured with a Big Muff and a boost, the result was silence instead of a -42 dBFS roar.
- **PL MIN 0 makes a preset silent** when the built-in expression pedal is heel-down.
- **Factory presets can leave a 1/32 delay subdivision**, which smears repeats.
- **Your amp choice wins.** When a model sounds wrong to you, Claude switches it. The amp model's name alone doesn't decide.

## Disclaimer

This project is not affiliated with NUX / Cherub Technology. Model names are used only to identify the pedal's own presets. Use it at your own risk.
