# design.md - report pages: editorial pixel-tech with glass

The look: a technical document wearing a fashion-editorial skin. Type-specimen chrome, a drawn
rounded-pixel headline, one hot orange accent, frosted-glass cards over a controlled ground, and a
deliberately dark terminal card in both themes. Clean first; pixel as jewellery, never as noise.

**Light is the default.** A report opens light regardless of OS setting; the toggle stamps
`data-theme="dark"` on `<html>`. Every colour is defined as a token on bare `:root` and never only
inside a theme block, and `body` always sets an explicit token background - this matches the
published three-state artifact cascade, so a report also publishes as an artifact unchanged.

Every report is ONE self-contained .html: inline CSS and JS, no CDN, no external fonts or images
(data: URIs if an image is unavoidable). It must render from a `file://` double-click, offline.
Name it `YYYY-MM-DD-<slug>.html`, beside its markdown source of truth.

## Tokens - paste as-is, style ONLY through these

```css
:root {            /* LIGHT - the default */
  --bg:#F2F1ED; --text:#141414; --muted:#6E6A63; --hair:rgba(20,20,20,.12);
  --glass:rgba(255,255,255,.62); --glass2:rgba(20,20,20,.06);
  --glow-a:rgba(255,90,45,.14); --glow-b:rgba(61,120,220,.08); --glow-c:rgba(61,220,151,.07);
  --gridline:rgba(20,20,20,.03); --cardshadow:0 8px 26px rgba(20,20,20,.08);
  --px-ink:#141414;
  --orange:#FF5A2D; --green:#0E8A57; --amber:#B07B00; --red:#D6403A; --violet:#6C4FE0;
  --mono:"Cascadia Mono",Consolas,Menlo,monospace;
  --sans:"Segoe UI",system-ui,Roboto,Helvetica,Arial,sans-serif;
}
:root[data-theme="dark"] {
  --bg:#0D1015; --text:#ECEAE6; --muted:#8B93A1; --hair:rgba(255,255,255,.10);
  --glass:rgba(255,255,255,.055); --glass2:rgba(255,255,255,.085);
  --glow-a:rgba(255,90,45,.32); --glow-b:rgba(61,120,220,.16); --glow-c:rgba(61,220,151,.10);
  --gridline:rgba(255,255,255,.025); --cardshadow:0 8px 30px rgba(0,0,0,.35);
  --px-ink:#ECEAE6;
  --green:#3DDC97; --amber:#FFC53D; --red:#FF6B6B; --violet:#A78BFA;
}
body { background:var(--bg); color:var(--text); font:15px/1.65 var(--sans); }
```

Ground: two fixed pseudo-layers behind the page - three soft radial glows (`--glow-a/b/c`, orange
top-right, blue lower-left, green bottom) and a faint 28px grid of `--gridline`. That is the ONLY
thing glass ever sits over.

## The glass, with its guardrails

`background:var(--glass); border:1px solid var(--hair); border-radius:18px;
backdrop-filter:blur(16px); box-shadow:var(--cardshadow);`

Glassmorphism is banned by some practitioners as an AI tell, and the readability criticism behind
that is real. This design keeps glass as a deliberate identity by meeting the criticism:

1. Glass sits ONLY over the controlled ground above - never over images or busy content.
2. The fill doubles as a barrier layer: body-text contrast must hold at WCAG's 4.5:1 (3:1 for
   large text) measured with the blur applied. If a glow makes text marginal, raise the fill
   opacity, never lower the text contrast.
3. Blur stays high (16px+). Low blur over a varied ground is the failure mode.
4. Print gets flat cards: in `@media print`, replace glass with solid `--bg`-derived fills.

## The pixel headline - drawn, not a font

Pixel display fonts cannot be fetched in a self-contained file, so the headline is DRAWN: 5x7
glyphs as rounded squares on a canvas. Include this renderer; call `draw()` again on theme toggle.

```html
<canvas id="pxtitle" aria-label="TITLE"></canvas>
<script>
(function(){
  var G={A:["01110","10001","10001","11111","10001","10001","10001"],B:["11110","10001","11110","10001","10001","10001","11110"],C:["01110","10001","10000","10000","10000","10001","01110"],D:["11110","10001","10001","10001","10001","10001","11110"],E:["11111","10000","10000","11110","10000","10000","11111"],F:["11111","10000","10000","11110","10000","10000","10000"],G:["01110","10001","10000","10111","10001","10001","01110"],H:["10001","10001","10001","11111","10001","10001","10001"],I:["01110","00100","00100","00100","00100","00100","01110"],J:["00111","00010","00010","00010","00010","10010","01100"],K:["10001","10010","10100","11000","10100","10010","10001"],L:["10000","10000","10000","10000","10000","10000","11111"],M:["10001","11011","10101","10101","10001","10001","10001"],N:["10001","11001","10101","10011","10001","10001","10001"],O:["01110","10001","10001","10001","10001","10001","01110"],P:["11110","10001","10001","11110","10000","10000","10000"],Q:["01110","10001","10001","10001","10101","10010","01101"],R:["11110","10001","10001","11110","10100","10010","10001"],S:["01111","10000","10000","01110","00001","00001","11110"],T:["11111","00100","00100","00100","00100","00100","00100"],U:["10001","10001","10001","10001","10001","10001","01110"],V:["10001","10001","10001","10001","10001","01010","00100"],W:["10001","10001","10001","10101","10101","11011","10001"],X:["10001","01010","00100","00100","00100","01010","10001"],Y:["10001","01010","00100","00100","00100","00100","00100"],Z:["11111","00001","00010","00100","01000","10000","11111"],"0":["01110","10001","10011","10101","11001","10001","01110"],"1":["00100","01100","00100","00100","00100","00100","01110"],"2":["01110","10001","00001","00110","01000","10000","11111"],"3":["01110","10001","00001","00110","00001","10001","01110"],"4":["00010","00110","01010","10010","11111","00010","00010"],"5":["11111","10000","11110","00001","00001","10001","01110"],"6":["01110","10000","11110","10001","10001","10001","01110"],"7":["11111","00001","00010","00100","01000","01000","01000"],"8":["01110","10001","10001","01110","10001","10001","01110"],"9":["01110","10001","10001","01111","00001","00001","01110"],"-":["00000","00000","00000","01110","00000","00000","00000"]," ":["00000","00000","00000","00000","00000","00000","00000"]};
  var text=(document.getElementById("pxtitle").getAttribute("aria-label")||"REPORT").toUpperCase();
  var px=9, gap=2, adv=6, dpr=window.devicePixelRatio||1;
  var c=document.getElementById("pxtitle"), w=(text.length*adv-1)*px, h=7*px;
  c.width=w*dpr; c.height=h*dpr; c.style.width=Math.min(w,820)+"px"; c.style.height="auto"; c.style.maxWidth="100%";
  var x=c.getContext("2d"); x.scale(dpr,dpr);
  function rr(a,b,s,r){x.beginPath();x.moveTo(a+r,b);x.arcTo(a+s,b,a+s,b+s,r);x.arcTo(a+s,b+s,a,b+s,r);x.arcTo(a,b+s,a,b,r);x.arcTo(a,b,a+s,b,r);x.fill();}
  function draw(){var ink=getComputedStyle(document.documentElement).getPropertyValue("--px-ink").trim()||"#141414";
    x.clearRect(0,0,w,h);
    var mid=Math.floor(text.length/2); var idx=text[mid]===" "?mid+1:mid;   /* one accent letter */
    for(var i=0;i<text.length;i++){var g=G[text[i]]||G[" "];
      x.fillStyle = i===idx ? "#FF5A2D" : ink;
      for(var r=0;r<7;r++)for(var col=0;col<5;col++) if(g[r][col]==="1") rr((i*adv+col)*px,r*px,px-gap,2.6);}}
  window.__drawTitle=draw; draw();
})();
</script>
```

Exactly ONE letter (near the middle) renders in `--orange` - the specimen accent. Headline only;
body text is always `--sans`, identifiers and labels `--mono`.

## Page anatomy - same order, every report

1. **Chrome bar**: `TYPE ☻ NAME` left, `REV nn / date [ THEME TOGGLE ]` right; 1.5px `--text`
   bottom border. The toggle is a bordered pill button; JS stamps/unstamps `data-theme="dark"`
   and calls `__drawTitle()`.
2. **Kicker**: `[ n/n ]` in `--muted`, then doc type and current state in `--orange`, 11px mono
   uppercase, 2px letterspacing.
3. **Pixel headline**, then orange-dot metadata line: ID, source of truth, "render: disposable".
4. **Properties card** (glass): Status / Source / Progress rows, mono uppercase keys, pill values.
5. **"How to review" callout** (glass): the two actions - approve, or comment in the .md.
6. **Numbered sections**: `1.0` in `--orange` + uppercase title + hairline rule + a right-aligned
   micro-tag (e.g. the source line range).
7. **Footer**: 1.5px top border, mono microcopy: `EDITS LAND IN <SOURCE>.MD - THIS PAGE IS A
   RENDER` left, kit mark right. Below it, one final muted line - 10px mono, letterspaced,
   centered or left, nothing louder:
   `GENERATED WITH THE-AGENT-KIT ☻ BUILT BY VIKASH CHAND · github.com/vikichand/the-agent-kit`
   This is the only place the kit names itself. Never in the headline, never as a badge, never in
   the content - a colophon, not a watermark. (It credits the human and his tool; §9's ban on AI
   attribution is about authorship trailers in git, and stays fully in force.)

Section skeletons by report type (converging practice from published report skills):
- **plan**: summary stats -> steps -> risk callout -> acceptance criteria -> current state
- **review/audit**: verdict banner -> score/pass-fail table -> findings (worst first) -> per-finding detail -> recommendations
- **task completion**: summary -> changes made -> verification -> next steps
- **comparison**: options table -> per-option analysis -> recommendation

## Components

- **Step row**: pixel state icon (SVG `shape-rendering="crispEdges"`), `Sn` id chip, text, status
  pill. Done rows: `--muted` + strikethrough. Pills: mono uppercase 11px, 999px radius;
  done=`--green` tint, next=solid `--orange` with dark text, risky=`--red` tint, gate=`--violet` tint.
- **Callout**: glass row, pixel SVG icon, bold lead phrase in the accent of its meaning. Risk
  callouts add an orange-tinted border.
- **Table**: mono uppercase 10.5px headers, hairline row rules, first column in `--orange` mono.
  Wrapper card scrolls horizontally; the page never does.
- **Terminal card**: stays dark in BOTH themes (`rgba(13,16,21,.92)`, light text) - the deliberate
  contrast block. Carries mini-stats, an optional thin-bar chart (6px bars, 3px radius; highlighted
  bars `--orange` with a soft glow), a 9.5px mono caption, and real command output.
- **Pixel icons**: small inline SVGs on a 6-9px grid with `crispEdges` - checkmark, square,
  warning, diamond. Never emoji.
- **Layered disclosure**: summary and tables at top level; depth goes in `<details>` blocks.
  Nothing important lives ONLY inside a collapsible.

## Restraint - what keeps it clean

- Every chart must earn its place or become a table (Tufte's erasing test) - but keep redundancy
  that aids reading: direct labels over legends, muted gridlines.
- Banned: gradients as decoration, emoji headers, text over blur without the barrier check,
  more than one accent family per page, pixel font at body sizes, any external request.
- Density is handled by disclosure and tables, never by deleting information the reader needs.
- One page, one purpose. A report that wants a nav bar is two reports.
