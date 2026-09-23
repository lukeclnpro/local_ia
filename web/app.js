
const $=s=>document.querySelector(s);
let state={models:[],chats:[],current:null};

function esc(s){return String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[c]))}
async function api(url,opt){const r=await fetch(url,opt);let d;try{d=await r.json()}catch{throw new Error("Réponse serveur invalide")};if(!r.ok||d.error)throw new Error(d.error||("HTTP "+r.status));return d}
function show(page){document.querySelectorAll(".page").forEach(x=>x.classList.add("hidden"));$("#"+page).classList.remove("hidden");document.querySelectorAll(".nav").forEach(x=>x.classList.toggle("active",x.dataset.page===page));if(page==="chat")refreshChats()}

async function refresh(){
 try{
  const [s,m,c,ci]=await Promise.all([api("/api/status"),api("/api/models"),api("/api/chats"),api("/api/config-info")]);
  state.models=m.installed||[];state.chats=c.chats||[];
  $("#status").textContent=s.ok?"Ollama connecté":"Ollama inaccessible";
  $("#status").className=s.ok?"ok":"error";
  $("#ollama").textContent=s.ollama;
  $("#defaultModel").textContent=s.model||"Aucun";
  $("#modelCount").textContent=state.models.length;
  $("#chatCount").textContent=state.chats.length;
  renderModels();renderModelSelect();renderChats();renderConfig(ci);
 }catch(e){$("#status").textContent="Serveur disponible, Ollama inaccessible";$("#status").className="error";console.error(e)}
}
function renderModels(){ $("#modelsList").innerHTML=state.models.length?state.models.map(m=>`<div class="model"><b>${esc(m.name)}</b><div class="muted">${m.size?Math.round(m.size/1024/1024/10)/100+" GB":"Taille inconnue"}</div></div>`).join(""):"<p class='muted'>Aucun modèle installé. Utilisez main.py pour en installer un.</p>"}
function renderModelSelect(){const el=$("#modelSelect");el.innerHTML=state.models.map(m=>`<option value="${esc(m.name)}">${esc(m.name)}</option>`).join("");if(!state.models.length)el.innerHTML="<option>Aucun modèle installé</option>"}
function renderChats(){const el=$("#chatSelect");el.innerHTML=state.chats.map(c=>`<option value="${c.id}">${esc(c.summary||c.topic||("Conversation #"+c.id))}</option>`).join("");if(!state.chats.length)el.innerHTML="<option value=''>Aucune conversation</option>";if(state.current){el.value=state.current.id}}
function renderConfig(c){$("#configInfo").innerHTML=`Modèle configuré : <b>${esc(c.model||"Aucun")}</b><br>Ollama : <b>${esc(c.ollama_url||"—")}</b><br>Langue : <b>${esc(c.language||"français")}</b>`}
function renderMessages(chat){const box=$("#messages");if(!chat||!chat.messages?.length){box.innerHTML="<p class='muted'>Commencez une conversation.</p>";return}box.innerHTML=chat.messages.map(m=>`<div class="msg ${m.role==="user"?"user":"assistant"}"><div class="role">${m.role==="user"?"Vous":"IA"}</div>${esc(m.content)}</div>`).join("");box.scrollTop=box.scrollHeight}
async function refreshChats(){const d=await api("/api/chats");state.chats=d.chats||[];renderChats();if(!state.current&&state.chats.length)state.current=state.chats[0];if(state.current){const d=await api("/api/chats/"+state.current.id);state.current=d.chat;$("#chatSelect").value=state.current.id;renderMessages(state.current)}}
$("#newChat").onclick=async()=>{try{const d=await api("/api/chats/new",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});state.current=d.chat;await refresh();show("chat");renderMessages(state.current)}catch(e){alert(e.message)}}
$("#chatSelect").onchange=async e=>{if(!e.target.value)return;try{const d=await api("/api/chats/"+e.target.value);state.current=d.chat;renderMessages(state.current)}catch(x){alert(x.message)}}
$("#chatForm").onsubmit=async e=>{e.preventDefault();const text=$("#message").value.trim();if(!text||!state.current)return;if(!$("#modelSelect").value||$("#modelSelect").value==="Aucun modèle installé"){alert("Installez d'abord un modèle via main.py.");return}$("#send").disabled=true;$("#message").value="";try{const d=await api("/api/chat",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({chat_id:state.current.id,model:$("#modelSelect").value,message:text})});state.current=d.chat;renderMessages(state.current);refreshChats()}catch(x){alert(x.message)}finally{$("#send").disabled=false}}
document.querySelectorAll(".nav").forEach(b=>b.onclick=()=>show(b.dataset.page));
refresh().then(refreshChats).catch(console.error);
