# -*- coding: utf-8 -*-
"""
Brandskins control panel + static site server.

  /        -> сам статический сайт (из примонтированного репозитория /site)
  /admin   -> панель управления:
                - список тем-брендов с цветовыми превью и переключением на лету
                - экстрактор: загрузка до 10 скриншотов (png/jpg/jpeg/webp),
                  авто-определение названия бренда с логотипа (OCR) и палитры
                - предпросмотр сайта в трёх размерах: мобильный, планшет, ПК
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import mimetypes

from flask import Flask, request, jsonify, send_file, abort, Response
from PIL import Image

try:
    import pytesseract
    _HAS_OCR = True
except Exception:
    pytesseract = None
    _HAS_OCR = False

SITE_ROOT = os.environ.get("SITE_ROOT", "/site")
CSS_DIR = os.path.join(SITE_ROOT, "css")
OUT_DIR = os.path.join(SITE_ROOT, "out")
EXTRACTOR = os.path.join(SITE_ROOT, "tools", "extract_brand.py")
STOCK_BACKUP = os.path.join(CSS_DIR, "brand.stock.css")
ACTIVE = os.path.join(CSS_DIR, "brand.css")

ALLOWED_EXT = {"png", "jpg", "jpeg", "webp"}
MAX_IMAGES = 10

# слова из шаблона/навигации, которые не являются названием бренда
OCR_STOP = {
    "logo", "review", "bonuses", "deposits", "app", "login", "log", "in",
    "withdraw", "register", "now", "menu", "placeholder", "section", "heading",
    "label", "column", "row", "provider", "game", "title", "offer", "bonus",
    "terms", "apply", "all", "tab", "hot", "new", "footer", "casino", "legal",
    "privacy", "policy", "cookies", "responsible", "gaming", "conditions",
    "main", "page", "goes", "here", "stat", "the", "and", "for", "your",
    "subsection", "frequently", "asked", "question", "lorem", "ipsum",
}

app = Flask(__name__)


# ----------------------------------------------------------------------------- helpers
def ensure_stock_backup():
    """Сохраняем эталонную brand.css как brand.stock.css один раз — при старте."""
    try:
        if os.path.isfile(ACTIVE) and not os.path.isfile(STOCK_BACKUP):
            shutil.copyfile(ACTIVE, STOCK_BACKUP)
    except Exception as e:
        app.logger.warning("stock backup failed: %s", e)


ensure_stock_backup()


def slugify(name):
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s or "brand"


def brand_key_from_filename(fn):
    m = re.match(r"^brand\.(.+)\.css$", fn)
    return m.group(1) if m else ""


def parse_theme_colors(path):
    """Достаём ключевые цвета темы для цветного превью в списке."""
    colors = {}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            txt = f.read()
    except Exception:
        return colors
    for var in ("--c-accent", "--c-cta", "--c-bg", "--surface"):
        m = re.search(re.escape(var) + r"\s*:\s*([^;]+);", txt)
        if m:
            colors[var.lstrip("-")] = m.group(1).strip()
    return colors


def list_brands():
    active_bytes = None
    if os.path.isfile(ACTIVE):
        with open(ACTIVE, "rb") as f:
            active_bytes = f.read()
    brands = []
    if os.path.isdir(CSS_DIR):
        for fn in sorted(os.listdir(CSS_DIR)):
            if not fn.startswith("brand.") or not fn.endswith(".css") or fn == "brand.css":
                continue
            key = brand_key_from_filename(fn)
            if not key:
                continue
            path = os.path.join(CSS_DIR, fn)
            try:
                with open(path, "rb") as f:
                    is_active = (f.read() == active_bytes)
            except Exception:
                is_active = False
            brands.append({
                "key": key,
                "file": fn,
                "label": key.replace(".", " · "),
                "active": is_active,
                "colors": parse_theme_colors(path),
            })
    any_active = any(b["active"] for b in brands)
    return brands, any_active


def safe_site_path(rel):
    rel = rel.lstrip("/")
    full = os.path.realpath(os.path.join(SITE_ROOT, rel))
    root = os.path.realpath(SITE_ROOT)
    if full != root and not full.startswith(root + os.sep):
        return None
    return full


def detect_brand_name(paths):
    """OCR по загруженным картинкам: ищем самое крупное «логотипное» слово."""
    if not _HAS_OCR:
        return ""
    best = None  # (score, word)
    for p in paths:
        try:
            im = Image.open(p).convert("RGB")
        except Exception:
            continue
        try:
            data = pytesseract.image_to_data(im, output_type=pytesseract.Output.DICT)
        except Exception:
            continue
        for i in range(len(data["text"])):
            w = (data["text"][i] or "").strip()
            if not w:
                continue
            try:
                conf = float(data["conf"][i])
            except (ValueError, TypeError):
                conf = -1
            try:
                h = int(data["height"][i])
            except (ValueError, TypeError):
                h = 0
            wl = re.sub(r"[^A-Za-z0-9]", "", w)
            if len(wl) < 2 or len(wl) > 20 or not re.search(r"[A-Za-z]", wl):
                continue
            if wl.lower() in OCR_STOP or conf < 45:
                continue
            score = h * (conf / 100.0)
            if best is None or score > best[0]:
                best = (score, wl)
    return best[1] if best else ""


def next_auto_name():
    i = 1
    while os.path.isfile(os.path.join(CSS_DIR, "brand.brand%d.css" % i)):
        i += 1
    return "brand%d" % i


# ----------------------------------------------------------------------------- API
@app.get("/admin/api/brands")
def api_brands():
    brands, any_active = list_brands()
    return jsonify({"brands": brands, "custom": not any_active, "ocr": _HAS_OCR})


@app.post("/admin/api/switch")
def api_switch():
    data = request.get_json(silent=True) or request.form
    key = (data.get("key") or "").strip()
    src = os.path.join(CSS_DIR, "brand.%s.css" % key)
    if not key or not os.path.isfile(src):
        return jsonify({"ok": False, "error": "Тема не найдена: %s" % key}), 400
    try:
        shutil.copyfile(src, ACTIVE)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": True, "active": key})


@app.post("/admin/api/extract")
def api_extract():
    if not os.path.isfile(EXTRACTOR):
        return jsonify({"ok": False, "error": "Экстрактор не найден: %s" % EXTRACTOR}), 500

    files = request.files.getlist("images")
    if not files:
        return jsonify({"ok": False, "error": "Не загружены скриншоты"}), 400
    if len(files) > MAX_IMAGES:
        files = files[:MAX_IMAGES]

    enforce = request.form.get("enforce_contrast") in ("1", "true", "on", "yes")
    try:
        variants = max(0, int(request.form.get("variants") or 0))
    except ValueError:
        variants = 0

    tmpdir = tempfile.mkdtemp(prefix="refs_")
    img_paths = []
    try:
        for i, f in enumerate(files):
            base = os.path.basename(f.filename or "shot%d" % i)
            ext = base.rsplit(".", 1)[-1].lower() if "." in base else ""
            if ext not in ALLOWED_EXT:
                return jsonify({"ok": False,
                                "error": "Формат не поддержан: %s (нужно png/jpg/jpeg/webp)" % base}), 400
            dst = os.path.join(tmpdir, "%02d_%s" % (i, base))
            f.save(dst)
            try:
                Image.open(dst).verify()       # это действительно картинка?
            except Exception:
                return jsonify({"ok": False, "error": "Битый файл: %s" % base}), 400
            img_paths.append(dst)

        # имя бренда: поле -> OCR с логотипа -> авто-нумерация
        name = (request.form.get("name") or "").strip()
        detected = ""
        if not name:
            detected = detect_brand_name(img_paths)
            name = detected or next_auto_name()
        slug = slugify(name)

        os.makedirs(OUT_DIR, exist_ok=True)
        out_css = os.path.join(CSS_DIR, "brand.%s.css" % slug)
        report = os.path.join(OUT_DIR, "%s-report.md" % slug)

        cmd = [sys.executable, EXTRACTOR, *img_paths,
               "--name", name, "-o", out_css, "--report", report]
        if enforce:
            cmd.append("--enforce-contrast")
        if variants > 0:
            cmd += ["--variants", str(variants)]

        proc = subprocess.run(cmd, cwd=SITE_ROOT, capture_output=True,
                              text=True, timeout=300)
        report_text = ""
        if os.path.isfile(report):
            with open(report, "r", encoding="utf-8", errors="replace") as rf:
                report_text = rf.read()

        ok = proc.returncode == 0 and os.path.isfile(out_css)
        return jsonify({
            "ok": ok,
            "name": name,
            "detected": detected,
            "slug": slug,
            "file": "brand.%s.css" % slug,
            "returncode": proc.returncode,
            "stdout": proc.stdout[-4000:],
            "stderr": proc.stderr[-4000:],
            "report": report_text[:20000],
        }), (200 if ok else 500)
    except subprocess.TimeoutExpired:
        return jsonify({"ok": False, "error": "Экстрактор не успел за 300с"}), 504
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


@app.get("/admin")
@app.get("/admin/")
def admin():
    return Response(DASHBOARD_HTML, mimetype="text/html; charset=utf-8")


# ----------------------------------------------------------------------------- static site
def _send_no_store(full):
    ctype, _ = mimetypes.guess_type(full)
    resp = send_file(full, mimetype=ctype) if ctype else send_file(full)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/")
def root_index():
    idx = os.path.join(SITE_ROOT, "index.html")
    return _send_no_store(idx) if os.path.isfile(idx) else abort(404)


@app.get("/<path:relpath>")
def static_site(relpath):
    if relpath == "admin" or relpath.startswith("admin/"):
        abort(404)
    full = safe_site_path(relpath)
    if not full:
        abort(404)
    if os.path.isfile(full):
        return _send_no_store(full)
    idx = os.path.join(full, "index.html")
    if os.path.isfile(idx):
        return _send_no_store(idx)
    abort(404)


DASHBOARD_HTML = r"""<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Brandskins · панель управления</title>
<style>
  :root{
    --bg:#0e1411;--panel:#151d18;--panel-2:#1b251f;--line:#27332b;--txt:#e8efe9;
    --muted:#8fa394;--gold:#e8b84b;--gold-hi:#f7d579;--gold-deep:#b6862c;
    --ok:#46c98a;--err:#e06464;--radius:14px;
  }
  *{box-sizing:border-box}
  body{margin:0;font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
       background:radial-gradient(1200px 600px at 80% -10%,#16201a,transparent),var(--bg);color:var(--txt);min-height:100vh}
  a{color:var(--gold)}
  header{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:18px 24px;
         border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5;
         background:rgba(14,20,17,.85);backdrop-filter:blur(8px)}
  .brand{display:flex;align-items:center;gap:12px;font-weight:700;letter-spacing:.3px}
  .dot{width:10px;height:10px;border-radius:50%;background:var(--gold);box-shadow:0 0 12px var(--gold)}
  .wrap{display:grid;grid-template-columns:minmax(0,400px) 1fr;gap:20px;padding:20px 24px;max-width:1600px;margin:0 auto}
  @media (max-width:980px){.wrap{grid-template-columns:1fr}}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:18px}
  .card h2{margin:0 0 4px;font-size:15px;letter-spacing:.4px;text-transform:uppercase;color:var(--gold)}
  .card .sub{margin:0 0 16px;color:var(--muted);font-size:13px}
  .mt{margin-top:14px}
  .muted{color:var(--muted)}
  code{font-family:ui-monospace,Menlo,monospace}
  /* brands */
  .brands{display:flex;flex-direction:column;gap:10px}
  .brow{display:flex;align-items:center;justify-content:space-between;gap:12px;background:var(--panel-2);
        border:1px solid var(--line);border-radius:12px;padding:12px 14px}
  .brow .meta{display:flex;flex-direction:column;gap:6px;min-width:0}
  .brow .name{font-weight:600}
  .brow .file{color:var(--muted);font-size:12px;font-family:ui-monospace,Menlo,monospace}
  .sw{display:flex;gap:5px;margin-top:2px}
  .sw i{width:18px;height:18px;border-radius:5px;border:1px solid rgba(255,255,255,.12);display:inline-block}
  .badge{font-size:11px;padding:3px 9px;border-radius:999px;background:rgba(70,201,138,.15);
         color:var(--ok);border:1px solid rgba(70,201,138,.35);white-space:nowrap}
  button{font:inherit;cursor:pointer;border-radius:10px;border:1px solid var(--line);
         background:var(--panel-2);color:var(--txt);padding:9px 14px;transition:.15s}
  button:hover{border-color:var(--gold-deep)}
  button.apply{background:linear-gradient(180deg,var(--gold-hi),var(--gold) 55%,var(--gold-deep));
               color:#1a130a;border:none;font-weight:700}
  button.apply:disabled{filter:grayscale(.4) brightness(.8);cursor:default}
  .field{display:flex;flex-direction:column;gap:6px;margin-bottom:14px}
  .field label{font-size:13px;color:var(--muted)}
  .hint{font-size:12px;color:var(--muted);margin-top:4px;line-height:1.45}
  input[type=text],input[type=number]{background:var(--panel-2);border:1px solid var(--line);
       border-radius:10px;color:var(--txt);padding:10px 12px;font:inherit}
  input[type=file]{font-size:13px;color:var(--muted)}
  .row{display:flex;gap:14px;align-items:center;flex-wrap:wrap}
  .check{display:flex;align-items:center;gap:8px;color:var(--muted);font-size:13px}
  pre{white-space:pre-wrap;word-break:break-word;background:#0b100d;border:1px solid var(--line);
      border-radius:10px;padding:12px;max-height:280px;overflow:auto;font-size:12px;color:var(--muted)}
  details summary{cursor:pointer;color:var(--muted);font-size:13px}
  /* preview devices */
  .preview-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px}
  .preview-head h2{margin:0}
  .devrow{display:flex;gap:18px;align-items:flex-start}
  @media (max-width:680px){.devrow{flex-direction:column}}
  .dev{display:flex;flex-direction:column;gap:8px;min-width:0}
  .devlabel{font-size:12px;color:var(--muted);letter-spacing:.3px}
  .frame{position:relative;width:100%;overflow:hidden;border:1px solid var(--line);border-radius:12px;background:#000}
  .frame .screen{position:absolute;top:0;left:0;transform-origin:top left}
  .frame iframe{width:100%;height:100%;border:0;display:block;background:#000}
  .toast{position:fixed;right:20px;bottom:20px;background:var(--panel-2);border:1px solid var(--line);
         border-left:3px solid var(--gold);border-radius:10px;padding:12px 16px;max-width:380px;
         box-shadow:0 8px 30px rgba(0,0,0,.4);opacity:0;transform:translateY(8px);transition:.2s;z-index:50}
  .toast.show{opacity:1;transform:none}
  .toast.ok{border-left-color:var(--ok)} .toast.err{border-left-color:var(--err)}
</style>
</head>
<body>
<header>
  <div class="brand"><span class="dot"></span> Brandskins · панель управления</div>
  <div><a href="/" target="_blank" rel="noopener">Открыть сайт ↗</a></div>
</header>

<div class="wrap">
  <div class="col">
    <div class="card">
      <h2>Темы брендов</h2>
      <p class="sub">Применение копирует выбранную тему в <code>css/brand.css</code> — сайт обновляется без пересборки.</p>
      <div class="brands" id="brands">загрузка…</div>
    </div>

    <div class="card mt">
      <h2>Экстрактор цветов</h2>
      <p class="sub">Загрузите до 10 скриншотов бренда — палитра и тема соберутся автоматически.</p>
      <div class="field">
        <label>Название бренда <span class="muted">(необязательно)</span></label>
        <input type="text" id="ex-name" placeholder="оставьте пустым — распознаю с логотипа">
        <div class="hint" id="ocr-hint">Если поле пустое — название считывается с логотипа на скриншотах (OCR). Если не распозналось — тема получит авто-имя.</div>
      </div>
      <div class="field">
        <label>Скриншоты — до 10 файлов (png, jpg, jpeg, webp)</label>
        <input type="file" id="ex-files" accept=".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp" multiple>
      </div>
      <div class="row mt">
        <label class="check"><input type="checkbox" id="ex-contrast" checked> проверка контраста (WCAG)</label>
        <label class="check">варианты акцента
          <input type="number" id="ex-variants" value="0" min="0" max="8" style="width:64px">
        </label>
      </div>
      <div class="hint">
        <b>Акцент</b> — главный выделяющий цвет шаблона (кнопки, активные пункты меню, цифры, рамки, свечение).
        Основную тему экстрактор делает сам. <b>Варианты акцента = N</b> — это N дополнительных тем,
        где акцентом взяты другие заметные цвета со скриншотов, чтобы было из чего выбрать
        (файлы <code>…alt1.css</code>, <code>…alt2.css</code>). Реальное число ограничено тем,
        сколько разных цветов нашлось на картинках.
      </div>
      <div class="mt"><button id="ex-run" class="apply">Сгенерировать тему</button></div>
      <div id="ex-result" class="mt"></div>
    </div>
  </div>

  <div class="col">
    <div class="card">
      <div class="preview-head">
        <h2>Превью сайта</h2>
        <button id="reload">Обновить ⟳</button>
      </div>
      <div class="devrow">
        <div class="dev" style="flex:390 1 0">
          <div class="devlabel">📱 Мобильная · 390px</div>
          <div class="frame" data-w="390" data-h="844" data-maxh="560">
            <div class="screen"><iframe id="pv-mobile" src="/" loading="lazy"></iframe></div>
          </div>
        </div>
        <div class="dev" style="flex:820 1 0">
          <div class="devlabel">📲 Планшет · 820px</div>
          <div class="frame" data-w="820" data-h="1180" data-maxh="560">
            <div class="screen"><iframe id="pv-tablet" src="/" loading="lazy"></iframe></div>
          </div>
        </div>
      </div>
      <div class="dev mt" style="margin-top:18px">
        <div class="devlabel">🖥 ПК · 1440px</div>
        <div class="frame" data-w="1440" data-h="900" data-maxh="720">
          <div class="screen"><iframe id="pv-desktop" src="/" loading="lazy"></iframe></div>
        </div>
      </div>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
const $=s=>document.querySelector(s);
const $$=s=>Array.from(document.querySelectorAll(s));
function toast(m,k){const t=$("#toast");t.textContent=m;t.className="toast show "+(k||"");setTimeout(()=>t.className="toast",3400);}
function escapeHtml(s){return (s||"").replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));}

function fitDevices(){
  $$(".frame").forEach(fr=>{
    const w=+fr.dataset.w,h=+fr.dataset.h,maxh=+fr.dataset.maxh||700;
    const avail=fr.clientWidth||1;
    let k=avail/w; if(h*k>maxh)k=maxh/h;
    const sc=fr.querySelector(".screen");
    sc.style.width=w+"px"; sc.style.height=h+"px"; sc.style.transform="scale("+k+")";
    const scaledW=w*k;
    sc.style.left=Math.max(0,(avail-scaledW)/2)+"px";
    fr.style.height=(h*k)+"px";
  });
}
let rt;window.addEventListener("resize",()=>{clearTimeout(rt);rt=setTimeout(fitDevices,120);});

function reloadPreview(){
  const t=Date.now();
  ["pv-mobile","pv-tablet","pv-desktop"].forEach(id=>{const f=document.getElementById(id);if(f)f.src="/?_t="+t;});
  setTimeout(fitDevices,60);
}
$("#reload").onclick=reloadPreview;

async function loadBrands(){
  const box=$("#brands");
  try{
    const r=await fetch("/admin/api/brands");const d=await r.json();
    if(!d.ocr){$("#ocr-hint").innerHTML="OCR недоступен в этом контейнере — название берётся из поля или авто-имя. Пересоберите образ, чтобы включить распознавание с логотипа.";}
    box.innerHTML="";
    if(d.custom){
      const n=document.createElement("div");n.className="muted";n.style.marginBottom="10px";
      n.textContent="Активная brand.css изменена вручную и не совпадает ни с одной темой.";box.appendChild(n);
    }
    d.brands.forEach(b=>{
      const row=document.createElement("div");row.className="brow";
      const meta=document.createElement("div");meta.className="meta";
      const nm=document.createElement("div");nm.className="name";nm.textContent=b.label;
      const fl=document.createElement("div");fl.className="file";fl.textContent=b.file;
      const sw=document.createElement("div");sw.className="sw";
      ["c-accent","c-cta","c-bg","surface"].forEach(c=>{
        if(b.colors&&b.colors[c]){const i=document.createElement("i");i.style.background=b.colors[c];i.title=c+": "+b.colors[c];sw.appendChild(i);}
      });
      meta.appendChild(nm);meta.appendChild(fl);if(sw.children.length)meta.appendChild(sw);
      const right=document.createElement("div");right.className="row";
      if(b.active){const bd=document.createElement("span");bd.className="badge";bd.textContent="активна";right.appendChild(bd);}
      else{const bt=document.createElement("button");bt.className="apply";bt.textContent="Применить";bt.onclick=()=>switchBrand(b.key,bt);right.appendChild(bt);}
      row.appendChild(meta);row.appendChild(right);box.appendChild(row);
    });
    if(!d.brands.length)box.innerHTML="<div class='muted'>Тем не найдено в css/</div>";
  }catch(e){box.innerHTML="<div class='muted'>Ошибка загрузки: "+e+"</div>";}
}

async function switchBrand(key,btn){
  if(btn){btn.disabled=true;btn.textContent="…";}
  try{
    const r=await fetch("/admin/api/switch",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({key})});
    const d=await r.json();
    if(d.ok){toast("Тема применена: "+key,"ok");await loadBrands();reloadPreview();}
    else toast(d.error||"Ошибка","err");
  }catch(e){toast(String(e),"err");}
  finally{if(btn){btn.disabled=false;btn.textContent="Применить";}}
}

$("#ex-run").onclick=async()=>{
  const files=$("#ex-files").files;
  if(!files.length){toast("Выберите скриншоты","err");return;}
  if(files.length>10){toast("Не больше 10 файлов","err");return;}
  const fd=new FormData();
  fd.append("name",$("#ex-name").value||"");
  fd.append("enforce_contrast",$("#ex-contrast").checked?"1":"0");
  fd.append("variants",$("#ex-variants").value||"0");
  for(const f of files)fd.append("images",f);
  const btn=$("#ex-run");btn.disabled=true;btn.textContent="Обработка…";
  const res=$("#ex-result");res.innerHTML="<span class='muted'>Запуск экстрактора…</span>";
  try{
    const r=await fetch("/admin/api/extract",{method:"POST",body:fd});const d=await r.json();
    if(d.ok){
      toast("Создана тема "+d.file,"ok");
      let html="<p class='muted'>Тема: <b style='color:var(--txt)'>"+escapeHtml(d.name)+"</b> → <code>css/"+escapeHtml(d.file)+"</code></p>";
      if(d.detected)html+="<p class='muted'>Название распознано с логотипа: <b style='color:var(--txt)'>"+escapeHtml(d.detected)+"</b></p>";
      if(d.report)html+="<details open><summary>Отчёт по палитре</summary><pre>"+escapeHtml(d.report)+"</pre></details>";
      res.innerHTML=html;await loadBrands();
    }else{
      res.innerHTML="<pre>"+escapeHtml((d.error||"")+"\n"+(d.stderr||"")+"\n"+(d.stdout||""))+"</pre>";
      toast("Ошибка экстрактора","err");
    }
  }catch(e){res.innerHTML="<pre>"+escapeHtml(String(e))+"</pre>";toast(String(e),"err");}
  finally{btn.disabled=false;btn.textContent="Сгенерировать тему";}
};

loadBrands();
window.addEventListener("load",()=>setTimeout(fitDevices,80));
setTimeout(fitDevices,300);
</script>
</body>
</html>
"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8888)))
