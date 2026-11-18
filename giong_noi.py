# -*- coding: utf-8 -*-
"""
NÓI THAY VÌ GÕ - chuyển giọng nói thành văn bản ngay trong trình duyệt (Web Speech API),
dựa trên trang "giong-noi-thanh-van-ban.html".

    q = giong_noi("khoa_duy_nhat")
    if q: ...   # gõ hoặc nói trong cùng 1 ô; trả về 1 lần mỗi khi người dùng gửi

Lưu ý vận hành:
- Chạy trên Chrome / Edge / Safari bản mới; Firefox chưa hỗ trợ.
- Trình duyệt chỉ cho dùng micro trên HTTPS hoặc http://localhost
  (truy cập bằng http://<IP>:8501 sẽ bị chặn micro -> cần HTTPS, xem Hướng dẫn triển khai).
- Âm thanh được gửi tới dịch vụ nhận dạng của nhà cung cấp trình duyệt (Google / Microsoft / Apple)
  và cần Internet. Không đọc thông tin cá nhân của khách hàng khi dùng tính năng này.
"""
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from db import DATA_DIR

_HTML = r"""<!DOCTYPE html>
<html lang="vi"><head><meta charset="utf-8">
<style>
:root{--surface:#F0F2F6;--ink:#31333F;--muted:#6B6F7B;--accent:#FF4B4B;--live:#C8323C;--line:#D5D8DE;--interim:#8A8F99;--field:#F0F2F6}
:root.dark{--surface:#262730;--ink:#FAFAFA;--muted:#A3A8B4;--live:#FF6B72;--line:#3B3D48;--interim:#8E95A1;--field:#262730}
*{box-sizing:border-box}
body{margin:0;padding:2px 1px 2px;background:transparent;color:var(--ink);font-family:"Source Sans Pro","Source Sans 3",system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;font-size:16px;line-height:1.45}
.box{display:flex;align-items:flex-end;gap:.35rem;background:var(--field);border:1px solid var(--line);border-radius:10px;padding:.4rem .45rem .4rem .9rem;transition:border-color .15s}
.box:focus-within{border-color:var(--accent)}
.box.on{border-color:var(--live)}
textarea{flex:1;min-width:0;border:none;outline:none;background:transparent;color:var(--ink);font:inherit;resize:none;height:1.6rem;max-height:9rem;padding:.25rem 0;line-height:1.45;overflow-y:auto}
textarea::placeholder{color:var(--muted)}
.ib{position:relative;width:2.2rem;height:2.2rem;border-radius:8px;border:none;cursor:pointer;display:grid;place-items:center;flex:none;background:transparent;color:var(--muted)}
.ib:hover{background:rgba(127,127,127,.15);color:var(--ink)}
.ib:disabled{opacity:.35;cursor:not-allowed;background:transparent}
.ib svg{width:1.2rem;height:1.2rem}
.mic.on{background:var(--live);color:#fff}
.ring{position:absolute;inset:-3px;border-radius:10px;border:2px solid var(--live);opacity:0;pointer-events:none;transition:transform .08s linear,opacity .2s}
.mic.on .ring{opacity:.5}
.send:not(:disabled){color:var(--accent)}
.meta{display:flex;align-items:center;gap:.6rem;margin:.25rem .2rem 0;font-size:.8rem;color:var(--muted);min-height:1.2rem}
.status.err{color:var(--live)}
.interim{color:var(--interim);font-style:italic;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
select{font:inherit;font-size:.78rem;color:var(--muted);background:transparent;border:none;cursor:pointer}
</style></head><body>
<div class="box" id="box">
  <textarea id="text" rows="1" aria-label="Câu hỏi"></textarea>
  <button class="ib mic" id="mic" aria-pressed="false" aria-label="Hỏi bằng giọng nói" title="Hỏi bằng giọng nói">
    <span class="ring" id="ring"></span>
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10v1a7 7 0 0 0 14 0v-1"/><path d="M12 18v4"/></svg>
  </button>
  <button class="ib send" id="send" aria-label="Gửi" title="Gửi (Enter)">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 19V5"/><path d="M5 12l7-7 7 7"/></svg>
  </button>
</div>
<div class="meta">
  <span class="status" id="status" role="status">Gõ câu hỏi rồi nhấn Enter, hoặc bấm 🎤 để nói</span>
  <span class="interim" id="interim" aria-live="polite"></span>
  <select id="lang" aria-label="Ngôn ngữ nói" title="Ngôn ngữ nói"><option value="vi-VN" selected>Tiếng Việt</option><option value="en-US">English</option></select>
</div>
<script>
(function(){
  function post(type, extra){ window.parent.postMessage(Object.assign({isStreamlitMessage:true, type:type}, extra||{}), "*"); }
  function height(){ post("streamlit:setFrameHeight", {height: document.documentElement.scrollHeight}); }
  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  var box=document.getElementById('box'), mic=document.getElementById('mic'), ring=document.getElementById('ring'),
      statusEl=document.getElementById('status'), langSel=document.getElementById('lang'), text=document.getElementById('text'),
      interimEl=document.getElementById('interim'), sendBtn=document.getElementById('send');
  var rec=null, listening=false, audioCtx=null, stream=null, raf=null, idleMsg=statusEl.textContent;

  function setStatus(m, err){ statusEl.textContent=m; statusEl.classList.toggle('err', !!err); }
  function grow(){ if(!text.value){ text.style.height=''; height(); return; } text.style.height='auto'; text.style.height=Math.min(text.scrollHeight, 144)+'px'; height(); }
  function update(){ sendBtn.disabled=!text.value.trim(); grow(); }
  text.addEventListener('input', update); update();

  if (!SR){ mic.disabled=true; mic.title='Trình duyệt này chưa hỗ trợ nhận dạng giọng nói (dùng Chrome / Edge)'; langSel.style.display='none'; }
  else if (!window.isSecureContext){ mic.disabled=true; mic.title='Micro chỉ dùng được khi mở bằng HTTPS hoặc http://localhost'; langSel.style.display='none'; }

  function appendFinal(chunk){
    chunk=chunk.trim(); if(!chunk) return;
    var cur=text.value, sep=cur && !/\s$/.test(cur) ? ' ' : '';
    if (!cur.trim() || /[.!?…]\s*$/.test(cur)) chunk=chunk.charAt(0).toUpperCase()+chunk.slice(1);
    text.value=cur+sep+chunk; update();
  }
  function startMeter(){
    if(!navigator.mediaDevices||!navigator.mediaDevices.getUserMedia) return;
    navigator.mediaDevices.getUserMedia({audio:true}).then(function(s){
      stream=s; audioCtx=new (window.AudioContext||window.webkitAudioContext)();
      var an=audioCtx.createAnalyser(); an.fftSize=256; audioCtx.createMediaStreamSource(s).connect(an);
      var buf=new Uint8Array(an.fftSize);
      (function tick(){ an.getByteTimeDomainData(buf); var sum=0; for(var i=0;i<buf.length;i++){var v=(buf[i]-128)/128; sum+=v*v;}
        ring.style.transform='scale('+(1+Math.min(Math.sqrt(sum/buf.length)*3,.35))+')'; raf=requestAnimationFrame(tick); })();
    }).catch(function(){});
  }
  function stopMeter(){ if(raf) cancelAnimationFrame(raf); raf=null; if(stream) stream.getTracks().forEach(function(t){t.stop();}); stream=null;
    if(audioCtx) audioCtx.close(); audioCtx=null; ring.style.transform='scale(1)'; }
  function build(){
    var r=new SR(); r.lang=langSel.value; r.continuous=true; r.interimResults=true;
    r.onresult=function(e){ var interim=''; for(var i=e.resultIndex;i<e.results.length;i++){ var t=e.results[i][0].transcript;
      if(e.results[i].isFinal) appendFinal(t); else interim+=t; } interimEl.textContent=interim; };
    r.onerror=function(e){
      var map={'not-allowed':'Chưa được cấp quyền micro - bấm biểu tượng ổ khoá trên thanh địa chỉ để cho phép.',
        'service-not-allowed':'Trình duyệt chặn dịch vụ nhận dạng. Thử Chrome hoặc Edge.',
        'audio-capture':'Không tìm thấy micro.','network':'Mất kết nối Internet - nhận dạng giọng nói cần Internet.'};
      if(e.error==='no-speech'){ setStatus('Chưa nghe thấy gì, vẫn đang nghe…'); return; }
      if(e.error==='aborted') return;
      setStatus(map[e.error]||('Lỗi: '+e.error), true);
      if(['not-allowed','service-not-allowed','audio-capture'].indexOf(e.error)>=0) stop();
    };
    r.onend=function(){ if(listening){ try{ r.start(); }catch(err){} } };
    return r;
  }
  function start(){ rec=build(); try{ rec.start(); }catch(e){ setStatus('Không thể bắt đầu ghi', true); return; }
    listening=true; mic.classList.add('on'); box.classList.add('on'); mic.setAttribute('aria-pressed','true');
    setStatus('🔴 Đang nghe… nói xong bấm 🎤 để dừng, sửa nếu cần rồi nhấn Enter'); startMeter(); }
  function stop(){ listening=false; if(rec){ try{ rec.stop(); }catch(e){} } mic.classList.remove('on'); box.classList.remove('on');
    mic.setAttribute('aria-pressed','false'); interimEl.textContent=''; if(!statusEl.classList.contains('err')) setStatus(idleMsg); stopMeter(); text.focus(); }
  function send(){
    if(listening) stop();
    var v=text.value.trim(); if(!v) return;
    post("streamlit:setComponentValue", {value:{text:v, ts:Date.now()}, dataType:"json"});
    text.value=''; update(); setStatus(idleMsg);
  }
  mic.addEventListener('click', function(){ listening ? stop() : start(); });
  sendBtn.addEventListener('click', send);
  text.addEventListener('keydown', function(e){ if(e.key==='Enter' && !e.shiftKey && !e.isComposing){ e.preventDefault(); send(); } });
  langSel.addEventListener('change', function(){ if(listening){ stop(); start(); } });
  window.addEventListener('message', function(ev){
    var d=ev.data||{}; if(d.type!=="streamlit:render") return;
    var a=d.args||{}; if(a.placeholder) text.placeholder=a.placeholder; if(a.lang) langSel.value=a.lang;
    if(a.ghi_chu && a.ghi_chu!==idleMsg){ var wasIdle=(statusEl.textContent===idleMsg); idleMsg=a.ghi_chu; if(wasIdle) setStatus(idleMsg); }
    var th=d.theme||{}; document.documentElement.classList.toggle('dark', th.base==='dark');
    if(th.primaryColor) document.documentElement.style.setProperty('--accent', th.primaryColor);
    if(th.secondaryBackgroundColor) document.documentElement.style.setProperty('--field', th.secondaryBackgroundColor);
    if(th.textColor) document.documentElement.style.setProperty('--ink', th.textColor);
    height();
  });
  new ResizeObserver(height).observe(document.body);
  post("streamlit:componentReady", {apiVersion:1});
})();
</script></body></html>
"""

_DIR = Path(DATA_DIR) / ".components" / "giong_noi"
_DIR.mkdir(parents=True, exist_ok=True)
_index = _DIR / "index.html"
if not _index.exists() or _index.read_text(encoding="utf-8") != _HTML:
    _index.write_text(_HTML, encoding="utf-8")

_component = components.declare_component("giong_noi", path=str(_DIR))


def giong_noi(key, placeholder="Gõ câu hỏi hoặc bấm 🎤 để nói…", lang="vi-VN", ghi_chu=None, **_bo_qua):
    """Ô hỏi: gõ phím hoặc bấm 🎤 để nói ngay trong cùng một ô; Enter / nút ↑ để gửi.
    Trả về câu hỏi (str) đúng 1 lần mỗi lần gửi, ngược lại None."""
    value = _component(key=key, placeholder=placeholder, lang=lang, ghi_chu=ghi_chu, default=None)
    if isinstance(value, dict) and value.get("ts") != st.session_state.get(f"_gn_ts_{key}"):
        st.session_state[f"_gn_ts_{key}"] = value.get("ts")
        return (value.get("text") or "").strip() or None
    return None
