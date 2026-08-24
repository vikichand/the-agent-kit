# design.md - the agent kit report theme, as a component library

**The look**: a technical document wearing a fashion-editorial skin. Type-specimen chrome, a drawn
rounded-pixel headline, frosted-glass cards over a controlled dark ground, and a **neon glow on every
colored element**. Orange `#FF5A2D` is the kit's brand color and leads everything. Clean first; pixel
and glow as jewellery, never as noise.

**Dark is the default.** Bare `:root` carries the dark palette; the in-page toggle stamps
`data-theme="light"`. Every color is a token; style ONLY through tokens; `body` always sets an
explicit token background. (If a report is ever published as a claude.ai artifact, invert the
cascade to light-on-root per the artifact contract - standalone kit reports stay dark-first.)

**Responsive is part of the contract.** The stylesheet below already handles phones: chrome, foot
and colophon wrap; the theme button never breaks its brackets; property rows stack under 480px;
step rows wrap their pills; tables scroll inside `.tblwrap`. Keep it that way - any new component
must survive a 390px viewport without horizontal page scroll.

Every report is ONE self-contained .html: inline CSS/JS, no CDN, no external fonts/images (data:
URIs if unavoidable), renders from a `file://` double-click offline. Name: `YYYY-MM-DD-<slug>.html`.

**Do not improvise the UI.** Paste the stylesheet below as-is, use the markup patterns as given, and
build anything new from the same tokens. A report should be recognisably the same theme every time.

## 1. The stylesheet - paste verbatim

```css
:root {            /* DARK - the default */
  --bg:#0D1015; --text:#ECEAE6; --muted:#8B93A1; --hair:rgba(255,255,255,.10);
  --glass:rgba(255,255,255,.055); --glass2:rgba(255,255,255,.085);
  --glow-a:rgba(255,90,45,.32); --glow-b:rgba(61,120,220,.16); --glow-c:rgba(61,220,151,.10);
  --gridline:rgba(255,255,255,.025); --cardshadow:0 8px 30px rgba(0,0,0,.35);
  --px-ink:#ECEAE6;
  --orange:#FF5A2D; --green:#3DDC97; --amber:#FFC53D; --red:#FF6B6B; --violet:#A78BFA;
  --ng-o:0 0 12px rgba(255,90,45,.55); --ng-o-soft:0 0 8px rgba(255,90,45,.35);
  --ng-g:0 0 10px rgba(61,220,151,.40); --ng-r:0 0 10px rgba(255,107,107,.40);
  --ng-v:0 0 10px rgba(167,139,250,.40); --ng-am:0 0 10px rgba(255,197,61,.40);
  --mono:"Cascadia Mono",Consolas,Menlo,monospace;
  --sans:"Segoe UI",system-ui,Roboto,Helvetica,Arial,sans-serif;
}
:root[data-theme="light"] {
  --bg:#F2F1ED; --text:#141414; --muted:#6E6A63; --hair:rgba(20,20,20,.12);
  --glass:rgba(255,255,255,.62); --glass2:rgba(20,20,20,.06);
  --glow-a:rgba(255,90,45,.14); --glow-b:rgba(61,120,220,.08); --glow-c:rgba(61,220,151,.07);
  --gridline:rgba(20,20,20,.03); --cardshadow:0 8px 26px rgba(20,20,20,.08);
  --px-ink:#141414;
  --green:#0E8A57; --amber:#B07B00; --red:#D6403A; --violet:#6C4FE0;
  --ng-o:0 0 8px rgba(255,90,45,.30); --ng-o-soft:0 0 6px rgba(255,90,45,.20);
  --ng-g:0 0 6px rgba(14,138,87,.22); --ng-r:0 0 6px rgba(214,64,58,.22);
  --ng-v:0 0 6px rgba(108,79,224,.22); --ng-am:0 0 6px rgba(176,123,0,.22);
}
*{box-sizing:border-box;margin:0}
body{background:var(--bg);color:var(--text);font:15px/1.65 var(--sans);padding:20px 16px 40px;position:relative;overflow-x:hidden}
body::before{content:"";position:fixed;inset:0;z-index:-1;
  background:
    radial-gradient(560px 380px at 85% -5%, var(--glow-a), transparent 65%),
    radial-gradient(500px 420px at -10% 55%, var(--glow-b), transparent 65%),
    radial-gradient(420px 320px at 70% 110%, var(--glow-c), transparent 60%);}
body::after{content:"";position:fixed;inset:0;z-index:-1;
  background-image:linear-gradient(var(--gridline) 1px,transparent 1px),linear-gradient(90deg,var(--gridline) 1px,transparent 1px);
  background-size:28px 28px}
.frame{max-width:860px;margin:0 auto}
.chrome{display:flex;justify-content:space-between;align-items:center;font:11px var(--mono);letter-spacing:1.5px;text-transform:uppercase;padding:10px 2px;border-bottom:1.5px solid var(--text)}
.chrome .mark{color:var(--orange);text-shadow:var(--ng-o)}
.chrome .r{color:var(--muted);display:flex;align-items:center;gap:12px}
.tbtn{font:inherit;letter-spacing:inherit;text-transform:inherit;background:none;border:1px solid var(--hair);border-radius:999px;color:inherit;padding:2px 12px;cursor:pointer}
.tbtn:hover{border-color:var(--orange);color:var(--orange);text-shadow:var(--ng-o-soft)}
.hero{padding:44px 2px 30px}
.kicker{font:11px var(--mono);letter-spacing:2px;text-transform:uppercase;color:var(--orange);text-shadow:var(--ng-o-soft);margin-bottom:16px}
.kicker .brk{color:var(--muted);text-shadow:none}
#pxtitle{display:block;max-width:100%}
.sub{display:flex;gap:26px;flex-wrap:wrap;margin-top:22px;font:12px var(--mono);color:var(--muted)}
.sub b{color:var(--text);font-weight:600}
.sub .dot{color:var(--orange);text-shadow:var(--ng-o)}
.glass{background:var(--glass);border:1px solid var(--hair);border-radius:18px;backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);box-shadow:var(--cardshadow)}
.props{padding:8px 20px;margin-bottom:16px}
.prop{display:flex;align-items:center;padding:10px 0;border-bottom:1px solid var(--hair);font-size:14px}
.prop:last-child{border-bottom:none}
.prop .k{color:var(--muted);width:170px;flex:none;display:flex;gap:10px;align-items:center;font:12px var(--mono);letter-spacing:1px;text-transform:uppercase}
.tag{border-radius:999px;padding:2px 12px;font:600 12px var(--mono)}
.t-amber{background:rgba(255,197,61,.15);color:var(--amber);box-shadow:var(--ng-am)}
.t-glass{background:var(--glass2);color:var(--text)}
.sec{margin:34px 0 14px;display:flex;align-items:baseline;gap:12px}
.sec .no{font:700 12px var(--mono);color:var(--orange);text-shadow:var(--ng-o)}
.sec h2{font:700 14px var(--sans);letter-spacing:2.5px;text-transform:uppercase}
.sec .rule{flex:1;height:1px;background:var(--hair);align-self:center}
.sec .tag2{font:10px var(--mono);color:var(--muted);letter-spacing:1px}
.step{display:flex;align-items:center;gap:14px;padding:14px 20px;border-bottom:1px solid var(--hair)}
.step:last-child{border-bottom:none}
.step svg{flex:none;image-rendering:pixelated}
.step .sid{font:700 11px var(--mono);color:var(--muted);background:var(--glass2);border-radius:6px;padding:3px 8px;flex:none}
.step .t{flex:1;font-size:15px}
.step.done .t{color:var(--muted);text-decoration:line-through}
.step .t code{font:12.5px var(--mono);background:rgba(255,90,45,.14);color:var(--orange);border-radius:5px;padding:1px 6px}
.pill{font:600 11px var(--mono);letter-spacing:1px;text-transform:uppercase;border-radius:999px;padding:4px 12px;flex:none}
.p-done{background:rgba(61,220,151,.14);color:var(--green);box-shadow:var(--ng-g)}
.p-next{background:var(--orange);color:#16100D;box-shadow:var(--ng-o)}
.p-risk{background:rgba(255,107,107,.14);color:var(--red);box-shadow:var(--ng-r)}
.p-gate{background:rgba(167,139,250,.14);color:var(--violet);box-shadow:var(--ng-v)}
.ic-o{filter:drop-shadow(0 0 4px rgba(255,90,45,.6))}
.ic-g{filter:drop-shadow(0 0 4px rgba(61,220,151,.5))}
.ic-r{filter:drop-shadow(0 0 4px rgba(255,107,107,.5))}
.ic-v{filter:drop-shadow(0 0 4px rgba(167,139,250,.5))}
.callout{display:flex;gap:14px;padding:16px 20px;margin-top:14px;font-size:14px;align-items:flex-start}
.callout svg{flex:none;image-rendering:pixelated;margin-top:2px}
.callout b{color:var(--orange);text-shadow:var(--ng-o-soft)}
.split{display:grid;grid-template-columns:1.35fr 1fr;gap:14px;align-items:stretch}
@media (max-width:640px){.split{grid-template-columns:1fr}}
table{border-collapse:collapse;width:100%;font-size:13.5px}
th{text-align:left;font:600 10.5px var(--mono);letter-spacing:1.5px;text-transform:uppercase;color:var(--muted);padding:12px 20px;border-bottom:1px solid var(--hair)}
td{padding:11px 20px;border-bottom:1px solid var(--hair)}
tr:last-child td{border-bottom:none}
td:first-child{font:700 12px var(--mono);color:var(--orange);text-shadow:var(--ng-o-soft)}
td code{font:12px var(--mono);color:var(--text);background:var(--glass2);border-radius:5px;padding:1px 6px}
.termcard{padding:18px 20px;font:12.5px/1.8 var(--mono);overflow:hidden;
  background:rgba(13,16,21,.92)!important;color:#ECEAE6;border-color:rgba(255,255,255,.10)!important}
.termcard .p,.termcard .blab{color:#8B93A1}
.termcard .ok{color:#3DDC97;text-shadow:0 0 10px rgba(61,220,151,.45)}
.termcard .sk{color:#FFC53D;text-shadow:0 0 10px rgba(255,197,61,.40)}
.bars{display:flex;align-items:flex-end;gap:3px;height:70px;margin:4px 0 8px}
.bar{width:6px;border-radius:3px;background:rgba(255,255,255,.18)}
.bar.hot{background:var(--orange);box-shadow:0 0 12px rgba(255,90,45,.55)}
.bar.g{background:#3DDC97;box-shadow:0 0 8px rgba(61,220,151,.35)}
.blab{font:9.5px var(--mono);letter-spacing:1px;margin-bottom:12px}
.statmini{display:flex;gap:18px;font:12px var(--mono);color:#8B93A1;margin-bottom:10px}
.statmini b{font:700 20px var(--sans);color:#ECEAE6}
.matrix{display:flex;align-items:flex-end;gap:4px}
.mcol{display:flex;flex-direction:column-reverse;gap:3px}
.mpx{width:9px;height:9px;border-radius:2px;background:rgba(255,255,255,.14)}
.mpx.on{background:var(--orange);box-shadow:0 0 8px rgba(255,90,45,.45)}
.mpx.g{background:#3DDC97;box-shadow:0 0 6px rgba(61,220,151,.35)}
.gauge{display:flex;gap:3px}
.gcell{width:22px;height:10px;border-radius:2px;background:var(--glass2);border:1px solid var(--hair)}
.gcell.on{background:var(--orange);border-color:var(--orange);box-shadow:var(--ng-o-soft)}
.delta{font:700 12px var(--mono)}
.delta.up{color:var(--green);text-shadow:var(--ng-g)} .delta.down{color:var(--red);text-shadow:var(--ng-r)}
details{border-top:1px solid var(--hair);padding:10px 20px}
details summary{cursor:pointer;font:600 12px var(--mono);letter-spacing:1px;text-transform:uppercase;color:var(--muted)}
details[open] summary{color:var(--orange);text-shadow:var(--ng-o-soft)}
.foot{display:flex;justify-content:space-between;font:10.5px var(--mono);letter-spacing:1.5px;text-transform:uppercase;color:var(--muted);border-top:1.5px solid var(--text);margin-top:44px;padding-top:12px}
.colophon{margin-top:30px;padding-top:12px;border-top:1px dashed var(--hair);display:flex;justify-content:center;align-items:center;gap:10px;font:10px var(--mono);letter-spacing:2px;text-transform:uppercase;color:var(--muted)}
.colophon .mark{color:var(--orange);text-shadow:var(--ng-o);font-size:12px}
.colophon .repo{color:var(--text)}
/* scrollbars - thin pill, brand orange, stronger on hover.
   ENGINE TRAP: if scrollbar-color/scrollbar-width are set unconditionally, Chromium IGNORES all
   ::-webkit-scrollbar styling and renders a near-invisible native bar. The standard properties
   therefore apply ONLY where the webkit pseudos are unsupported (Firefox). Keep this guard. */
@supports not selector(::-webkit-scrollbar){
  html{scrollbar-width:thin;scrollbar-color:rgba(255,90,45,.55) transparent}
}
::-webkit-scrollbar{width:14px;height:12px;background:transparent}
::-webkit-scrollbar-track,::-webkit-scrollbar-track-piece{background:transparent;border:none;box-shadow:none}
::-webkit-scrollbar-button{display:none;width:0;height:0}
::-webkit-scrollbar-thumb{background:rgba(255,90,45,.55);border-radius:999px;border:4px solid transparent;background-clip:content-box}
::-webkit-scrollbar-thumb:hover{background:rgba(255,90,45,.85);background-clip:content-box}
::-webkit-scrollbar-corner{background:transparent}
.sec canvas{align-self:center}
.tbtn{white-space:nowrap}
.chrome{flex-wrap:wrap;row-gap:6px}
.foot{flex-wrap:wrap;row-gap:6px}
.colophon{flex-wrap:wrap;row-gap:4px;text-align:center}
.tblwrap{overflow-x:auto;-webkit-overflow-scrolling:touch}
@media (max-width:480px){
  .chrome,.kicker{letter-spacing:1px}
  .prop{flex-direction:column;align-items:flex-start;gap:4px}
  .prop .k{width:auto}
  .step{flex-wrap:wrap;row-gap:8px}
  th,td{padding:9px 12px}
  .hero{padding:32px 2px 24px}
}
@media print{.glass,.termcard{backdrop-filter:none!important;background:var(--bg)!important;box-shadow:none}
  body::before,body::after{display:none}.tbtn{display:none}}
```

## 2. The glow system - the kit's signature

**Every colored element glows; neutral elements never do.** Orange is the brand and glows
strongest; the other accents glow in their own color at lower intensity. Mechanics:

- Colored TEXT: `text-shadow: var(--ng-o)` (or `--ng-g/-r/-v/-am` to match the color).
- Colored FILLS and BORDERS (pills, bars, gauge cells): `box-shadow` with the same tokens.
- Pixel SVG ICONS: the `.ic-o/.ic-g/.ic-r/.ic-v` drop-shadow filters.
- The headline's accent letter: canvas `shadowColor="#FF5A2D"; shadowBlur=10`.

Hard rules: body text NEVER glows; `--muted` and `--text` never glow; light mode uses the reduced
tokens automatically (a strong glow on paper looks like a printing error - the tokens already
handle it, do not override). One glow per element, in the element's own color.

## 3. Fixed template chrome - IDENTICAL on every report

The header and the colophon are the template's signature. Use this markup verbatim, only swapping
the CAPITALISED content:

```html
<div class="frame">
<div class="chrome"><span>TYPE <span class="mark">&#9787;</span> DOC-NAME</span>
  <span class="r"><span>REV NN &nbsp;/&nbsp; YYYY-MM-DD</span>
  <button id="themebtn" class="tbtn">[ LIGHT ]</button></span></div>
...report content...
<div class="foot"><span>EDITS LAND IN SOURCE.MD &#8212; THIS PAGE IS A RENDER</span>
  <span>REV NN &#183; YYYY-MM-DD</span></div>
<div class="colophon"><span>GENERATED WITH THE-AGENT-KIT</span><span class="mark">&#9787;</span>
  <span>BUILT BY VIKASH CHAND</span><span>&#183;</span>
  <span class="repo">GITHUB.COM/VIKICHAND/THE-AGENT-KIT</span></div>
</div>
```

The colophon sits BELOW the document footer, separated by its dashed rule - deliberately outside
the document, like a plate mark on a print. Exact text, exact classes, always last, never louder.
It is the only place the kit names itself: never a badge, never in the headline, never in content.
(It credits the human and his tool; §9's ban on AI attribution governs git trailers and stands.)

Everything lives inside `.frame` (max-width 860px), so chrome, content, foot and colophon share
exact edges.

## 4. Hero

Kicker -> pixel headline -> metadata dots, in this order:

```html
<div class="hero">
  <div class="kicker"><span class="brk">[ 1/1 ]</span> DOC TYPE &#8212;&gt; CURRENT STATE</div>
  <canvas id="pxtitle" class="pxt" data-text="SHORT TITLE" data-accent="1" data-px="9" aria-label="SHORT TITLE"></canvas>
  <div class="sub">
    <span><span class="dot">&#9679;</span> ID <b>doc-id</b></span>
    <span><span class="dot">&#9679;</span> SOURCE OF TRUTH <b>source.md</b></span>
    <span><span class="dot">&#9679;</span> RENDER <b>disposable</b></span>
  </div>
</div>
```

The headline is DRAWN (no font dependency): 5x7 glyphs as rounded squares, one letter near the
middle in glowing orange. Keep titles short (2-3 words); the renderer reads `aria-label`.

```html
<script>
(function(){
  var root=document.documentElement, btn;
  function current(){ return root.getAttribute("data-theme")==="light" ? "light" : "dark"; }
  function apply(m){ if(m==="light"){root.setAttribute("data-theme","light");}else{root.removeAttribute("data-theme");}
    if(btn) btn.textContent = current()==="dark" ? "[ LIGHT ]" : "[ DARK ]";
    if(window.__drawTitle) window.__drawTitle(); }
  document.addEventListener("DOMContentLoaded",function(){
    btn=document.getElementById("themebtn");
    btn.addEventListener("click",function(){ apply(current()==="dark"?"light":"dark"); });
    apply("dark");
  });
})();
(function(){
  var G={A:["01110","10001","10001","11111","10001","10001","10001"],B:["11110","10001","11110","10001","10001","10001","11110"],C:["01110","10001","10000","10000","10000","10001","01110"],D:["11110","10001","10001","10001","10001","10001","11110"],E:["11111","10000","10000","11110","10000","10000","11111"],F:["11111","10000","10000","11110","10000","10000","10000"],G:["01110","10001","10000","10111","10001","10001","01110"],H:["10001","10001","10001","11111","10001","10001","10001"],I:["01110","00100","00100","00100","00100","00100","01110"],J:["00111","00010","00010","00010","00010","10010","01100"],K:["10001","10010","10100","11000","10100","10010","10001"],L:["10000","10000","10000","10000","10000","10000","11111"],M:["10001","11011","10101","10101","10001","10001","10001"],N:["10001","11001","10101","10011","10001","10001","10001"],O:["01110","10001","10001","10001","10001","10001","01110"],P:["11110","10001","10001","11110","10000","10000","10000"],Q:["01110","10001","10001","10001","10101","10010","01101"],R:["11110","10001","10001","11110","10100","10010","10001"],S:["01111","10000","10000","01110","00001","00001","11110"],T:["11111","00100","00100","00100","00100","00100","00100"],U:["10001","10001","10001","10001","10001","10001","01110"],V:["10001","10001","10001","10001","10001","01010","00100"],W:["10001","10001","10001","10101","10101","11011","10001"],X:["10001","01010","00100","00100","00100","01010","10001"],Y:["10001","01010","00100","00100","00100","00100","00100"],Z:["11111","00001","00010","00100","01000","10000","11111"],"0":["01110","10001","10011","10101","11001","10001","01110"],"1":["00100","01100","00100","00100","00100","00100","01110"],"2":["01110","10001","00001","00110","01000","10000","11111"],"3":["01110","10001","00001","00110","00001","10001","01110"],"4":["00010","00110","01010","10010","11111","00010","00010"],"5":["11111","10000","11110","00001","00001","10001","01110"],"6":["01110","10000","11110","10001","10001","10001","01110"],"7":["11111","00001","00010","00100","01000","01000","01000"],"8":["01110","10001","10001","01110","10001","10001","01110"],"9":["01110","10001","10001","01111","00001","00001","01110"],"-":["00000","00000","00000","01110","00000","00000","00000"]," ":["00000","00000","00000","00000","00000","00000","00000"]};
  function build(c){
    var text=(c.getAttribute("data-text")||c.getAttribute("aria-label")||"").toUpperCase();
    var px=parseFloat(c.getAttribute("data-px"))||9;
    var gap=px>=6?2:1, adv=6, dpr=window.devicePixelRatio||1;
    var w=(text.length*adv-1)*px, h=7*px;
    c.width=w*dpr; c.height=h*dpr;
    c.style.width=Math.min(w,820)+"px"; c.style.height="auto"; c.style.maxWidth="100%";
    var x=c.getContext("2d"); x.setTransform(dpr,0,0,dpr,0,0);
    function rr(a,b,s,r){x.beginPath();x.moveTo(a+r,b);x.arcTo(a+s,b,a+s,b+s,r);x.arcTo(a+s,b+s,a,b+s,r);x.arcTo(a,b+s,a,b,r);x.arcTo(a,b,a+s,b,r);x.fill();}
    return function(){
      var ink=getComputedStyle(document.documentElement).getPropertyValue("--px-ink").trim()||"#ECEAE6";
      x.clearRect(0,0,w,h);
      var accent=c.getAttribute("data-accent")==="1";
      var mid=Math.floor(text.length/2); var idx=text[mid]===" "?mid+1:mid;
      var rad=px>=6?2.6:1.1;
      for(var i=0;i<text.length;i++){var g=G[text[i]]||G[" "];
        if(accent&&i===idx){x.fillStyle="#FF5A2D";x.shadowColor="#FF5A2D";x.shadowBlur=10;}
        else{x.fillStyle=ink;x.shadowBlur=0;}
        for(var r=0;r<7;r++)for(var col=0;col<5;col++)
          if(g[r][col]==="1") rr((i*adv+col)*px,r*px,px-gap,rad);}
      x.shadowBlur=0;
    };
  }
  var fns=[]; var list=document.querySelectorAll("canvas.pxt");
  for(var i=0;i<list.length;i++) fns.push(build(list[i]));
  function drawAll(){for(var i=0;i<fns.length;i++)fns[i]();}
  window.__drawTitle=drawAll; drawAll();
})();
</script>
```

## 5. Components

- **Properties card** (`.glass.props` + `.prop` rows): Status / Source / Progress. Mono uppercase
  keys with a 12px pixel SVG, pill or plain values. First card after the hero.
- **Callout** (`.glass.callout`): pixel icon + bold lead phrase in the meaning's accent. Risk
  callouts add `style="border-color:rgba(255,90,45,.35);box-shadow:var(--cardshadow),var(--ng-o-soft)"`.
- **Step row** (`.step` inside `.glass`): pixel state icon with matching `.ic-*` glow, `Sn` chip,
  text, status pill. Done rows get `.done` (muted + strikethrough). Pills: done / next / risk / gate.
- **Table** (inside `.glass`, wrapped in `<div class="tblwrap">`): mono uppercase headers, hairline
  rows, first column glowing orange mono. The wrapper scrolls horizontally on narrow screens; the
  page never scrolls sideways.
- **Terminal card** (`.glass.termcard`): dark in BOTH themes - the deliberate contrast block. Holds
  mini-stats, a chart, a 9.5px caption, real command output. Command prompt in `.p`, pass counts in
  `.ok`, warnings in `.sk`.
- **Section header** (`.sec`): glowing `1.0` number, then the title as SMALL PIXEL TYPE - a
  `<canvas class="pxt" data-text="SECTION TITLE" data-px="3" role="heading" aria-level="2"
  aria-label="Section Title">` - then hairline rule and right micro-tag. Same renderer as the
  headline at 3px cells, plain ink, no accent letter.
- **Disclosure** (`details` inside a `.glass`): depth behind a mono uppercase `summary` that glows
  orange when open. Nothing important lives ONLY inside one.
- **Pixel icons**: inline SVGs on a 6-9px grid, `shape-rendering="crispEdges"`, with the matching
  `.ic-*` glow class. Stock glyphs: check, hollow/filled square, warning triangle, diamond, arrow,
  smiley `&#9787;` (text). Never emoji.

## 6. Infographics - the data vocabulary

Charts live inside cards (usually the terminal card). Each must earn its place or become a table.

- **Thin-bar chart** (`.bars` + `.bar`): categorical comparison. Neutral bars, `.hot` (orange,
  glowing) for the subject of the report, `.g` (green) for healthy/pass. Always a `.blab` caption
  saying what the colors mean. 10-20 bars max.
- **Pixel matrix** (`.matrix` > `.mcol` > `.mpx`): dot-matrix column chart for small counts
  (tests per file, findings per area) - stacked 9px cells, `.on` orange / `.g` green. The most
  on-brand chart; prefer it when values are small integers.
- **Progress gauge** (`.gauge` + `.gcell.on`): n-of-m completion as chunky cells. One row, one
  meaning.
- **Stat band** (`.statmini` or a 3-up glass grid): big number + tiny mono label. Deltas use
  `.delta.up/.down` with glow.
- **Sparkline-grade trends**: use the thin-bar chart; no line-chart library, no axes theatre -
  direct labels over legends, muted gridlines only if genuinely needed (Tufte's erasing test, kept
  humane: keep redundancy that aids reading).

## 7. Page anatomy and section skeletons

Order, every report: chrome -> hero -> properties -> "how to review" callout -> numbered sections ->
foot -> colophon. Numbered sections per report type (converging practice from published skills):

- **plan**: summary stats -> steps -> risk callout -> acceptance criteria -> current state
- **review/audit**: verdict banner -> score/pass-fail table -> findings (worst first) -> per-finding
  detail (disclosure for depth) -> recommendations
- **task completion**: summary -> changes made -> verification -> next steps
- **comparison**: options table -> per-option analysis -> recommendation

## 8. Pixel type - where it appears, and nowhere else

The dot font is the signature, and it stays scarce. It appears in EXACTLY three places:

1. The headline (`data-px="9"`, one glowing orange accent letter).
2. Section headings (`data-px="3"`, plain ink, no accent).
3. The `&#9787;` marks in chrome and colophon (text glyphs, not canvas).

Never at body sizes, never in tables, pills, captions or the terminal. The renderer draws every
`canvas.pxt` from its `data-text`/`data-px` attributes and re-inks all of them on theme toggle -
one script serves the whole page. Give each canvas an `aria-label` (and `role="heading"
aria-level="2"` for sections) so the page reads correctly to assistive tech.

## 9. Scrollbars

A **floating pill**: no rail, no track, no arrow buttons - just the thumb hovering in the gutter.
The trick is `background-clip:content-box` with a transparent 4px border, which insets the painted
pill inside a 14px scrollbar box so nothing touches the edges; track, track-piece, buttons and
corner are all explicitly transparent/hidden. Orange thumb (`rgba(255,90,45,.55)`, stronger on
hover), with
the standard `scrollbar-color`/`scrollbar-width` applied ONLY under a
`@supports not selector(::-webkit-scrollbar)` guard for Firefox. That guard is load-bearing:
without it Chromium discards the webkit styling entirely and shows a near-invisible native bar.
Same treatment on inner scrollers (`.tblwrap`, wide code). Do not restyle per report and never
OS-default chunky bars.

## 10. Glass guardrails and restraint

- Glass ONLY over the controlled ground (the glows + grid) - never over images or busy content.
- The fill is the barrier layer: body-text contrast holds at 4.5:1 (3:1 large text) measured with
  blur applied. If a glow makes text marginal, raise fill opacity, never lower text contrast.
- Blur stays 16px+. Print gets flat cards (the stylesheet's `@media print` block already does it).
- Banned: gradients as decoration, emoji headers, pixel font at body sizes, glow on body text or
  neutrals, more than the five accent colors, any external request.
- Density is handled by tables and disclosure, never by deleting information the reader needs.
- One page, one purpose. A report that wants a nav bar is two reports.
