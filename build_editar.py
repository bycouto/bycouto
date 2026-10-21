"""Edita o vídeo 'Editar' no estilo orgânico (fonte branca)."""
import json, re, subprocess, sys

SRC = "work/editar.mov"
WORDS = "work/editar.mov.json"
ASS = "work/editar.ass"
OUT = sys.argv[1] if len(sys.argv) > 1 else "work/editar_v2.mp4"
SO_CORTES = "--so-cortes" in sys.argv  # sem legenda, destaques, zoom nem ajuste de cor
PAD = 0.12

# Trechos do bruto que ficam (tempo do original). Retomadas/erros ficam de fora.
KEEP = [
    (0.0, 3.5),      # o Brasil tem muito talento né
    (8.9, 19.8),     # eu mesmo fico impressionada... Lina Bo Bardi (1ª versão, igual ao roteiro)
    (32.3, 48.6),    # desenharam peças... continuarem tão atuais
    (51.8, 53.9),    # e não, não é a moda
    (69.1, 74.8),    # é a forma da proporção, a escolha dos materiais e claro, conforto de verdade (3ª tentativa)
    (75.8, 79.8),    # quando o cliente tem uma peça assim...
    (89.85, 93.0),   # além de ser um patrimônio familiar... (2ª tentativa)
    (106.8, 111.9),  # e é claro que nesses casos o projeto... (última tentativa)
    (117.6, 120.8),  # quem sabe um dia eu posso ter um mobiliário desse pra chamar de minha né
]
# Zoom de ênfase (punch-in): instante do original -> fator
ZOOMS = {40.9: 1.18, 52.2: 1.18, 106.9: 1.12, 117.8: 1.18}

PROPER = {"brasil": "Brasil", "sérgio": "Sérgio", "rodrigues": "Rodrigues", "joaquim": "Joaquim",
          "tenreiro": "Tenreiro", "lina": "Lina", "bo": "Bo", "bardi": "Bardi", "mole": "Mole"}
FIXES = {"mil": "minha"}


def speech_intervals():
    log = subprocess.run(["ffmpeg", "-hide_banner", "-i", SRC, "-af", "silencedetect=n=-35dB:d=0.35",
                          "-vn", "-f", "null", "-"], capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([\d.]+)", log)]
    ends = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", log)]
    out, cur = [], 0.0
    for s, e in zip(starts, ends):
        if s + PAD - cur > 0.2:
            out.append((max(0.0, cur), s + PAD))
        cur = e - PAD
    out.append((cur, 999.0))
    return out


def build_segments():
    segs = []
    for ka, kb in KEEP:
        for sa, sb in speech_intervals():
            a, b = max(ka, sa), min(kb, sb)
            if b - a > 0.2:
                if segs and a - segs[-1][1] < 0.15:
                    segs[-1] = (segs[-1][0], b)
                else:
                    segs.append((a, b))
    return segs


def to_out(t, segs):
    acc = 0.0
    for a, b in segs:
        if a <= t <= b:
            return acc + (t - a)
        acc += b - a
    return None


def ts(t):
    t = max(t, 0)
    return f"{int(t // 3600)}:{int(t % 3600 // 60):02d}:{t % 60:05.2f}"


def clean(w):
    w = re.sub(r"[.,!?;:]", "", w.strip())
    lw = w.lower()
    lw = FIXES.get(lw, lw)
    return PROPER.get(lw, lw)


def main():
    segs = build_segments()
    total = sum(b - a for a, b in segs)
    print(f"{len(segs)} trechos, duração final {total:.1f}s")

    # Palavras mantidas, no tempo de saída
    words = []
    for s in json.load(open(WORDS)):
        for w in s["words"]:
            seg = next(((a, b) for a, b in segs if min(w["e"], b) - max(w["s"], a) > 0.03 or a <= w["s"] + 0.03 <= b), None)
            if seg is None:
                continue
            t0 = max(w["s"] + 0.03, seg[0])
            o_s = to_out(t0, segs)
            words.append({"w": clean(w["w"]), "raw": w["w"], "src": w["s"], "s": o_s,
                          "e": o_s + min(w["e"], seg[1]) - t0})
    words = [w for w in words if w["w"]]

    def at(word, after=0.0):
        return next(w for w in words if w["w"].lower() == word.lower() and w["src"] >= after)

    def until(w, extra):  # segura o destaque, mas some antes da próxima palavra
        nxt = next((x for x in words if x["s"] > w["s"] + 0.01), None)
        return min(w["e"] + extra, nxt["s"] - 0.02) if nxt else w["e"] + extra

    # Blocos de destaque (fonte grossa). Durante uma lista a legenda corrida some.
    lists = [
        (["Sérgio Rodrigues", "Joaquim Tenreiro", "Lina Bo Bardi"],
         [at("Sérgio"), at("Joaquim"), at("Lina")], until(at("Bardi"), 0.6)),
        (["proporção", "materiais", "conforto"],
         [at("proporção", 69), at("materiais", 69), at("conforto", 69)], until(at("verdade", 69), 0.5)),
    ]
    singles = [(r"design\Nbrasileiro", 0.0, 2.6),
               ("1957", at("1957")["s"], at("1957")["e"] + 0.9),
               (r"patrimônio\Nfamiliar", at("patrimônio", 89)["s"], at("geração", 91)["e"] + 0.4)]
    hide = [(starts[0]["s"], end) for _, starts, end in lists]

    # Legenda corrida: frases curtas (até ~30 caracteres por linha, 2 linhas)
    def hidden(w):
        return any(ha <= w["s"] < hb for ha, hb in hide)
    cap = [w for w in words if not hidden(w)]
    chunks, cur = [], []
    for i, w in enumerate(cap):
        cur.append(w)
        text = " ".join(x["w"] for x in cur)
        nxt = cap[i + 1] if i + 1 < len(cap) else None
        brk = (nxt is None or len(text) > 38 or re.search(r"[.,?!]$", w["raw"].strip())
               or (nxt["s"] - w["e"]) > 0.35 or hidden(w) != hidden(nxt)
               or any(w["s"] < hb <= nxt["s"] for _, hb in hide))
        if brk:
            chunks.append(cur)
            cur = []
    lines = []
    for c in chunks:
        a, b = c[0]["s"], c[-1]["e"] + 0.15
        text = " ".join(x["w"] for x in c)
        if len(text) > 26:  # quebra em 2 linhas equilibradas
            ws = text.split()
            best = min(range(1, len(ws)), key=lambda k: abs(len(" ".join(ws[:k])) - len(" ".join(ws[k:]))))
            text = " ".join(ws[:best]) + r"\N" + " ".join(ws[best:])
        lines.append((a, b, text))
    # sem sobreposição
    for i in range(len(lines) - 1):
        a, b, t = lines[i]
        lines[i] = (a, min(b, lines[i + 1][0]), t)

    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Legenda,Playfair Display,70,&H00FFFFFF,&H00FFFFFF,&HA0000000,&HA0000000,0,1,0,0,100,100,0,0,1,4,0,8,110,110,320,1
Style: Destaque,Unbounded ExtraBold,86,&H00FFFFFF,&H00FFFFFF,&HB4000000,&H8C000000,0,0,0,0,100,100,0,0,1,3,0,5,50,50,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    for a, b, t in lines:
        ev.append(f"Dialogue: 0,{ts(a)},{ts(b)},Legenda,,0,0,0,,{{\\blur6}}{t}")
    pop = r"{\fad(80,120)\t(0,120,\fscx100\fscy100)\fscx88\fscy88\blur5}"
    for items, starts, end in lists:
        for k, (txt, w) in enumerate(zip(items, starts)):
            y = 1420 + (k - (len(items) - 1) / 2) * 125
            ev.append(f"Dialogue: 1,{ts(w['s'])},{ts(end)},Destaque,,0,0,0,,{{\\pos(540,{y:.0f})}}{pop}{txt}")
    for txt, a, b in singles:
        ev.append(f"Dialogue: 1,{ts(a)},{ts(b)},Destaque,,0,0,0,,{{\\pos(540,1420)}}{pop}{txt}")
    open(ASS, "w").write(head + "\n".join(ev) + "\n")

    # Vídeo: corta, aplica zoom de ênfase por trecho, concatena, legenda
    f = []
    for i, (a, b) in enumerate(segs):
        z = 1.0 if SO_CORTES else next((zv for zt, zv in ZOOMS.items() if a <= zt <= b), 1.0)
        crop = f",crop=iw/{z}:ih/{z}:(iw-iw/{z})/2:(ih-ih/{z})*0.3" if z > 1 else ""
        scale = "" if SO_CORTES else ",scale=1080:1920:flags=lanczos"
        f.append(f"[0:v]trim={a:.3f}:{b:.3f},setpts=PTS-STARTPTS{crop}{scale},setsar=1[v{i}];"
                 f"[0:a]atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS,afade=t=in:d=0.02,afade=t=out:st={b - a - 0.03:.3f}:d=0.03[a{i}]")
    n = len(segs)
    f.append("".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[vc][ac];"
             + ("[vc]null[vo];" if SO_CORTES else f"[vc]eq=brightness=0.02:saturation=1.05,ass={ASS}:fontsdir=fonts/static[vo];")
             + 
             "[ac]loudnorm=I=-14:TP=-1.5:LRA=11[ao]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", SRC, "-filter_complex", ";".join(f),
                    "-map", "[vo]", "-map", "[ao]", "-c:v", "libx264", "-preset", "slow", "-crf", "18" if SO_CORTES else "23",
                    "-maxrate", "8M", "-bufsize", "16M", "-pix_fmt", "yuv420p", "-r", "30",
                    "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", OUT], check=True)
    print("ok", OUT)


main()
