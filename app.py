# -*- coding: utf-8 -*-
"""
Brandskins control panel + static site server.

Один процесс делает две вещи:
  *  /            -> отдаёт сам статический сайт (из примонтированного репозитория)
  *  /admin       -> веб-дашборд для управления:
                       - переключение активной brand-темы на лету
                       - запуск экстрактора цветов (tools/extract_brand.py)
                         прямо из браузера (загрузил скриншоты -> новая тема)

Сайт-репозиторий монтируется в /site (см. docker-compose).
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import mimetypes

from flask import Flask, request, jsonify, send_file, abort, Response

SITE_ROOT = os.environ.get("SITE_ROOT", "/site")
CSS_DIR = os.path.join(SITE_ROOT, "css")
OUT_DIR = os.path.join(SITE_ROOT, "out")
EXTRACTOR = os.path.join(SITE_ROOT, "tools", "extract_brand.py")
STOCK_BACKUP = os.path.join(CSS_DIR, "brand.stock.css")
ACTIVE = os.path.join(CSS_DIR, "brand.css")

app = Flask(__name__)


# ----------------------------------------------------------------------------- helpers
def ensure_stock_backup():
    """Сохраняем «стоковую» brand.css как brand.stock.css один раз — при самом
    первом запуске, ДО любых переключений, чтобы всегда можно было откатиться."""
    try:
        if os.path.isfile(ACTIVE) and not os.path.isfile(STOCK_BACKUP):
            shutil.copyfile(ACTIVE, STOCK_BACKUP)
    except Exception as e:
        app.logger.warning("stock backup failed: %s", e)


# фиксируем эталонную тему сразу при импорте модуля (срабатывает один раз
# при старте контейнера, до того как пользователь что-либо переключит)
ensure_stock_backup()


def slugify(name):
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s or "brand"


def brand_key_from_filename(fn):
    # brand.fraga.alt1.css -> fraga.alt1 ; brand.css -> "" (активная, исключаем)
    m = re.match(r"^brand\.(.+)\.css$", fn)
    return m.group(1) if m else ""


def list_brands():
    ensure_stock_backup()
    active_bytes = None
    if os.path.isfile(ACTIVE):
        with open(ACTIVE, "rb") as f:
            active_bytes = f.read()

    brands = []
    if os.path.isdir(CSS_DIR):
        for fn in sorted(os.listdir(CSS_DIR)):
            if not fn.startswith("brand.") or not fn.endswith(".css"):
                continue
            if fn == "brand.css":
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
                "size": os.path.getsize(path),
            })
    any_active = any(b["active"] for b in brands)
    return brands, any_active


def safe_site_path(rel):
    """Защита от path traversal: путь обязан лежать внутри SITE_ROOT."""
    rel = rel.lstrip("/")
    full = os.path.realpath(os.path.join(SITE_ROOT, rel))
    root = os.path.realpath(SITE_ROOT)
    if full != root and not full.startswith(root + os.sep):
        return None
    return full


# ----------------------------------------------------------------------------- dashboard API
@app.get("/admin/api/brands")
def api_brands():
    brands, any_active = list_brands()
    return jsonify({"brands": brands, "custom": not any_active})


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

    name = (request.form.get("name") or "Brand").strip()
    slug = slugify(name)
    enforce = request.form.get("enforce_contrast") in ("1", "true", "on", "yes")
    try:
        variants = int(request.form.get("variants") or 0)
    except ValueError:
        variants = 0

    tmpdir = tempfile.mkdtemp(prefix="refs_")
    img_paths = []
    try:
        for i, f in enumerate(files):
            base = os.path.basename(f.filename or "shot%d.png" % i) or "shot%d.png" % i
            dst = os.path.join(tmpdir, "%02d_%s" % (i, base))
            f.save(dst)
            img_paths.append(dst)

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


@app.get("/admin/api/status")
def api_status():
    brands, any_active = list_brands()
    return jsonify({
        "site_root": SITE_ROOT,
        "has_index": os.path.isfile(os.path.join(SITE_ROOT, "index.html")),
        "has_extractor": os.path.isfile(EXTRACTOR),
        "brand_count": len(brands),
    })


# ----------------------------------------------------------------------------- dashboard UI
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
    if os.path.isfile(idx):
        return _send_no_store(idx)
    abort(404)


@app.get("/<path:relpath>")
def static_site(relpath):
    if relpath == "admin" or relpath.startswith("admin/"):
        abort(404)
    full = safe_site_path(relpath)
    if not full:
        abort(404)
    if os.path.isdir(full):
        idx = os.path.join(full, "index.html")
        if os.path.isfile(idx):
            return _send_no_store(idx)
        abort(404)
    if os.path.isfile(full):
        return _send_no_store(full)
    # директория без завершающего слеша
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
    --bg:#0e1411; --panel:#151d18; --panel-2:#1b251f; --line:#27332b;
    --txt:#e8efe9; --muted:#8fa394; --gold:#e8b84b; --gold-hi:#f7d579;
    --gold-deep:#b6862c; --ok:#46c98a; --err:#e06464; --radius:14px;
  }
  *{box-sizing:border-box}
  body{margin:0;font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
       background:radial-gradient(1200px 600px at 80% -10%,#16201a,transparent),var(--bg);color:var(--txt);min-height:100vh}
  a{color:var(--gold)}
  header{display:flex;align-items:center;justify-content:space-between;gap:16px;
         padding:18px 24px;border-bottom:1px solid var(--line);position:sticky;top:0;z-index:5;
         background:rgba(14,20,17,.85);backdrop-filter:blur(8px)}
  .brand{display:flex;align-items:center;gap:12px;font-weight:700;letter-spacing:.3px}
  .dot{width:10px;height:10px;border-radius:50%;background:var(--gold);box-shadow:0 0 12px var(--gold)}
  header .links{display:flex;gap:16px;font-size:14px}
  .wrap{display:grid;grid-template-columns:minmax(0,420px) 1fr;gap:20px;padding:20px 24px;max-width:1400px;margin:0 auto}
  @media (max-width:900px){.wrap{grid-template-columns:1fr}}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:18px 18px 20px}
  .card h2{margin:0 0 4px;font-size:15px;letter-spacing:.4px;text-transform:uppercase;color:var(--gold)}
  .card .sub{margin:0 0 16px;color:var(--muted);font-size:13px}
  .brands{display:flex;flex-direction:column;gap:10px}
  .brow{display:flex;align-items:center;justify-content:space-between;gap:12px;
        background:var(--panel-2);border:1px solid var(--line);border-radius:12px;padding:12px 14px}
  .brow .meta{display:flex;flex-direction:column;gap:2px;min-width:0}
  .brow .name{font-weight:600}
  .brow .file{color:var(--muted);font-size:12px;font-family:ui-monospace,Menlo,monospace}
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
  input[type=text],input[type=number]{background:var(--panel-2);border:1px solid var(--line);
       border-radius:10px;color:var(--txt);padding:10px 12px;font:inherit}
  input[type=file]{font-size:13px;color:var(--muted)}
  .row{display:flex;gap:14px;align-items:center;flex-wrap:wrap}
  .check{display:flex;align-items:center;gap:8px;color:var(--muted);font-size:13px}
  .preview-card{padding:0;overflow:hidden;display:flex;flex-direction:column}
  .preview-head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:14px 18px;border-bottom:1px solid var(--line)}
  .preview-head h2{margin:0}
  iframe{width:100%;height:72vh;border:0;background:#000}
  pre{white-space:pre-wrap;word-break:break-word;background:#0b100d;border:1px solid var(--line);
      border-radius:10px;padding:12px;max-height:280px;overflow:auto;font-size:12px;color:var(--muted)}
  .toast{position:fixed;right:20px;bottom:20px;background:var(--panel-2);border:1px solid var(--line);
         border-left:3px solid var(--gold);border-radius:10px;padding:12px 16px;max-width:360px;
         box-shadow:0 8px 30px rgba(0,0,0,.4);opacity:0;transform:translateY(8px);transition:.2s;z-index:50}
  .toast.show{opacity:1;transform:none}
  .toast.ok{border-left-color:var(--ok)} .toast.err{border-left-color:var(--err)}
  .muted{color:var(--muted)} .mt{margin-top:14px}
  details summary{cursor:pointer;color:var(--muted);font-size:13px}
</style>
</head>
<body>
<header>
  <div class="brand"><span class="dot"></span> Brandskins · панель управления</div>
  <div class="links">
    <a href="/" target="_blank" rel="noopener">Открыть сайт ↗</a>
  </div>
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
      <p class="sub">Загрузите 1–5 скриншотов бренда — скрипт соберёт палитру и создаст новую тему.</p>
      <div class="field">
        <label>Название бренда</label>
        <input type="text" id="ex-name" placeholder="например, MyCasino">
      </div>
      <div class="field">
        <label>Скриншоты (png / jpg)</label>
        <input type="file" id="ex-files" accept="image/*" multiple>
      </div>
      <div class="row mt">
        <label class="check"><input type="checkbox" id="ex-contrast" checked> проверка контраста (WCAG)</label>
        <label class="check">варианты акцента
          <input type="number" id="ex-variants" value="0" min="0" max="4" style="width:64px">
        </label>
      </div>
      <div class="mt"><button id="ex-run" class="apply">Сгенерировать тему</button></div>
      <div id="ex-result" class="mt"></div>
    </div>
  </div>

  <div class="col">
    <div class="card preview-card">
      <div class="preview-head">
        <h2>Превью сайта</h2>
        <button id="reload">Обновить ⟳</button>
      </div>
      <iframe id="preview" src="/"></iframe>
    </div>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
const $ = s => document.querySelector(s);
function toast(msg, kind){
  const t=$("#toast"); t.textContent=msg; t.className="toast show "+(kind||"");
  setTimeout(()=>t.className="toast",3200);
}
function reloadPreview(){
  const f=$("#preview"); f.src="/?_t="+Date.now();
}
$("#reload").onclick=reloadPreview;

async function loadBrands(){
  const box=$("#brands");
  try{
    const r=await fetch("/admin/api/brands"); const d=await r.json();
    box.innerHTML="";
    if(d.custom){
      const note=document.createElement("div");
      note.className="muted"; note.style.marginBottom="10px";
      note.textContent="Активная brand.css не совпадает ни с одной темой (изменена вручную).";
      box.appendChild(note);
    }
    d.brands.forEach(b=>{
      const row=document.createElement("div"); row.className="brow";
      const meta=document.createElement("div"); meta.className="meta";
      const nm=document.createElement("div"); nm.className="name"; nm.textContent=b.label;
      const fl=document.createElement("div"); fl.className="file"; fl.textContent=b.file;
      meta.appendChild(nm); meta.appendChild(fl);
      const right=document.createElement("div"); right.className="row";
      if(b.active){
        const bd=document.createElement("span"); bd.className="badge"; bd.textContent="активна";
        right.appendChild(bd);
      }else{
        const btn=document.createElement("button"); btn.className="apply"; btn.textContent="Применить";
        btn.onclick=()=>switchBrand(b.key,btn);
        right.appendChild(btn);
      }
      row.appendChild(meta); row.appendChild(right); box.appendChild(row);
    });
    if(!d.brands.length) box.innerHTML="<div class='muted'>Тем не найдено в css/</div>";
  }catch(e){ box.innerHTML="<div class='muted'>Ошибка загрузки: "+e+"</div>"; }
}

async function switchBrand(key,btn){
  if(btn){btn.disabled=true;btn.textContent="…";}
  try{
    const r=await fetch("/admin/api/switch",{method:"POST",
      headers:{"Content-Type":"application/json"},body:JSON.stringify({key})});
    const d=await r.json();
    if(d.ok){ toast("Тема применена: "+key,"ok"); await loadBrands(); reloadPreview(); }
    else { toast(d.error||"Ошибка","err"); }
  }catch(e){ toast(String(e),"err"); }
  finally{ if(btn){btn.disabled=false;btn.textContent="Применить";} }
}

$("#ex-run").onclick=async()=>{
  const files=$("#ex-files").files;
  if(!files.length){ toast("Выберите скриншоты","err"); return; }
  const fd=new FormData();
  fd.append("name",$("#ex-name").value||"Brand");
  fd.append("enforce_contrast",$("#ex-contrast").checked?"1":"0");
  fd.append("variants",$("#ex-variants").value||"0");
  for(const f of files) fd.append("images",f);
  const btn=$("#ex-run"); btn.disabled=true; btn.textContent="Обработка…";
  const res=$("#ex-result"); res.innerHTML="<span class='muted'>Запуск экстрактора…</span>";
  try{
    const r=await fetch("/admin/api/extract",{method:"POST",body:fd});
    const d=await r.json();
    if(d.ok){
      toast("Создана тема "+d.file,"ok");
      let html="<p class='muted'>Файл: <code>css/"+d.file+"</code> — появился в списке тем.</p>";
      if(d.report) html+="<details open><summary>Отчёт</summary><pre>"+escapeHtml(d.report)+"</pre></details>";
      res.innerHTML=html;
      await loadBrands();
    }else{
      res.innerHTML="<pre>"+escapeHtml((d.error||"")+"\n"+(d.stderr||"")+"\n"+(d.stdout||""))+"</pre>";
      toast("Экстрактор завершился с ошибкой","err");
    }
  }catch(e){ res.innerHTML="<pre>"+escapeHtml(String(e))+"</pre>"; toast(String(e),"err"); }
  finally{ btn.disabled=false; btn.textContent="Сгенерировать тему"; }
};

function escapeHtml(s){return (s||"").replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));}

loadBrands();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8888)))
