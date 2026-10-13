#!/usr/bin/env python3
"""Control a NUX MG-400 over USB MIDI.

Commands:
  ports                               list MIDI ports
  list [BLOCK [MODEL]]                show blocks, models of a block, or params of a model
  apply PRESET.json [--dry-run] [--scene N]  send a preset (all 3 scenes) to the edit buffer
  scene N                             switch to scene 1-3 (CC79); CC edits only change the active scene
  order [BLOCK ...]                   set the chain order (all 10 blocks; no args = default order)
  model BLOCK MODEL [--off]           select a model in a block (resets its params to defaults)
  onoff BLOCK on|off                  switch a block on or off (needs the current model, given with --model)
  set BLOCK PARAM VALUE [--model M]   set one param; VALUE is 0-100 or with a unit: 80hz, 7khz, -3db
  program SLOT                        switch to preset slot (e.g. 15B, or 0-based number 57)
  name                                print the name of the preset in the edit buffer
  save SLOT [--name NAME] [--same-scenes] --yes
                                      write the edit buffer to SLOT (OVERWRITES it), optionally renamed;
                                      --same-scenes copies SCN1 into SCN2/SCN3 for one-tone presets
  copy SRC DST --yes                  copy a stored preset to another slot (OVERWRITES DST), byte for byte
  monitor [SECONDS]                   print what the pedal sends

CC edits only change the edit buffer; use `save` (or save on the pedal) to keep them.
"""
import argparse, json, math, os, re, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
MAP = json.load(open(os.path.join(HERE, "..", "data", "mg400.json"), encoding="utf-8"))
# Local, per-pedal description of the loaded NAM captures (not committed): show it on the NAM slots.
_nam_path = os.path.join(HERE, "..", "nam_slots.json")
if os.path.exists(_nam_path):
    for _slot, _info in json.load(open(_nam_path, encoding="utf-8-sig")).items():
        if _slot.isdigit() and str(32 + int(_slot)) in MAP["models"]["AMP"]:
            _m = MAP["models"]["AMP"][str(32 + int(_slot))]
            _m["based_on"] = f"{_info.get('name')} - {_info.get('amp', '')}{' (full rig: keep IR off)' if _info.get('full_rig') else ''}"
BLOCKS = MAP["blocks"]
OFF = MAP["midi"]["bypass_offset"]
CH = MAP["midi"]["channel"]
SEND_ORDER = ["CMP", "EFX", "AMP", "IR", "EQ", "GATE", "MOD", "DLY", "RVB", "PL"]  # AMP before IR: amp change resets cab


def norm(s):
    return re.sub(r"[^A-Z0-9]", "", str(s).upper())


def find_model(block, model):
    models = MAP["models"].get(block, {})
    if str(model).isdigit() and str(model) in models:
        return int(model), models[str(model)]
    for num, m in models.items():
        if norm(m["name"]) == norm(model):
            return int(num), m
    hits = [(n, m) for n, m in models.items() if norm(model) in norm(m["name"])]
    if len(hits) == 1:
        return int(hits[0][0]), hits[0][1]
    names = ", ".join(f"{n}:{m['name']}" for n, m in models.items())
    sys.exit(f"Unknown {block} model '{model}'. Options: {names}")


def params_for(block, model_info):
    if "params" in BLOCKS[block]:
        return BLOCKS[block]["params"]
    return model_info["params"] if model_info else []


def find_param(block, model_info, pname):
    plist = params_for(block, model_info)
    for p in plist:
        if norm(p["name"]) == norm(pname):
            return p
    # EQ bands may be written as "1K", "1KHZ", "1000"
    if block == "EQ":
        want = norm(pname).replace("HZ", "")
        for p in plist:
            n = norm(p["name"]).replace("HZ", "")
            if n == want or (want.isdigit() and n.endswith("K") and want == str(int(float(n[:-1]) * 1000))):
                return p
    if not plist:
        sys.exit(f"Block {block} needs a model to resolve param names (pass --model).")
    sys.exit(f"Unknown param '{pname}' for {block}. Options: {', '.join(p['name'] for p in plist)}")


def to_cc_value(p, value):
    """Turn a user value (number, choice name, or value with unit) into the 0-127 MIDI value."""
    if "choices" in p and not re.match(r"^-?\d+(\.\d+)?$", str(value)):
        for i, c in enumerate(p["choices"]):
            if norm(c) == norm(value):
                return i
        sys.exit(f"{p['name']}: choose one of {p['choices']}")
    s = str(value).strip().lower().replace(",", ".")
    scale = p.get("scale")
    m = re.match(r"^([+-]?\d+(?:\.\d+)?)\s*(khz|hz|db)?$", s)
    if not m:
        sys.exit(f"Bad value '{value}' for {p['name']}")
    num, unit = float(m.group(1)), m.group(2)
    if unit in ("hz", "khz"):
        hz = num * (1000 if unit == "khz" else 1)
        if scale == "lowcut":
            v = 100 * math.log(max(hz, 20) / 20) / math.log(50)
        elif scale == "highcut":
            v = 100 * math.log(max(hz, 5000) / 5000) / math.log(4)
        else:
            sys.exit(f"{p['name']} does not take Hz")
    elif unit == "db":
        if scale == "db15":
            v = (num + 15) / 0.3
        elif scale == "db12":
            v = (num + 12) / 0.24
        else:
            sys.exit(f"{p['name']} does not take dB")
    else:
        v = num
    v = int(round(v))
    lo, hi = p.get("min", 0), p.get("max", 100)
    if not lo <= v <= hi:
        clamped = max(lo, min(hi, v))
        print(f"  ! {p['name']}={value} -> {v} out of range {lo}-{hi}, using {clamped}")
        v = clamped
    return v


def describe(p, v):
    scale = p.get("scale")
    if scale == "db15": return f"{-15 + 0.3 * v:+.1f} dB"
    if scale == "db12": return f"{-12 + 0.24 * v:+.1f} dB"
    if scale == "lowcut": return f"{20 * 50 ** (v / 100):.0f} Hz"
    if scale == "highcut": return f"{5000 * 4 ** (v / 100):.0f} Hz"
    if "choices" in p: return p["choices"][v]
    return str(v)


def open_port(kind):
    import mido
    names = mido.get_output_names() if kind == "out" else mido.get_input_names()
    match = [n for n in names if MAP["midi"]["port_match"] in n]
    if not match:
        sys.exit(f"MG-400 not found. MIDI {kind} ports: {names}. Is it connected by USB?")
    return mido.open_output(match[0]) if kind == "out" else mido.open_input(match[0])


class Sender:
    def __init__(self, dry):
        self.dry = dry
        self.out = None if dry else open_port("out")
        self.inp = None if dry else open_port("in")

    def cc(self, cc, value, label=""):
        print(f"  CC{cc:<3} = {value:<3} {label}")
        if not self.dry:
            import mido
            self.out.send(mido.Message("control_change", channel=CH, control=cc, value=value))
            time.sleep(0.02)

    def settle(self, cc=None, quiet=0.2, min_wait=0.3, limit=2.0):
        """After a model change the pedal loads (and echoes) that model's defaults, sometimes slowly
        (alternate-type slots). Wait for the echo of the model CC when one comes, at least `min_wait`,
        and then for `quiet` seconds of silence, so the defaults cannot overwrite the params sent next."""
        if self.dry:
            return
        start = last = time.time()
        echoed = cc is None
        while time.time() - start < limit:
            msgs = list(self.inp.iter_pending())  # drain everything queued
            if msgs:
                last = time.time()
                echoed = echoed or any(m.type == "control_change" and m.control == cc for m in msgs)
            elif time.time() - start >= min_wait and time.time() - last >= quiet and (echoed or time.time() - start >= 1.0):
                return
            time.sleep(0.005)


# Some slots can host another block type: model CC value + 32 selects a model of the alternate type.
# Its params then live on the slot's own param CCs. (DLY has no alternate type.)
ALT_TYPE = {"CMP": "EFX", "EFX": "MOD", "MOD": "EFX", "RVB": "DLY"}
ALT_FLAG = 32
# Models missing from a slot's alternate list; later models shift down by one.
# Verified on the pedal: CMP->EFX has no TOUCH WAH (16 = HORSEMAN OD there), MOD->EFX keeps the full list.
# EFX->MOD and RVB->DLY assumed full (not exhaustively verified).
ALT_SKIP = {"CMP": {"TOUCH WAH"}}


def alt_number(slot, kind, num, info):
    skip = ALT_SKIP.get(slot, set())
    if info["name"] in skip:
        sys.exit(f"{info['name']} is not available when the {slot} slot is switched to {kind}.")
    models = MAP["models"][kind]
    return num - sum(1 for n, m in models.items() if int(n) < num and m["name"] in skip)
_bases = sorted(b["param_cc"] for b in BLOCKS.values())
SLOT_SIZE = {name: (_bases[_bases.index(b["param_cc"]) + 1] if b["param_cc"] != _bases[-1] else 78) - b["param_cc"]
             for name, b in BLOCKS.items()}


def slot_kind(slot, spec):
    kind = str(spec.get("as", slot)).upper()
    if kind != slot and ALT_TYPE.get(slot) != kind:
        options = f"'{ALT_TYPE[slot]}'" if slot in ALT_TYPE else "nothing (no alternate type)"
        sys.exit(f"Slot {slot} can only be switched to {options}, not '{kind}'.")
    return kind


def block_plan(block, spec):
    """Return list of (cc, value, label) for one block spec from a preset. `block` is the slot."""
    b = BLOCKS[block]
    kind = slot_kind(block, spec)
    tag = block if kind == block else f"{block}->{kind}"
    plan = []
    num, info = (None, None)
    if "model" in spec:
        num, info = find_model(kind, spec["model"])
        on = spec.get("on", True)
        value = (alt_number(block, kind, num, info) + ALT_FLAG if kind != block else num) + (0 if on else OFF)
        plan.append((b["type_cc"], value, f"{tag} model {info['name']}{'' if on else ' (OFF)'}"))
    elif "on" in spec or kind != block:
        sys.exit(f"{block}: 'on'/'as' need 'model' too (both live in the model CC)")
    for pname, val in spec.get("params", {}).items():
        p = find_param(kind, info, pname)
        if p["index"] >= SLOT_SIZE[block]:
            sys.exit(f"{tag}: param {p['name']} does not fit in the {block} slot ({SLOT_SIZE[block]} params max)")
        v = to_cc_value(p, val)
        plan.append((b["param_cc"] + p["index"], v, f"{tag} {p['name']} = {describe(p, v)}"))
    return plan


def order_ids(names):
    """Validate a chain order (all 10 blocks, each once) and return the block ids (= type CC numbers)."""
    names = [str(n).upper() for n in names]
    if sorted(names) != sorted(BLOCKS):
        sys.exit(f"Order must list each block exactly once: {MAP['chain_order']}")
    return [BLOCKS[n]["type_cc"] for n in names]


def send_order(sender, names):
    ids = order_ids(names)
    print(f"  order: {' -> '.join(str(n).upper() for n in names)}")
    if sender.dry:
        return
    sysex_exchange(sender.out, sender.inp, [0x0D, 0x01] + ids + [0, 0], SX + [0x0D, 0x02])


SCENE_CC = 79  # value 0-2 = SCN1-SCN3; CC edits only touch the active scene


def upper_keys(blocks, where):
    blocks = {k.upper(): v for k, v in blocks.items()}
    unknown = set(blocks) - set(BLOCKS)
    if unknown:
        sys.exit(f"Unknown blocks in {where}: {unknown}. Valid: {list(BLOCKS)}")
    return blocks


def merge_block(base, over):
    """Scene override on top of the base block. A different model does not inherit the base params."""
    if base is None:
        return over
    if str(over.get("as", base.get("as", ""))).upper() != str(base.get("as", "")).upper():
        return over  # different block type in this slot: nothing to inherit
    if "model" in over and find_model_name(over["model"]) != find_model_name(base.get("model")):
        return over
    merged = {**base, **{k: v for k, v in over.items() if k != "params"}}
    merged["params"] = {**base.get("params", {}), **over.get("params", {})}
    return merged


def find_model_name(model):
    return norm(model) if model is not None else None


def scene_blocks(preset):
    """Return {scene_number: blocks} for the scenes to write."""
    base = upper_keys(preset.get("blocks", {}), "blocks")
    scenes = preset.get("scenes")
    if not scenes:
        return {n: base for n in (1, 2, 3)}  # no scenes: same tone everywhere, so SCN2/3 never hold stale sounds
    out = {}
    for key, over in scenes.items():
        n = int(key)
        if n not in (1, 2, 3):
            sys.exit(f"Scene must be 1, 2 or 3 (got {key})")
        over = upper_keys(over.get("blocks", over), f"scene {n}")
        out[n] = {blk: merge_block(base.get(blk), over.get(blk, {})) if blk in over else base[blk]
                  for blk in set(base) | set(over)}
    for n in (1, 2, 3):
        out.setdefault(n, base)  # scenes not listed get the base tone
    return out


def cmd_apply(path, dry, only_scene=None):
    preset = json.load(open(path, encoding="utf-8-sig"))  # tolerate the BOM some Windows editors add
    scenes = scene_blocks(preset)
    if only_scene:
        scenes = {only_scene: scenes[only_scene]}
    plans = {n: [(blk, blocks[blk], block_plan(blk, blocks[blk])) for blk in SEND_ORDER if blk in blocks]
             for n, blocks in scenes.items()}  # validate everything before sending anything
    order = preset.get("order")
    if order:
        order_ids(order)  # validate before sending anything
    s = Sender(dry)
    print(f"Applying '{preset.get('name', path)}'{' (dry run)' if dry else ''}")
    if order:  # one chain order per preset (shared by all scenes)
        send_order(s, order)
    for n, plan in sorted(plans.items()):
        print(f" Scene {n}")
        s.cc(SCENE_CC, n - 1, f"select SCN{n}")
        s.settle(SCENE_CC)
        for blk, spec, steps in plan:
            for i, (cc, v, label) in enumerate(steps):
                s.cc(cc, v, label)
                if i == 0 and "model" in spec:
                    s.settle(cc)
    if len(plans) > 1:
        s.cc(SCENE_CC, 0, "back to SCN1")
    print("Done. Edit buffer only - use `save SLOT --name ... --yes` (or save on the pedal) to keep it.")


# --- SysEx: preset data (edit buffer / slots) ---------------------------------
# Messages: F0 43 58 70 <cmd> <op> <slot> <chunk> ... F7
#   cmd 0x0C = edit buffer, 0x0B = stored preset; op 00 = read request, 02 = reply, 01 = write, 03 = write ack.
# A preset is 3 chunks of 219 bytes (incl. F0/F7). The name sits at bytes 166..189 of every chunk:
# 8 triplets, each holding two ASCII chars as (c0, bit6 of c1, (c1 << 1) & 0x7F). 16 chars max.
SX = [0x43, 0x58, 0x70]
NAME_AT, NAME_LEN = 166, 16


def parse_slot(s):
    s = str(s).strip().upper()
    if s.isdigit():
        n = int(s)
    else:
        m = re.match(r"^(\d{1,2})([A-D])$", s)
        if not m:
            sys.exit(f"Bad slot '{s}'. Use bank+letter like 15B, or a 0-based number.")
        n = (int(m.group(1)) - 1) * 4 + "ABCD".index(m.group(2))
    if not 0 <= n <= 127:
        sys.exit(f"Slot out of range: {s}")
    return n


def slot_label(n):
    return f"{n // 4 + 1}{'ABCD'[n % 4]}"


def decode_name(chunk):
    seg = chunk[NAME_AT:NAME_AT + 24]
    chars = []
    for i in range(0, 24, 3):
        chars += [seg[i], (seg[i + 2] >> 1) | ((seg[i + 1] & 1) << 6)]
    return bytes(c for c in chars if c).decode("ascii", "replace")


def encode_name(name):
    if len(name) > NAME_LEN or any(not 0x20 <= ord(c) <= 0x7E for c in name):
        sys.exit(f"Name must be up to {NAME_LEN} plain ASCII characters.")
    b = name.encode("ascii").ljust(NAME_LEN, b"\0")
    out = []
    for i in range(0, NAME_LEN, 2):
        c0, c1 = b[i], b[i + 1]
        out += [c0, (c1 >> 6) & 1, (c1 << 1) & 0x7F]
    return out


def sysex_exchange(out, inp, data, want, timeout=1.5, tries=3):
    """Send one SysEx and wait for a reply whose first bytes equal `want`; resend if the pedal stays silent."""
    import mido
    for _ in range(tries):
        out.send(mido.Message("sysex", data=SX + data))
        end = time.time() + timeout
        while time.time() < end:
            for m in inp.iter_pending():
                if m.type == "sysex" and list(m.data[:len(want)]) == want:
                    return [0xF0] + list(m.data) + [0xF7]
            time.sleep(0.003)
    sys.exit(f"No reply from pedal for {bytes(data[:4]).hex(' ')} after {tries} tries. Is the USB cable connected?")


def read_edit_buffer(out, inp):
    for _ in inp.iter_pending():
        pass
    chunks = []
    for ch in range(3):
        msg = sysex_exchange(out, inp, [0x0C, 0x00, 0x00, ch, 0, 0, 0, 0, 0, 0], SX + [0x0C, 0x02])
        if msg[7] != ch or len(msg) != 219:
            sys.exit(f"Unexpected edit buffer reply (chunk {msg[7]}, {len(msg)} bytes)")
        chunks.append(msg)
    return chunks


def cmd_name():
    out, inp = open_port("out"), open_port("in")
    chunks = read_edit_buffer(out, inp)
    print(f"Edit buffer (slot {slot_label(chunks[0][6])}): {decode_name(chunks[0])!r}")


def cmd_save(slot, name, yes, same_scenes=False):
    n = parse_slot(slot)
    if not yes:
        sys.exit(f"This overwrites slot {slot_label(n)} on the pedal. Re-run with --yes once the user agreed.")
    out, inp = open_port("out"), open_port("in")
    chunks = read_edit_buffer(out, inp)
    old = decode_name(chunks[0])
    if name is None and chunks[0][6] != n:
        sys.exit(f"The edit buffer is from slot {slot_label(chunks[0][6])} ({old!r}), not {slot_label(n)}. "
                 "The user may have switched presets. Pass --name, or switch back and re-apply first.")
    if same_scenes:  # one-tone preset: SCN2/SCN3 become exact copies of SCN1 (no stale params in bypassed blocks)
        chunks = [chunks[0][:7] + [i] + chunks[0][8:] for i in range(3)]
    for i, c in enumerate(chunks):
        data = c[1:-1]                    # strip F0/F7
        data[3], data[4], data[5] = 0x0B, 0x01, n   # stored preset, write, target slot
        if name is not None:
            data[NAME_AT - 1:NAME_AT - 1 + 24] = encode_name(name)
        ack = sysex_exchange(out, inp, data[3:], SX + [0x0B, 0x03, n, i])
    print(f"Saved to {slot_label(n)} as {name if name is not None else old!r} (pedal acknowledged all 3 chunks).")


def cmd_copy(src, dst, yes):
    """Copy a stored preset to another slot byte for byte (all scenes, order, name)."""
    import mido
    s, d = parse_slot(src), parse_slot(dst)
    if not yes:
        sys.exit(f"This overwrites slot {slot_label(d)}. Re-run with --yes once the user agreed.")
    out, inp = open_port("out"), open_port("in")
    out.send(mido.Message("program_change", channel=CH, program=s))
    time.sleep(0.8)
    chunks = read_edit_buffer(out, inp)
    if chunks[0][6] != s:
        sys.exit(f"Pedal did not load {slot_label(s)} (edit buffer is from {slot_label(chunks[0][6])}).")
    for i, c in enumerate(chunks):
        data = c[1:-1]
        data[3], data[4], data[5] = 0x0B, 0x01, d
        sysex_exchange(out, inp, data[3:], SX + [0x0B, 0x03, d, i])
    print(f"Copied {slot_label(s)} {decode_name(chunks[0])!r} -> {slot_label(d)} (pedal acknowledged all 3 chunks).")


def cmd_list(block, model):
    if not block:
        for name, b in BLOCKS.items():
            n = len(MAP["models"].get(name, {}))
            print(f"{name:5} type CC{b['type_cc']:<3} params from CC{b['param_cc']:<3} {n} models")
        return
    block = block.upper()
    if not model:
        for n, m in MAP["models"].get(block, {}).items():
            ref = f"  <- {m['based_on']}{' (inferred)' if m.get('reference') == 'inferred' else ''}" if m.get("based_on") else ""
            print(f"{n:>3}  {m['name']:16}{ref}")
        if "params" in BLOCKS[block]:
            print("params:", ", ".join(p["name"] for p in BLOCKS[block]["params"]))
        return
    num, info = find_model(block, model)
    ref = f"  (based on {info['based_on']}{', inferred' if info.get('reference') == 'inferred' else ''})" if info.get("based_on") else ""
    print(f"{block} {num}: {info['name']}{ref}")
    for p in params_for(block, info):
        extra = p.get("scale") or ("switch" if p.get("switch") else "") or ("/".join(p["choices"]) if "choices" in p else "")
        print(f"  {p['name']:12} CC{BLOCKS[block]['param_cc'] + p['index']:<3} {p['min']}-{p['max']}  default={p.get('default')}  {extra}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ports")
    p = sub.add_parser("list"); p.add_argument("block", nargs="?"); p.add_argument("model", nargs="?")
    p = sub.add_parser("apply"); p.add_argument("preset"); p.add_argument("--dry-run", action="store_true")
    p.add_argument("--scene", type=int, choices=[1, 2, 3], help="apply only this scene")
    p = sub.add_parser("scene"); p.add_argument("n", type=int, choices=[1, 2, 3])
    p = sub.add_parser("order"); p.add_argument("blocks", nargs="*", help="all 10 blocks in chain order; empty = default")
    p = sub.add_parser("model"); p.add_argument("block"); p.add_argument("model"); p.add_argument("--off", action="store_true")
    p = sub.add_parser("onoff"); p.add_argument("block"); p.add_argument("state", choices=["on", "off"]); p.add_argument("--model", required=True)
    p = sub.add_parser("set"); p.add_argument("block"); p.add_argument("param"); p.add_argument("value"); p.add_argument("--model")
    p.add_argument("--as", dest="as_type", help="the slot hosts another block type (e.g. CMP slot --as EFX)")
    p = sub.add_parser("program"); p.add_argument("slot")
    sub.add_parser("name")
    p = sub.add_parser("copy"); p.add_argument("src"); p.add_argument("dst"); p.add_argument("--yes", action="store_true")
    p = sub.add_parser("save"); p.add_argument("slot"); p.add_argument("--name"); p.add_argument("--yes", action="store_true")
    p.add_argument("--same-scenes", action="store_true", help="copy SCN1 into SCN2 and SCN3 (presets without scenes)")
    p = sub.add_parser("monitor"); p.add_argument("seconds", nargs="?", type=float, default=30)
    a = ap.parse_args()

    if a.cmd == "ports":
        import mido
        print("IN: ", mido.get_input_names()); print("OUT:", mido.get_output_names())
    elif a.cmd == "list":
        cmd_list(a.block, a.model)
    elif a.cmd == "apply":
        cmd_apply(a.preset, a.dry_run, a.scene)
    elif a.cmd == "scene":
        Sender(False).cc(SCENE_CC, a.n - 1, f"select SCN{a.n}")
    elif a.cmd == "order":
        send_order(Sender(False), a.blocks or MAP["chain_order"])
    elif a.cmd in ("model", "onoff"):
        blk = a.block.upper()
        on = (not a.off) if a.cmd == "model" else a.state == "on"
        num, info = find_model(blk, a.model)
        Sender(False).cc(BLOCKS[blk]["type_cc"], num + (0 if on else OFF), f"{blk} {info['name']} {'ON' if on else 'OFF'}")
    elif a.cmd == "set":
        blk = a.block.upper()  # the slot
        kind = slot_kind(blk, {"as": a.as_type} if a.as_type else {})
        info = find_model(kind, a.model)[1] if a.model else None
        p = find_param(kind, info, a.param)
        v = to_cc_value(p, a.value)
        tag = blk if kind == blk else f"{blk}->{kind}"
        Sender(False).cc(BLOCKS[blk]["param_cc"] + p["index"], v, f"{tag} {p['name']} = {describe(p, v)}")
    elif a.cmd == "program":
        import mido
        n = parse_slot(a.slot)
        open_port("out").send(mido.Message("program_change", channel=CH, program=n))
        print(f"program {n} ({slot_label(n)})")
    elif a.cmd == "name":
        cmd_name()
    elif a.cmd == "copy":
        cmd_copy(a.src, a.dst, a.yes)
    elif a.cmd == "save":
        cmd_save(a.slot, a.name, a.yes, a.same_scenes)
    elif a.cmd == "monitor":
        inp = open_port("in"); end = time.time() + a.seconds
        while time.time() < end:
            for msg in inp.iter_pending():
                print(msg.hex() if msg.type == "sysex" else msg)
            time.sleep(0.005)


if __name__ == "__main__":
    main()
