// Helper: toast
function toast(msg, ok=true){
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.remove('hidden');
  t.style.borderColor = ok ? '#1f5ec3' : '#743232';
  setTimeout(()=>t.classList.add('hidden'), 3000);
}

// Elements
const creditsEl = document.getElementById('credits');
const priceEl = document.getElementById('price');
const progressBox = document.getElementById('progress');
const progressMsg = document.getElementById('progressMsg');
const fileInput = document.getElementById('fileInput');
const fileList = document.getElementById('fileList');
const dropzone = document.getElementById('dropzone');

const email = document.getElementById('email');
const password = document.getElementById('password');
const loginBtn = document.getElementById('loginBtn');
const signupBtn = document.getElementById('signupBtn');
const logoutBtn = document.getElementById('logoutBtn');
const chooseBtn = document.getElementById('chooseBtn');
const topupBtn = document.getElementById('topupBtn');
const stampBtn = document.getElementById('stampBtn');

const dateEl = document.getElementById('date');
const cropEl = document.getElementById('crop');
const startEl = document.getElementById('start');
const endEl = document.getElementById('end');

// Defaults
(function setDefaults(){
  const d = new Date();
  const dd = String(d.getDate()).padStart(2,'0');
  const mm = String(d.getMonth()+1).padStart(2,'0');
  const yyyy = d.getFullYear();
  dateEl.value = `${dd}/${mm}/${yyyy}`;
  startEl.value = "09:00:00";
  endEl.value = "09:05:00";
})();

// API helpers
async function api(url, opts={}){
  const res = await fetch(url, {credentials:'include', ...opts});
  if(!res.ok){
    const txt = await res.text();
    throw new Error(txt || res.statusText);
  }
  const ct = res.headers.get('content-type')||'';
  if(ct.includes('application/json')) return res.json();
  return res; // for blobs/streams
}

async function refreshStatus(){
  try{
    const data = await api('/auth/status');
    creditsEl.textContent = data.credits ?? '?';
    priceEl.textContent = data.credit_cost_gbp ?? '20';
  }catch(e){
    creditsEl.textContent = '?';
  }
}

// Auth
loginBtn.onclick = async ()=>{
  try{
    await api('/auth/login', {
      method:'POST',
      headers:{'content-type':'application/json'},
      body: JSON.stringify({email: email.value.trim(), password: password.value})
    });
    toast('Logged in');
    refreshStatus();
  }catch(e){ toast(e.message,false); }
};

signupBtn.onclick = async ()=>{
  try{
    await api('/auth/signup', {
      method:'POST',
      headers:{'content-type':'application/json'},
      body: JSON.stringify({email: email.value.trim(), password: password.value})
    });
    toast('Account created. You can login now.');
  }catch(e){ toast(e.message,false); }
};

logoutBtn.onclick = async ()=>{
  try{
    await api('/auth/logout', {method:'POST'});
    toast('Logged out');
    refreshStatus();
  }catch(e){ toast(e.message,false); }
};

topupBtn.onclick = async ()=>{
  try{
    await api('/auth/topup_demo', {method:'POST'});
    toast('Added 5 demo credits');
    refreshStatus();
  }catch(e){ toast('Demo top-up not enabled', false); }
};

// File chooser
chooseBtn.onclick = ()=> fileInput.click();
fileInput.onchange = ()=> renderFiles(fileInput.files);

// Dropzone
function prevent(e){ e.preventDefault(); e.stopPropagation(); }
['dragenter','dragover','dragleave','drop'].forEach(ev=>{
  dropzone.addEventListener(ev, prevent, false);
});
dropzone.addEventListener('drop', (e)=>{
  const dt = e.dataTransfer;
  if(!dt) return;
  const files = dt.files;
  fileInput.files = files;
  renderFiles(files);
});

function renderFiles(list){
  if(!list || !list.length){ fileList.textContent = ''; return; }
  const names = [...list].map(f=>`${f.name} (${Math.round(f.size/1024)} KB)`);
  fileList.textContent = names.join('  •  ');
}

// Stamp & download
stampBtn.onclick = async ()=>{
  try{
    const files = fileInput.files;
    if(!files || !files.length) throw new Error('Please add images or a .zip');
    const fd = new FormData();
    [...files].forEach(f=> fd.append('files', f, f.name));
    fd.append('date', dateEl.value.trim());
    fd.append('start_time', startEl.value.trim());
    fd.append('end_time', endEl.value.trim());
    fd.append('crop_height', cropEl.value.trim());

    progressBox.classList.remove('hidden');
    progressMsg.textContent = 'Processing…';

    const res = await api('/api/stamp', {method:'POST', body: fd});
    // server streams zip; in our API helper res is the Response
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = 'stamped_images.zip';
    document.body.appendChild(a); a.click();
    a.remove(); URL.revokeObjectURL(url);

    progressMsg.textContent = 'Done';
    setTimeout(()=>progressBox.classList.add('hidden'), 500);
    refreshStatus();
  }catch(e){
    progressBox.classList.add('hidden');
    toast(e.message, false);
  }
};

// Kick off
refreshStatus();
