(()=>{var x="opendiscovery.sdk",g=1;var lt=`
:root {
  /* Quiet at rest like the app's own thumbs; hover gives a clear grab target. */
  --oc-scrollbar-thumb: color-mix(in srgb, var(--oc-muted, currentColor) 18%, transparent);
  --oc-scrollbar-thumb-hover: color-mix(in srgb, var(--oc-muted, currentColor) 36%, transparent);
  scrollbar-gutter: stable;
}
* {
  scrollbar-width: thin;
  scrollbar-color: transparent transparent;
}
:hover, [data-oc-scrolling] {
  scrollbar-color: var(--oc-scrollbar-thumb) transparent;
}
/* Chromium's standard scrollbar properties otherwise override its pseudo-elements. */
@supports selector(::-webkit-scrollbar) {
  *, :hover, [data-oc-scrolling] { scrollbar-width: auto; scrollbar-color: auto; }
  ::-webkit-scrollbar { width: 6px; height: 6px; background: transparent; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb {
    background: transparent;
    border-radius: 999px;
    min-width: 24px;
    min-height: 24px;
  }
  :hover::-webkit-scrollbar-thumb, [data-oc-scrolling]::-webkit-scrollbar-thumb { background: var(--oc-scrollbar-thumb); }
  ::-webkit-scrollbar-thumb:hover { background: var(--oc-scrollbar-thumb-hover); }
  ::-webkit-scrollbar-corner { background: transparent; }
  ::-webkit-scrollbar-button { display: none; width: 0; height: 0; }
}
@media (forced-colors: active) {
  *, :hover, [data-oc-scrolling] { scrollbar-color: auto; }
  ::-webkit-scrollbar-thumb, ::-webkit-scrollbar-thumb:hover { background: CanvasText; }
}
`;function yo(e){let o=e.documentElement;if(o.hasAttribute("data-oc-scrollbar-activity"))return;o.setAttribute("data-oc-scrollbar-activity","");let n=new WeakMap;e.addEventListener("scroll",(s)=>{let i=s.target===e?o:s.target;if(!(i instanceof Element))return;if(!i.hasAttribute("data-oc-scrolling"))i.setAttribute("data-oc-scrolling","");let a=n.get(i);if(a!==void 0)clearTimeout(a);n.set(i,setTimeout(()=>{n.delete(i),i.removeAttribute("data-oc-scrolling")},1000))},{capture:!0,passive:!0})}var jr=`(${yo.toString()})(document);`;var pt=128,ut=65536;var Ie=128;var Le=65536;var ko=/^[a-z][a-z0-9-]{0,39}$/;var Ao=(e)=>Object(e)===e&&!Array.isArray(e),mt=(e,o)=>Object.keys(e).every((n)=>o.includes(n)),vo=(e)=>String(e)===e&&e.length>=1&&e.length<=60,Ro=(e)=>String(e)===e&&e.length>=1&&e.length<=80,wo=(e)=>{if(!Array.isArray(e)||e.length>4)return!1;let o=new Set;for(let n of e){if(!Ao(n)||!ko.test(n.id)||!vo(n.label))return!1;if(n.disabled!==void 0&&n.disabled!==!0&&n.disabled!==!1)return!1;if(o.has(n.id))return!1;if(o.add(n.id),n.kind==="button"){if(!mt(n,["kind","id","label","disabled"]))return!1;continue}if(n.kind!=="select"||!mt(n,["kind","id","label","value","options","disabled"]))return!1;if(!Ro(n.value)||!Array.isArray(n.options)||n.options.length<1||n.options.length>16)return!1;let s=new Set;for(let i of n.options){if(!Ao(i)||!mt(i,["value","label"])||!Ro(i.value)||!vo(i.label)||s.has(i.value))return!1;s.add(i.value)}if(!s.has(n.value))return!1}return!0};var Me=20000000,Ne=256;var ft=(e)=>("bytes"in e)?e.bytes.byteLength:e.content.length,Uo=(e,o)=>{if(e.path!==o.path||e.readOnly!==o.readOnly)return!1;if(e.encoding==="text"||o.encoding==="text")return e.encoding==="text"&&o.encoding==="text"&&e.content===o.content;if(e.bytes.byteLength!==o.bytes.byteLength)return!1;for(let n=0;n<e.bytes.byteLength;n+=1)if(e.bytes[n]!==o.bytes[n])return!1;return!0};var Co=/^[A-Za-z0-9_-]{1,80}$/;var Io=["left","right","top","bottom"];var Lo=(e,o=0,n={remaining:16000})=>{if(--n.remaining<0||o>=32)return!1;if(e===null)return!0;let s=Array.isArray(e)?e:Object(e)===e?Object.values(e):[];for(let i of s)if(!Lo(i,o+1,n))return!1;return!0},Et=(e)=>{if(e===null||e===!0||e===!1)return!0;if(Array.isArray(e))return Object.keys(e).every((o)=>/^(0|[1-9]\d*)$/.test(o)&&Number(o)<e.length)&&e.every(Et);if(Object(e)===e){let o=Object.getPrototypeOf(e);return(o===null||o===Object.prototype)&&Object.values(e).every(Et)}return String(e)===e||Number.isFinite(e)},_t=(e)=>{try{if(String(e.id)!==e.id||!Co.test(e.id)||!Number.isFinite(e.anchor.x)||Math.abs(e.anchor.x)>1e5||!Number.isFinite(e.anchor.y)||Math.abs(e.anchor.y)>1e5||!Number.isFinite(e.anchor.width)||!Number.isFinite(e.anchor.height)||e.anchor.width<=0||e.anchor.height<=0||e.anchor.width>1e5||e.anchor.height>1e5||!Number.isInteger(e.width)||e.width<160||e.width>640||!Number.isInteger(e.height)||e.height<48||e.height>480||e.side!==void 0&&!Io.includes(e.side)||e.focus!==void 0&&e.focus!==!0&&e.focus!==!1||!Lo(e.data)||!Et(e.data))return!1;return JSON.stringify(e.data).length<=16000}catch{return!1}};var No=["file","directory","other","missing"],Tt=(e)=>Boolean(e&&"sessionId"in e),ht=(e)=>Boolean(e&&"sent"in e&&!("sessionId"in e));var Po=/^[0-9a-f]{7,64}$/i,xt=(e)=>Po.test(e),Pe=500,Ge=32000,Go=16000,Do=128,$o=200,Ho=2000,Xo=16000,Fo=80,Vo=200,Bo=16000;var jo=2000;var gt=20000,De=1024,$e=2000000;var He=64000,Xe=8000,bt=4000;var Ot=960000;var zo=999,Ko=1e4,be=500,Wo=["HOST_UNAVAILABLE","HOST_TIMEOUT","HOST_REJECTED","DISCONNECTED","DISABLED","BAD_PATH","NO_INTEGRATION","NO_SERVICE","SERVICE_FAILED","REQUEST_FAILED","RESPONSE_TOO_LARGE","NO_SESSION","SESSION_BUSY","NOT_GRANTED","NO_DIRECTORY","NOT_FOUND","FILE_TOO_LARGE","DENIED","NO_MODEL","MODEL_FAILED","UNSUPPORTED"],Yo=["stopped","starting","ready","failed"],Kr=new Set(Wo),Jo=(e)=>Kr.has(e),Qo=(e)=>e&&Jo(e)?e:"HOST_REJECTED",me=(e)=>{if(e===void 0)return!1;if(e===null||e===!0||e===!1)return!0;if(String(e)===e)return!0;if(Number(e)===e)return Number.isFinite(e);if(Array.isArray(e))return e.every(me);if(Object(e)===e)return Object.values(e).every(me);return!1},Zo=(e)=>me(e)&&JSON.stringify(e).length<=Bo,Mo=(e)=>e?.trim().slice(0,Vo)??"",fe=(e)=>{let o=e.id.trim().slice(0,Do),n=e.title.trim().slice(0,$o),s=e.url.trim().slice(0,Ho),i=e.text?.trim().slice(0,Xo),a=e.author?.trim().slice(0,Fo),d=e.kind==="pull"?"pull":"issue",_={providerId:e.providerId.trim(),id:o,title:n||o,url:s,kind:d};if(i)_.text=i;if(a)_.author=a;if(d==="pull"){let E=Mo(e.branches?.head),T=Mo(e.branches?.base);if(E&&T)_.branches={head:E,base:T}}if(Zo(e.data))_.data=e.data;return _},yt=(e)=>{let o=fe(e);if(e.projectId)o.projectId=e.projectId;if(e.navigation)o.navigation=e.navigation;if(e.worktree)o.worktree=e.worktree;return o},At=(e)=>{let o={text:e.text.trim().slice(0,Go)};if(e.send)o.send=!0;return o},vt=(e)=>{if(e===null||!Number.isFinite(e))return null;return Math.min(zo,Math.max(0,Math.round(e)))},Rt=(e)=>{if(!Number.isFinite(e))return 0;return Math.min(Ko,Math.max(0,Math.ceil(e)))};var Ee=(e)=>e.length>0&&e.length<=De&&!e.includes("\x00")&&!e.includes("\\");var Fe=(e)=>{if(!e.startsWith("/")||e.includes("\x00")||e.includes("\\")||e.includes("://"))return!1;if(e.length>jo)return!1;return!e.split("/").some((n)=>n==="."||n==="..")},Wr=new Set(Yo),kt=(e)=>Boolean(e&&"status"in e&&Wr.has(String(e.status))&&!("body"in e)),Ve=(e)=>Boolean(e&&"status"in e&&"body"in e&&Number.isInteger(e.status)),wt=(e)=>Boolean(e&&"content"in e&&String(e.content)===e.content),Ut=(e)=>Boolean(e&&"written"in e&&e.written===!0),Ct=(e)=>Boolean(e&&"entries"in e&&Array.isArray(e.entries)),Yr=new Set(No),It=(e)=>Boolean(e&&"kind"in e&&"size"in e&&Yr.has(String(e.kind))&&Number.isFinite(e.size)),Lt=(e)=>Boolean(e&&"text"in e&&String(e.text)===e.text&&!("status"in e)),Jr=new Set(["workspace","shells","ready","directory","session","connection","settings","session-lifecycle","item","resolve","action","status-control-event","popover-closed","file-open","file-snapshot","file-saved","generate-late"]),Qr=(e)=>Object(e)===e?e:null,St=(e)=>String(e)===e&&e.length>0,Zr=(e)=>{if(!St(e.id))return null;if(e.ok===!0){let o={channel:x,v:g,type:"result",id:e.id,ok:!0};if(Object(e.payload)===e.payload)o.payload=e.payload;return o}if(e.ok===!1&&St(e.error))return{channel:x,v:g,type:"result",id:e.id,ok:!1,error:e.error,code:Qo(St(e.code)?e.code:void 0)};return null},Mt=(e)=>{let o=Qr(e);if(!o||o.channel!==x||o.v!==g)return null;if(o.type==="result")return Zr(o);if(!Jr.has(String(o.type))||Object(o.payload)!==o.payload)return null;return o};var qo=(e)=>("key"in e)&&("metaKey"in e)&&("ctrlKey"in e),qr=(e)=>(e.metaKey||e.ctrlKey)&&!e.altKey&&!e.shiftKey&&e.key.toLowerCase()==="s";class m extends Error{code;constructor(e,o){super(o);this.name="HostRequestError",this.code=e}}var er=()=>Promise.reject(new m("BAD_PATH",'Request path must start with "/" and stay on the declared origin.')),Be=()=>Promise.reject(new m("BAD_PATH",`File path must be 1 to ${De} characters without NUL or backslash.`)),je=(e)=>{if(e===void 0)return;if(Object(e)!==e||Array.isArray(e)||e.scope!==void 0&&e.scope!=="instance"&&e.scope!=="device")throw new m("HOST_REJECTED",'Storage scope must be "instance" or "device".');return e.scope==="device"?"device":void 0},S=(e)=>(e.value+=1,`oc-${e.value}`),Nt=(e={})=>{let o=e.target??("window"in globalThis?window:null);if(!o)throw new m("HOST_UNAVAILABLE","No window. connectHost runs in a browser frame.");let n=e.acceptSource??((t)=>t===o.parent),s=e.requestTimeoutMs??gt,i=new Set,a=new Set,d=new Set,_=new Set,E=new Set,T=new Set,A=new Set,w=new Set,b=new Set,h=new Set,X=[],D=null,Q=null,Z=new Set,de=new Set,re=null,ne=null,ke=!1,U=new Map,L=new Map,M=new Map,H=!1,f={value:0},p=null,Y=null,le=!1,ge=!1,uo=null,mo=(t)=>{if(!t)return null;return{sessionId:t.id,phase:t.busy?"started":"completed"}},K=(t)=>{o.parent.postMessage(t,"*")},fo=()=>{if(H||o.parent===o||h.size===0||p?.features?.lateGenerateResults!==!0)return;K({channel:x,v:g,type:"generate-late-listen"})},C=(t,r)=>{for(let l of t)try{l(r)}catch(u){console.error(u)}},Eo=(t)=>{if(!(t instanceof MessageEvent))return;if(!n(t.source))return;let r=Mt(t.data);if(!r)return;if(r.type==="workspace"){let u=L.get(r.payload.subscriptionId);if(u)C([u],r.payload.snapshot);return}if(r.type==="shells"){let u=M.get(r.payload.subscriptionId);if(u)C([u],r.payload.snapshot);return}if(r.type==="ready"){if(p=r.payload,Y=mo(r.payload.session),C(i,r.payload),C(a,r.payload.directory),C(d,r.payload.session),Y)C(_,Y);C(E,r.payload.connection),C(T,r.payload.settings),C(A,r.payload.item),fo();return}if(r.type==="generate-late"){if(h.size===0)X.push(r.payload);else C(h,r.payload);return}if(r.type==="directory"){if(p)p={...p,directory:r.payload.directory};C(a,r.payload.directory);return}if(r.type==="session"){if(p)p={...p,session:r.payload.session};if(!r.payload.session)Y=null;else if(Y?.sessionId!==r.payload.session.id)Y=mo(r.payload.session);C(d,r.payload.session);return}if(r.type==="session-lifecycle"){Y=r.payload,C(_,r.payload);return}if(r.type==="connection"){if(p)p={...p,connection:r.payload.connection};C(E,r.payload.connection);return}if(r.type==="settings"){if(p)p={...p,settings:r.payload.settings};C(T,r.payload.settings);return}if(r.type==="item"){if(p)p={...p,item:r.payload.item};C(A,r.payload.item);return}if(r.type==="status-control-event"){C(w,r.payload);return}if(r.type==="popover-closed"){C(b,r.payload);return}if(r.type==="action"){let u=(O)=>{if(!H)K({channel:x,v:g,type:"action-result",id:r.id,payload:O})},y=Q;if(!y){u({ok:!1,error:"This extension does not handle background actions."});return}Promise.resolve().then(()=>y(r.payload)).then(()=>u({ok:!0}),(O)=>{let G=(O instanceof Error?O.message:String(O)).trim();u({ok:!1,error:(G||"Action failed.").slice(0,be)})});return}if(r.type==="file-open"){let u=r.payload;if(ne&&Uo(ne,u))return;ne=u,C(Z,r.payload);return}if(r.type==="file-saved"){C(de,r.payload.version);return}if(r.type==="file-snapshot"){let u=(G)=>{if(!H)K({channel:x,v:g,type:"file-snapshot-result",id:r.id,payload:G})},y=(G)=>u({error:(G.trim()||"Could not read the edited file.").slice(0,be)}),O=re;if(!O){y("This extension does not edit files.");return}Promise.resolve().then(()=>O(r.payload.purpose)).then((G)=>{if(ft(G)>Me){y(`The file is over ${Me} ${"bytes"in G?"bytes":"characters"}.`);return}if(G.version.length>Ne){y(`The snapshot version is over ${Ne} characters.`);return}u({snapshot:"bytes"in G?{bytes:G.bytes,version:G.version}:{content:G.content,version:G.version}})},(G)=>y(G instanceof Error?G.message:String(G)));return}if(r.type==="resolve"){let u=(O)=>{K({channel:x,v:g,type:"resolve-result",id:r.id,payload:O})},y=D;if(!y){u({error:"This extension does not resolve commands."});return}Promise.resolve().then(()=>y(r.payload)).then((O)=>u({item:O?fe(O):null}),(O)=>{let G=(O instanceof Error?O.message:String(O)).trim();u({error:(G||"Command failed.").slice(0,be)})});return}let l=U.get(r.id);if(!l)return;if(clearTimeout(l.timer),U.delete(r.id),r.ok){l.resolve(r.payload);return}l.reject(new m(r.code,r.error))};o.addEventListener("message",Eo),K({channel:x,v:g,type:"hello"});let F=(t,r=s)=>{if(H||o.parent===o)return Promise.reject(new m("HOST_UNAVAILABLE","No host frame. This page is not in an iframe."));return new Promise((l,u)=>{let y=setTimeout(()=>{U.delete(t.id),u(new m("HOST_TIMEOUT","Host did not answer in time."))},r);U.set(t.id,{resolve:l,reject:u,timer:y}),K(t)})},N=(t)=>F(t).then(()=>{return}),P={channel:x,v:g},at=(t)=>{if(!H&&o.parent!==o)K(t)},_o=()=>at({...P,type:"file-save"}),So=(t)=>{if(!qo(t)||!qr(t))return;t.preventDefault(),_o()},To=(t)=>{if(!qo(t)||t.key!=="Escape"||p?.surface!=="popover"||!p.popover)return;t.preventDefault(),bo(p.popover.id,"escape").catch(()=>{return})},we=()=>{let t=p?.surface==="popover"?p.popover:void 0;if(!t)return;let r=le||ge;if(uo===r)return;uo=r,Oo(t.id,r).catch(()=>{return})},Ue=()=>{if(p?.surface!=="popover"||le)return;le=!0,we()},ho=(t)=>{if(p?.surface!=="popover"||t.relatedTarget!==null||!le)return;le=!1,we()},xo=()=>{if(p?.surface!=="popover"||ge)return;ge=!0,we()},go=()=>{if(p?.surface!=="popover"||!ge)return;ge=!1,we()},J=(t,r=1024)=>{if(!t.trim()||t.length>r)throw new m("HOST_REJECTED",`Identity must contain 1 to ${r} characters.`)},ct=async(t)=>{if(t.kind!=="projects")J(t.projectId);let r=await F({...P,type:"workspace-read",id:S(f),payload:t});if(!r||!("kind"in r)||!("state"in r)||r.kind!==t.kind)throw new m("HOST_REJECTED","Host did not return workspace data.");return r},dt=async(t,r)=>{if(t.kind!=="projects")J(t.projectId);let l=S(f);L.set(l,r);try{await N({...P,type:"workspace-subscribe",id:S(f),payload:{subscriptionId:l,query:t}})}catch(u){if(L.delete(l),!H)K({...P,type:"workspace-unsubscribe",id:S(f),payload:{subscriptionId:l}});throw u}return()=>{if(!L.delete(l)||H)return;K({...P,type:"workspace-unsubscribe",id:S(f),payload:{subscriptionId:l}})}},Br=async(t,r)=>{if(t.kind==="session")J(t.sessionId);if(t.kind==="project")J(t.projectId);let l=S(f);M.set(l,r);try{await N({...P,type:"shells-subscribe",id:S(f),payload:{subscriptionId:l,scope:t}})}catch(u){if(M.delete(l),!H)K({...P,type:"shells-unsubscribe",id:S(f),payload:{subscriptionId:l}});throw u}return()=>{if(!M.delete(l)||H)return;K({...P,type:"shells-unsubscribe",id:S(f),payload:{subscriptionId:l}})}},Ce=async(t)=>{if("key"in t&&(t.key.length===0||t.key.length>pt))throw new m("HOST_REJECTED","Storage key must contain 1 to 128 characters.");if(t.op==="set"&&!me(t.value))throw new m("HOST_REJECTED","Storage values must be JSON.");if(t.op==="set"&&new TextEncoder().encode(JSON.stringify(t.value)).length>ut)throw new m("HOST_REJECTED","Storage value exceeds 64 KiB.");if(t.scope==="device"&&p?.features?.deviceStorage!==!0)throw new m("UNSUPPORTED","This host does not support device storage.");let r=await F({...P,type:"storage",id:S(f),payload:t});if(!r||!("storage"in r)||r.op!==t.op)throw new m("HOST_REJECTED","Host did not return storage data.");return r},bo=(t,r)=>p?.features?.popovers!==!0&&!(p?.surface==="popover"&&p.popover?.id===t)?Promise.reject(new m("UNSUPPORTED","This host does not support popovers.")):N({...P,type:"popover-close",id:S(f),payload:r?{id:t,reason:r}:{id:t}}),Oo=(t,r)=>p?.features?.popovers!==!0&&!(p?.surface==="popover"&&p.popover?.id===t)?Promise.reject(new m("UNSUPPORTED","This host does not support popovers.")):N({...P,type:"popover-anchor",id:S(f),payload:{id:t,active:r}});return o.addEventListener("keydown",To,!0),o.addEventListener("pointerover",Ue),o.addEventListener("pointermove",Ue),o.addEventListener("pointerout",ho),o.addEventListener("focus",xo),o.addEventListener("blur",go),{onAction:(t)=>(Q=t,()=>{if(Q===t)Q=null}),listProjects:async()=>{let t=await ct({kind:"projects"});if(t.kind!=="projects")throw new m("HOST_REJECTED","Expected projects.");return t},listWorktrees:async(t)=>{let r=await ct({kind:"worktrees",projectId:t});if(r.kind!=="worktrees")throw new m("HOST_REJECTED","Expected worktrees.");return r},listSessions:async(t)=>{let r=await ct({kind:"sessions",projectId:t});if(r.kind!=="sessions")throw new m("HOST_REJECTED","Expected sessions.");return r},onProjects:(t)=>dt({kind:"projects"},(r)=>{if(r.kind==="projects")t(r)}),onWorktrees:(t,r)=>dt({kind:"worktrees",projectId:t},(l)=>{if(l.kind==="worktrees")r(l)}),onSessions:(t,r)=>dt({kind:"sessions",projectId:t},(l)=>{if(l.kind==="sessions")r(l)}),onRunningShells:(t,r)=>Br(t,r),readShellOutput:async(t,r)=>{J(t,Ie);let l=r?.cursor;if(l!==void 0&&(!Number.isInteger(l)||l<0))throw new m("HOST_REJECTED","Shell output cursor must be a non-negative integer.");let u=r?.tailBytes;if(u!==void 0&&(!Number.isInteger(u)||u<1||u>Le))throw new m("HOST_REJECTED",`Shell output tailBytes must be an integer between 1 and ${Le}.`);let O=await F({...P,type:"shell-output",id:S(f),payload:{shellId:t,cursor:l,tailBytes:u}});if(!O||typeof O.output!=="string"||!Number.isFinite(O.cursor))throw new m("HOST_REJECTED","Host did not return shell output.");return O},stopShell:async(t)=>{if(J(t,Ie),(await F({...P,type:"shell-stop",id:S(f),payload:{shellId:t}}))?.stopped!==!0)throw new m("HOST_REJECTED","Host did not stop the shell.");return{stopped:!0}},openSession:async(t)=>{J(t),await N({...P,type:"open-session",id:S(f),payload:{sessionId:t}})},storage:{get:async(t,r)=>{let l=je(r),u={op:"get",key:t};if(l)u.scope=l;let y=await Ce(u);return y.op==="get"&&y.found?y.value:void 0},set:async(t,r,l)=>{let u=je(l),y={op:"set",key:t,value:r};if(u)y.scope=u;await Ce(y)},delete:async(t,r)=>{let l=je(r),u={op:"delete",key:t};if(l)u.scope=l;await Ce(u)},keys:async(t)=>{let r=je(t),l={op:"keys"};if(r)l.scope=r;let u=await Ce(l);if(u.op!=="keys")throw new m("HOST_REJECTED","Expected storage keys.");return u.keys}},onReady:(t)=>{if(i.add(t),p)t(p);return()=>{i.delete(t)}},onDirectory:(t)=>{if(a.add(t),p)t(p.directory);return()=>{a.delete(t)}},onSession:(t)=>{if(d.add(t),p)t(p.session);return()=>{d.delete(t)}},onSessionLifecycle:(t)=>{if(_.add(t),Y)t(Y);return()=>{_.delete(t)}},onConnection:(t)=>{if(E.add(t),p)t(p.connection);return()=>{E.delete(t)}},onSettings:(t)=>{if(T.add(t),p)t(p.settings);return()=>{T.delete(t)}},onItem:(t)=>{if(A.add(t),p)t(p.item);return()=>{A.delete(t)}},onStatusControl:(t)=>(w.add(t),()=>{w.delete(t)}),onPopoverClosed:(t)=>(b.add(t),()=>{b.delete(t)}),setStatusControls:(t)=>{if(p?.features?.statusControls!==!0)return Promise.reject(new m("UNSUPPORTED","This host does not support status controls."));if(!wo(t))return Promise.reject(new m("HOST_REJECTED","Status controls must have unique bounded ids and valid selected options."));return N({...P,type:"status-controls",id:S(f),payload:{controls:t}})},openPopover:(t)=>{if(p?.features?.popovers!==!0)return Promise.reject(new m("UNSUPPORTED","This host does not support popovers."));if(!_t(t))return Promise.reject(new m("HOST_REJECTED","Popover requests need bounded geometry and JSON data."));return N({...P,type:"popover-open",id:S(f),payload:t})},closePopover:bo,setPopoverAnchorActive:Oo,onResolve:(t)=>(D=t,()=>{if(D===t)D=null}),toast:(t)=>{let r=t.message.trim();if(!r||r.length>Pe)return Promise.reject(new m("HOST_REJECTED",`Toast message must contain 1 to ${Pe} characters.`));if(t.copy&&t.copy!==!0&&(!t.copy.text.length||t.copy.text.length>Ge))return Promise.reject(new m("HOST_REJECTED",`Toast copy text must contain 1 to ${Ge} characters.`));return N({channel:x,v:g,type:"toast",id:S(f),payload:{...t,message:r}})},openUrl:(t)=>N({channel:x,v:g,type:"open-url",id:S(f),payload:{url:t}}),openCommit:(t)=>xt(t)?N({channel:x,v:g,type:"open-commit",id:S(f),payload:{sha:t}}):Promise.reject(new m("HOST_REJECTED","Commit id must be 7 to 64 hex characters.")),openSurface:(t)=>N({channel:x,v:g,type:"open-surface",id:S(f),payload:{surfaceId:t}}),writeClipboard:(t)=>N({channel:x,v:g,type:"clipboard-write",id:S(f),payload:{text:t}}),compose:(t)=>N({channel:x,v:g,type:"compose",id:S(f),payload:t}),attach:(t)=>N({channel:x,v:g,type:"attach",id:S(f),payload:fe(t)}),startSession:async(t)=>{if(t.projectId!==void 0)J(t.projectId);let r=t.worktree;if(r&&r!==!0)if(r.kind==="existing")J(r.directory);else{if(r.name!==void 0)J(r.name,200);if(r.baseBranch!==void 0)J(r.baseBranch,200)}let l=await F({channel:x,v:g,type:"start-session",id:S(f),payload:yt(t)},e.requestTimeoutMs??180000);if(!Tt(l))throw new m("HOST_REJECTED","Host did not return a session.");return l},prompt:(t)=>F({channel:x,v:g,type:"prompt",id:S(f),payload:At(t)}).then((r)=>{if(!ht(r))throw new m("HOST_REJECTED","Host did not return a prompt result.");return r}),sessionLink:(t)=>N({channel:x,v:g,type:"session-link",id:S(f),payload:fe(t)}),close:()=>N({channel:x,v:g,type:"close",id:S(f)}),oauthStart:()=>N({channel:x,v:g,type:"oauth-start",id:S(f)}),oauthDisconnect:()=>N({channel:x,v:g,type:"oauth-disconnect",id:S(f)}),request:(t)=>(Fe(t.path)?F({channel:x,v:g,type:"request",id:S(f),payload:t}):er()).then((r)=>{if(!Ve(r))throw new m("HOST_REJECTED","Host request result was empty.");return r}),serviceRequest:(t)=>(Fe(t.path)?F({channel:x,v:g,type:"service-request",id:S(f),payload:t}):er()).then((r)=>{if(!Ve(r))throw new m("HOST_REJECTED","Host service request result was empty.");return r}),serviceStatus:()=>F({channel:x,v:g,type:"service-status",id:S(f)}).then((t)=>{if(!kt(t))throw new m("HOST_REJECTED","Host did not return service status.");return t}),readFile:(t)=>(Ee(t)?F({channel:x,v:g,type:"file-read",id:S(f),payload:{path:t}}):Be()).then((r)=>{if(!wt(r))throw new m("HOST_REJECTED","Host did not return file content.");return r}),writeFile:(t,r)=>{if(!Ee(t))return Be();if(r.length>$e)return Promise.reject(new m("FILE_TOO_LARGE",`Content is over ${$e} characters.`));return F({channel:x,v:g,type:"file-write",id:S(f),payload:{path:t,content:r}}).then((l)=>{if(!Ut(l))throw new m("HOST_REJECTED","Host did not confirm the write.");return l})},listDir:(t)=>(Ee(t)?F({channel:x,v:g,type:"file-list",id:S(f),payload:{path:t}}):Be()).then((r)=>{if(!Ct(r))throw new m("HOST_REJECTED","Host did not return directory entries.");return r}),stat:(t)=>(Ee(t)?F({channel:x,v:g,type:"file-stat",id:S(f),payload:{path:t}}):Be()).then((r)=>{if(!It(r))throw new m("HOST_REJECTED","Host did not return file status.");return r}),generate:(t)=>{let r=t.prompt.trim(),l=t.system?.trim();if(r.length===0||r.length>He)return Promise.reject(new m("HOST_REJECTED",`Prompt must be 1 to ${He} characters.`));if(l!==void 0&&(l.length===0||l.length>Xe))return Promise.reject(new m("HOST_REJECTED",`System prompt must be 1 to ${Xe} characters.`));let u=t.maxOutputTokens===void 0?void 0:Math.min(bt,Math.max(1,Math.floor(t.maxOutputTokens)));if(u!==void 0&&!Number.isFinite(u))return Promise.reject(new m("HOST_REJECTED","maxOutputTokens must be a number."));let y={prompt:r};if(l!==void 0)y.system=l;if(u!==void 0)y.maxOutputTokens=u;return F({channel:x,v:g,type:"generate",id:S(f),payload:y},e.requestTimeoutMs??Ot).then((O)=>{if(!Lt(O))throw new m("HOST_REJECTED","Host did not return generated text.");return O})},onLateGenerateResult:(t)=>{h.add(t);for(let r of X.splice(0))C([t],r);return fo(),()=>{h.delete(t)}},setBadge:(t)=>N({channel:x,v:g,type:"badge",id:S(f),payload:{count:vt(t)}}),setHeight:(t)=>N({channel:x,v:g,type:"resize",id:S(f),payload:{height:Rt(t)}}),onFileOpen:(t)=>{if(Z.add(t),!ke)ke=!0,o.addEventListener("keydown",So,!0);if(ne)t(ne);return()=>{Z.delete(t)}},onFileSnapshot:(t)=>(re=t,()=>{if(re===t)re=null}),onFileSaved:(t)=>(de.add(t),()=>{de.delete(t)}),reportFileChange:(t)=>at({...P,type:"file-change",payload:{dirty:t.dirty,edited:t.edited}}),requestFileSave:_o,reportFileUnsupported:()=>at({...P,type:"file-unsupported"}),dispose:()=>{for(let t of L.keys())K({...P,type:"workspace-unsubscribe",id:S(f),payload:{subscriptionId:t}});L.clear();for(let t of M.keys())K({...P,type:"shells-unsubscribe",id:S(f),payload:{subscriptionId:t}});if(M.clear(),H=!0,D=null,Q=null,re=null,Z.clear(),de.clear(),ke)o.removeEventListener("keydown",So,!0);o.removeEventListener("message",Eo),o.removeEventListener("keydown",To,!0),o.removeEventListener("pointerover",Ue),o.removeEventListener("pointermove",Ue),o.removeEventListener("pointerout",ho),o.removeEventListener("focus",xo),o.removeEventListener("blur",go);for(let t of U.values())clearTimeout(t.timer),t.reject(new m("HOST_UNAVAILABLE","Host client was disposed."));U.clear(),i.clear(),a.clear(),d.clear(),_.clear(),E.clear(),T.clear(),A.clear(),w.clear(),b.clear(),h.clear(),X.length=0}}};var tr=["browser.open","browser.snapshot","browser.click","browser.type","browser.select","browser.scroll","browser.back","browser.forward","browser.inspect","browser.capture","browser.resize","browser.close"];var _s=new Set(tr);var or=["none","agent","user"];var Ts=new Set(or);var en=[["--oc-bg","background"],["--oc-elevated","elevated"],["--oc-fg","foreground"],["--oc-muted","muted"],["--oc-subtle","subtle"],["--oc-border","border"],["--oc-hover","hover"],["--oc-selection","selection"],["--oc-focus","focus"],["--oc-primary","primary"],["--oc-muted-surface","mutedSurface"],["--oc-elevated-fg","elevatedForeground"],["--oc-active","active"],["--oc-selection-fg","selectionForeground"],["--oc-primary-fg","primaryForeground"],["--oc-primary-text","primaryText"],["--oc-success-text","successText"],["--oc-warning-text","warningText"],["--oc-error-text","errorText"],["--oc-info-text","infoText"],["--oc-success","success"],["--oc-warning","warning"],["--oc-error","error"],["--oc-info","info"],["--oc-font","font"],["--oc-mono","mono"],["--oc-radius","radius"],["--surface-background","background"],["--surface-elevated","elevated"],["--surface-foreground","foreground"],["--surface-muted-foreground","muted"],["--surface-subtle","subtle"],["--interactive-border","border"],["--interactive-hover","hover"],["--interactive-selection","selection"],["--interactive-focus-ring","focus"],["--primary","primary"],["--surface-muted","mutedSurface"],["--surface-elevated-foreground","elevatedForeground"],["--interactive-active","active"],["--interactive-selection-foreground","selectionForeground"],["--primary-foreground","primaryForeground"],["--primary-text","primaryText"],["--success-text","successText"],["--warning-text","warningText"],["--error-text","errorText"],["--info-text","infoText"],["--status-success","success"],["--status-warning","warning"],["--status-error","error"],["--status-info","info"],["--font-sans","font"],["--font-mono","mono"],["--radius","radius"]],tn=[["--oc-syntax-keyword","--syntax-keyword","syntaxKeyword"],["--oc-syntax-string","--syntax-string","syntaxString"],["--oc-syntax-number","--syntax-number","syntaxNumber"],["--oc-syntax-function","--syntax-function","syntaxFunction"],["--oc-syntax-type","--syntax-type","syntaxType"],["--oc-syntax-comment","--syntax-comment","syntaxComment"],["--oc-syntax-variable","--syntax-variable","syntaxVariable"],["--oc-syntax-operator","--syntax-operator","syntaxOperator"]],rr=(e,o)=>{o.style.colorScheme=e.mode;for(let[n,s]of en)o.style.setProperty(n,e.tokens[s]);for(let[n,s,i]of tn){let a=e.tokens[i]??"";o.style.setProperty(n,a),o.style.setProperty(s,a)}o.style.setProperty("font-family",e.tokens.font),o.style.setProperty("font-size","0.875rem"),o.style.setProperty("line-height","1.45"),o.style.setProperty("color",e.tokens.foreground)},Pt=(e,o)=>{if(rr(e.theme,o),o.dataset)o.dataset.ocSurface=e.surface,o.dataset.ocTheme=e.theme.mode};var on={"surface-background":"bg","surface-elevated":"elevated","surface-elevated-foreground":"elevated-fg","surface-foreground":"fg","surface-muted-foreground":"muted","surface-muted":"muted-surface","surface-subtle":"subtle","interactive-border":"border","interactive-hover":"hover","interactive-active":"active","interactive-selection":"selection","interactive-selection-foreground":"selection-fg","interactive-focus-ring":"focus",primary:"primary","primary-foreground":"primary-fg","primary-text":"primary-text","success-text":"success-text","warning-text":"warning-text","error-text":"error-text","info-text":"info-text","status-success":"success","status-warning":"warning","status-error":"error","status-info":"info","font-sans":"font","font-mono":"mono",radius:"radius"},R=(e,o)=>`var(--${e}, var(--oc-${on[e]}, ${o}))`,ee=R("surface-background","transparent"),Ke=R("surface-elevated","transparent"),_e=R("surface-elevated-foreground","inherit"),W=R("surface-foreground","inherit"),v=R("surface-muted-foreground","gray"),rn=R("surface-muted","transparent"),se=R("interactive-border","currentColor"),V=R("interactive-hover","transparent"),pe=R("interactive-active","transparent"),Gt=R("interactive-selection","transparent"),Dt=R("interactive-selection-foreground","inherit"),q=R("primary","currentColor"),$t=R("primary-text","inherit"),Ht=R("error-text","inherit"),nn=R("font-sans","inherit"),Xt=R("font-mono","monospace"),cr=R("radius","9px"),Ft=`calc(${cr} - 2px)`,nr=`calc(${cr} - 4px)`,I=(e,o,n="transparent")=>`color-mix(in srgb, ${e} ${o}%, ${n})`,sr=`background-image: linear-gradient(${V}, ${V});`,Vt=(e)=>`box-shadow: inset 0 0 0 1px ${e}, var(--oc-sdk-field-lift);`,Bt="border-color: var(--oc-sdk-edge); box-shadow: var(--oc-sdk-raised-lift);",ir="box-shadow: var(--oc-sdk-lit);",ar=`inset 0 1px 0 0 ${I(W,1.5)}, 0 1px 1px 0 rgb(0 0 0 / 0.28), 0 2px 3px -2px rgb(0 0 0 / 0.2)`,sn=`
:root {
  --oc-sdk-edge: ${I(W,10)};
  --oc-sdk-field-bg: ${Ke};
  --oc-sdk-raised-bg: ${ee};
  --oc-sdk-field-lift: inset 0 1px 2px 0 rgb(0 0 0 / 0.04);
  --oc-sdk-raised-lift: 0 1px 2px 0 rgb(0 0 0 / 0.06);
  --oc-sdk-lit: inset 0 1px 0 0 rgb(255 255 255 / 0.45), 0 1px 2px 0 rgb(0 0 0 / 0.08);
  --oc-sdk-float-edge: rgb(0 0 0 / 0.1);
  --oc-sdk-float: inset 0 1px 0 0 rgb(255 255 255 / 0.8), inset 0 0 0 1px rgb(0 0 0 / 0.04), 0 1px 2px -0.5px rgb(0 0 0 / 0.08), 0 4px 8px -2px rgb(0 0 0 / 0.08), 0 12px 20px -4px rgb(0 0 0 / 0.08);
}
:root[data-oc-theme="dark"] {
  --oc-sdk-edge: ${I(W,6)};
  --oc-sdk-field-bg: ${I(ee,50,Ke)};
  --oc-sdk-raised-bg: ${Ke};
  --oc-sdk-field-lift: ${ar};
  --oc-sdk-raised-lift: ${ar};
  --oc-sdk-lit: inset 0 1px 0 0 ${I(W,1.5)}, 0 1px 1px 0 rgb(0 0 0 / 0.28), 0 2px 3px -2px rgb(0 0 0 / 0.2);
  --oc-sdk-float-edge: rgb(0 0 0 / 0.36);
  --oc-sdk-float: inset 0 1px 0 0 rgb(255 255 255 / 0.06), inset 0 0 0 1px rgb(255 255 255 / 0.08), 0 1px 1px -0.5px rgb(0 0 0 / 0.22), 0 3px 3px -1.5px rgb(0 0 0 / 0.2), 0 6px 6px -3px rgb(0 0 0 / 0.16);
}`,ze=(e)=>{let o=R(`status-${e}`,"currentColor");return`
.oc-sdk[data-tone="${e}"], .oc-sdk [data-tone="${e}"] { --oc-sdk-tone: ${o}; --oc-sdk-tone-text: ${R(`${e}-text`,"inherit")}; }`},an=`
.oc-sdk { box-sizing: border-box; font-size: 0.875rem; line-height: 1.45; }
.oc-sdk *, .oc-sdk *::before, .oc-sdk *::after { box-sizing: border-box; }
/* :where() keeps the reset at zero specificity so every primitive class below overrides it. */
:where(.oc-sdk) :where(button, input, textarea), :where(button.oc-sdk, input.oc-sdk, textarea.oc-sdk) { font: inherit; color: inherit; margin: 0; }
:where(.oc-sdk) :where(button), :where(button.oc-sdk) { cursor: pointer; background: none; border: 0; padding: 0; }
.oc-sdk button:disabled, button.oc-sdk:disabled, .oc-sdk[aria-disabled="true"], .oc-sdk [aria-disabled="true"] { opacity: .5; pointer-events: none; }

.oc-sdk-btn { display: inline-flex; align-items: center; justify-content: center; gap: 8px; height: 32px; padding: 0 12px; border: 1px solid transparent; font-size: 0.875rem; font-weight: 500; line-height: 1; white-space: nowrap; }
.oc-sdk-btn[data-size="sm"] { gap: 6px; height: 28px; padding: 0 10px; font-size: 0.8125rem; }
.oc-sdk-btn[data-size="xs"] { gap: 4px; height: 24px; padding: 0 8px; font-size: 0.75rem; }
.oc-sdk-btn[data-loading="true"] { opacity: .5; pointer-events: none; }
.oc-sdk-btn > .oc-sdk-spinner-ring { width: 14px; height: 14px; }

.oc-sdk-field { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.oc-sdk-field-label { font-size: 0.8125rem; font-weight: 500; }
.oc-sdk-field-note { font-size: 0.75rem; }
.oc-sdk-input { display: block; width: 100%; min-width: 0; height: 32px; padding: 0 10px; border: 0; font-size: 0.875rem; line-height: 1.45; appearance: none; }
textarea.oc-sdk-input { height: auto; padding: 8px 10px; resize: vertical; }

.oc-sdk-search { position: relative; min-width: 0; }
.oc-sdk-search .oc-sdk-input { padding-left: 34px; padding-right: 34px; }
.oc-sdk-search-icon { position: absolute; left: 11px; top: 50%; transform: translateY(-50%); pointer-events: none; }
.oc-sdk-search-clear { position: absolute; right: 6px; top: 50%; transform: translateY(-50%); display: none; align-items: center; justify-content: center; width: 24px; height: 24px; }
.oc-sdk-search[data-active="true"] .oc-sdk-search-clear { display: inline-flex; }

.oc-sdk-select { position: relative; display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.oc-sdk-trigger { display: inline-flex; align-items: center; gap: 6px; align-self: flex-start; width: auto; max-width: 100%; min-width: 0; height: 28px; padding: 0 10px; border: 1px solid transparent; font-size: 0.8125rem; text-align: left; }
.oc-sdk-trigger-value { flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.oc-sdk-trigger-chevron { flex: 0 0 auto; }
.oc-sdk-popup { position: fixed; z-index: 50; display: flex; flex-direction: column; gap: 2px; min-width: 160px; max-width: calc(100vw - 16px); max-height: min(320px, calc(100vh - 16px)); overflow: auto; padding: 4px; border: 1px solid transparent; }
.oc-sdk-popup-search { flex: 0 0 auto; padding: 2px 2px 4px; }
.oc-sdk-popup-search .oc-sdk-input { height: 28px; font-size: 0.8125rem; }
.oc-sdk-option { display: flex; align-items: center; gap: 8px; width: 100%; padding: 6px 8px; font-size: 0.8125rem; text-align: left; }
.oc-sdk-option-label { flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.oc-sdk-option-hint { flex: 0 0 auto; font-size: 0.75rem; }
.oc-sdk-option-check { flex: 0 0 auto; display: inline-flex; width: 14px; visibility: hidden; }
.oc-sdk-option[aria-selected="true"] > .oc-sdk-option-check { visibility: visible; }
.oc-sdk-popup-empty { padding: 8px; font-size: 0.8125rem; }

.oc-sdk-check { display: inline-flex; align-items: flex-start; gap: 8px; width: 100%; text-align: left; }
.oc-sdk-check-box { flex: 0 0 auto; display: inline-flex; align-items: center; justify-content: center; width: 14px; height: 14px; margin-top: 3px; border: 1px solid transparent; }
.oc-sdk-check-box > svg { display: none; }
.oc-sdk-check[aria-checked="true"] .oc-sdk-check-box > svg { display: block; }
.oc-sdk-check-thumb { flex: 0 0 auto; position: relative; width: 36px; height: 20px; }
.oc-sdk-check-thumb::after { content: ""; position: absolute; top: 2px; left: 2px; width: 16px; height: 16px; }
.oc-sdk-check-text { display: flex; flex-direction: column; min-width: 0; }
.oc-sdk-check-label { font-size: 0.875rem; }
.oc-sdk-check-desc { font-size: 0.75rem; }

.oc-sdk-tabs { display: inline-flex; gap: 2px; padding: 2px; max-width: 100%; overflow: auto; }
.oc-sdk-tab { display: inline-flex; align-items: center; gap: 6px; height: 28px; padding: 0 10px; border: 1px solid transparent; font-size: 0.8125rem; font-weight: 500; white-space: nowrap; }
.oc-sdk-tab-count { font-size: 0.75rem; font-variant-numeric: tabular-nums; }

.oc-sdk-badge { display: inline-flex; align-items: center; padding: 1px 6px; font-size: 11px; font-weight: 500; line-height: 16px; white-space: nowrap; }

.oc-sdk-list { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.oc-sdk-row { display: flex; align-items: center; gap: 8px; width: 100%; padding: 6px 8px; text-align: left; }
.oc-sdk-row-lead { flex: 0 0 auto; width: 64px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 0.75rem; }
.oc-sdk-row-main { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; }
.oc-sdk-row-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.oc-sdk-row-sub { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 0.75rem; }
.oc-sdk-row-meta { flex: 0 0 auto; font-size: 0.75rem; font-variant-numeric: tabular-nums; }
.oc-sdk-list-empty { padding: 16px 8px; text-align: center; font-size: 0.8125rem; }

.oc-sdk-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px; padding: 40px 16px; text-align: center; }
.oc-sdk-empty-title { margin: 0; font-size: 0.8125rem; font-weight: 600; }
.oc-sdk-empty-body { margin: 0; max-width: 32rem; font-size: 0.8125rem; }
.oc-sdk-empty-action { margin-top: 12px; }

@keyframes oc-sdk-spin { to { transform: rotate(360deg); } }
.oc-sdk-spinner { display: inline-flex; align-items: center; gap: 8px; font-size: 0.8125rem; }
.oc-sdk-spinner-ring { width: 16px; height: 16px; border: 2px solid transparent; animation: oc-sdk-spin .8s linear infinite; }
.oc-sdk-spinner[data-size="sm"] .oc-sdk-spinner-ring { width: 12px; height: 12px; }

.oc-sdk-banner { display: flex; align-items: flex-start; gap: 12px; padding: 8px 12px; border: 1px solid transparent; }
.oc-sdk-banner-text { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
.oc-sdk-banner-title { font-size: 0.8125rem; font-weight: 500; }
.oc-sdk-banner-body { font-size: 0.8125rem; }
.oc-sdk-banner-action { flex: 0 0 auto; }

.oc-sdk-separator { display: flex; align-items: center; gap: 8px; width: 100%; margin: 8px 0; font-size: 0.75rem; }
.oc-sdk-separator::before, .oc-sdk-separator::after { content: ""; flex: 1 1 auto; height: 1px; }
.oc-sdk-separator[data-labeled="false"]::after { display: none; }
.oc-sdk-popup > .oc-sdk-separator { margin: 4px 0; }

.oc-sdk-progress { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.oc-sdk-progress-label { display: flex; justify-content: space-between; font-size: 0.75rem; font-variant-numeric: tabular-nums; }
.oc-sdk-progress-track { height: 6px; overflow: hidden; }
.oc-sdk-progress-fill { height: 100%; transform-origin: left; transition: transform 200ms ease-out; }

.oc-sdk-menu { position: relative; display: inline-flex; }

.oc-sdk-text { white-space: pre-wrap; overflow-wrap: anywhere; }
.oc-sdk-text img { display: block; max-width: 100%; margin: 8px 0; }
`,dr=`${sn}
.oc-sdk { color: ${W}; font-family: ${nn}; }
.oc-sdk :focus-visible, .oc-sdk:focus-visible { outline: none; }
.oc-sdk :where(button, a[href], [role="button"], [role="tab"], [role="option"]):focus-visible, button.oc-sdk:focus-visible { ${sr} }
.oc-sdk-mono { font-family: ${Xt}; }
.oc-sdk-muted { color: ${v}; }
${ze("success")}${ze("warning")}${ze("error")}${ze("info")}
.oc-sdk[data-tone="primary"], .oc-sdk [data-tone="primary"] { --oc-sdk-tone: ${q}; --oc-sdk-tone-text: ${$t}; }

.oc-sdk-btn { border-radius: ${Ft}; transition: background 150ms ease-out, color 150ms ease-out; }
.oc-sdk-btn[data-size="xs"] { border-radius: ${nr}; }
.oc-sdk-btn[data-variant="default"] { color: ${$t}; background: ${I(q,10,ee)}; border-color: ${I(q,12)}; ${ir} }
.oc-sdk-btn[data-variant="default"]:hover { background: ${I(q,16,ee)}; }
.oc-sdk-btn[data-variant="default"]:active { background: ${I(q,22,ee)}; box-shadow: none; }
.oc-sdk-btn[data-variant="secondary"] { background: ${rn}; color: var(--oc-fg); }
.oc-sdk-btn[data-variant="secondary"]:hover { background-image: linear-gradient(${V}, ${V}); }
.oc-sdk-btn[data-variant="secondary"]:active { background-image: linear-gradient(${pe}, ${pe}); }
.oc-sdk-btn[data-variant="outline"] { background: var(--oc-sdk-raised-bg); color: ${_e}; ${Bt} }
.oc-sdk-btn[data-variant="outline"]:hover { background-image: linear-gradient(${V}, ${V}); }
.oc-sdk-btn[data-variant="outline"]:active { background-image: linear-gradient(${pe}, ${pe}); box-shadow: none; }
.oc-sdk-btn[data-variant="ghost"] { background: transparent; }
.oc-sdk-btn[data-variant="ghost"]:hover { background: ${V}; }
.oc-sdk-btn[data-variant="ghost"]:active { background: ${pe}; }
.oc-sdk-btn[data-variant="destructive"] { --oc-sdk-tone: ${R("status-error","red")}; color: ${Ht}; background: ${I("var(--oc-sdk-tone)",7,ee)}; border-color: ${I("var(--oc-sdk-tone)",12)}; ${ir} }
.oc-sdk-btn[data-variant="destructive"]:hover { background: ${I("var(--oc-sdk-tone)",9,ee)}; }
.oc-sdk-btn[data-variant="destructive"]:active { background: ${I("var(--oc-sdk-tone)",11,ee)}; box-shadow: none; }

.oc-sdk-field-note { color: ${v}; }
.oc-sdk-field[data-invalid="true"] .oc-sdk-field-note { color: ${Ht}; }
.oc-sdk-input { border-radius: ${Ft}; background: var(--oc-sdk-field-bg); color: ${_e}; ${Vt("var(--oc-sdk-edge)")} transition: background 150ms ease-out; }
.oc-sdk-input::placeholder { color: ${v}; }
.oc-sdk-input:hover:not(:focus) { background-image: linear-gradient(${V}, ${V}); }
.oc-sdk-input:focus, .oc-sdk-input:focus-visible { ${Vt(I(W,26))} }
.oc-sdk-field[data-invalid="true"] .oc-sdk-input, .oc-sdk-field[data-invalid="true"] .oc-sdk-input:focus { ${Vt(R("status-error","red"))} }
.oc-sdk-input[data-mono="true"] { font-family: ${Xt}; }

.oc-sdk-search-icon { color: ${v}; }
.oc-sdk-search[data-active="true"] .oc-sdk-search-icon { color: ${q}; }
.oc-sdk-search-clear { border-radius: ${nr}; color: ${v}; }
.oc-sdk-search-clear:hover { background: ${V}; color: ${W}; }

.oc-sdk-trigger { border-radius: ${Ft}; background: var(--oc-sdk-raised-bg); color: ${_e}; ${Bt} transition: background 150ms ease-out; }
.oc-sdk-trigger:hover { background-image: linear-gradient(${V}, ${V}); }
.oc-sdk-trigger[aria-expanded="true"] { background-image: linear-gradient(${pe}, ${pe}); }
.oc-sdk-trigger-value[data-empty="true"] { color: ${v}; }
.oc-sdk-trigger-chevron { color: ${v}; }
/* The app's dropdown light: lit top, hairline rings and a layered shadow. Its outer ring is the border, over the page like the app's. */
.oc-sdk-popup { --surface-foreground: ${_e}; border-color: var(--oc-sdk-float-edge); border-radius: 12px; background: ${Ke}; background-clip: padding-box; color: ${_e}; box-shadow: var(--oc-sdk-float); }
.oc-sdk-option { border-radius: 8px; }
.oc-sdk-option[data-active="true"] { background: ${V}; }
/* A selected option shows a check mark in the text colour, like the app's own pickers. Options without the mark come
   from bundles built before it existed and keep the selection fill as their only sign of the choice. */
.oc-sdk-option[aria-selected="true"]:not([data-mark]) { background: ${Gt}; color: ${Dt}; }
.oc-sdk-option-check { color: ${W}; }
.oc-sdk-option[data-destructive="true"] { color: ${Ht}; }
.oc-sdk-option[data-destructive="true"][data-active="true"] { background: ${I(R("status-error","red"),10)}; }
.oc-sdk-option-hint { color: ${v}; }
.oc-sdk-popup-empty { color: ${v}; }

/* Checked stays neutral: the mark carries the state, and the primary colour stays with primary actions. */
.oc-sdk-check-box { border-color: ${se}; border-radius: 4px; color: ${W}; transition: border-color 150ms ease-out; }
.oc-sdk-check[aria-checked="true"] .oc-sdk-check-box { border-color: ${I(W,60,se)}; }
.oc-sdk-check-thumb { border-radius: 9999px; background: ${se}; transition: background 150ms ease-out; }
.oc-sdk-check-thumb::after { border-radius: 9999px; background: ${ee}; transition: transform 150ms ease-out; }
.oc-sdk-check[aria-checked="true"] .oc-sdk-check-thumb { background: ${q}; }
.oc-sdk-check[aria-checked="true"] .oc-sdk-check-thumb::after { transform: translateX(16px); }
.oc-sdk-check:focus-visible { box-shadow: none; }
.oc-sdk-check:focus-visible .oc-sdk-check-box, .oc-sdk-check:focus-visible .oc-sdk-check-thumb { ${sr} }
.oc-sdk-check-desc { color: ${v}; }

.oc-sdk-tabs { border-radius: 10px; }
.oc-sdk-tabs[data-track="true"] { background: ${I(W,4)}; box-shadow: inset 0 1px 2px 0 rgb(0 0 0 / 0.16); }
.oc-sdk-tab { border-radius: 8px; color: ${v}; transition: color 150ms ease-out, background 150ms ease-out; }
.oc-sdk-tab:hover { color: ${W}; }
.oc-sdk-tab[aria-selected="true"] { color: ${Dt}; background: ${Gt}; border-color: ${se}; }
.oc-sdk-tabs[data-track="true"] .oc-sdk-tab[aria-selected="true"] { color: ${_e}; background: var(--oc-sdk-raised-bg); ${Bt} }
.oc-sdk-tab-count { color: ${v}; }

.oc-sdk-badge { border-radius: 9999px; background: ${V}; color: ${v}; }
.oc-sdk-badge[data-tone] { color: var(--oc-sdk-tone-text, var(--oc-sdk-tone)); background: ${I("var(--oc-sdk-tone)",15)}; }

.oc-sdk-row { border-radius: 6px; transition: background 120ms ease-out; }
.oc-sdk-row:hover, .oc-sdk-row[data-active="true"] { background: ${V}; }
.oc-sdk-row[aria-selected="true"] { background: ${Gt}; color: ${Dt}; }
.oc-sdk-row-lead { font-family: ${Xt}; color: ${v}; }
.oc-sdk-row-sub { color: ${v}; }
.oc-sdk-row-meta { color: ${v}; }
.oc-sdk-row[aria-selected="true"] .oc-sdk-row-lead, .oc-sdk-row[aria-selected="true"] .oc-sdk-row-sub, .oc-sdk-row[aria-selected="true"] .oc-sdk-row-meta { color: inherit; opacity: .75; }
.oc-sdk-list-empty { color: ${v}; }

.oc-sdk-empty-body { color: ${v}; }

.oc-sdk-spinner { color: ${v}; }
.oc-sdk-spinner-ring { border-color: ${se}; border-top-color: ${q}; border-radius: 9999px; }

/* Set apart by its tint alone, like the app's banners. */
.oc-sdk-banner { border-color: transparent; border-radius: 8px; background: ${I("var(--oc-sdk-tone)",10)}; }
.oc-sdk-banner-title { color: var(--oc-sdk-tone-text, var(--oc-sdk-tone)); }
.oc-sdk-banner-body { color: ${v}; }

.oc-sdk-separator { color: ${v}; }
.oc-sdk-separator::before, .oc-sdk-separator::after { background: ${I(se,40)}; }

.oc-sdk-progress-label { color: ${v}; }
.oc-sdk-progress-track { border-radius: 9999px; background: ${se}; }
.oc-sdk-progress-fill { border-radius: 9999px; background: var(--oc-sdk-tone, ${q}); }

.oc-sdk-text a { color: ${$t}; text-decoration: underline; text-underline-offset: 2px; }
.oc-sdk-text img { border-radius: 8px; border: 1px solid ${I(se,60)}; }
`,B=`
${lt}
${an}
${dr}`;var un=0,ie=(e,o)=>{let n=document.createElementNS("http://www.w3.org/2000/svg",e);for(let[s,i]of Object.entries(o))n.setAttribute(s,String(i));return n},Kt=(e)=>{let o=document.createElement("div");o.className="chart",o.style.height=`${e.height}px`;let n=e.height,s=ie("svg",{viewBox:`0 0 300 ${n}`,preserveAspectRatio:"none","aria-hidden":"true"}),i=`fill-${++un}`,a=ie("defs",{}),d=ie("linearGradient",{id:i,x1:0,x2:0,y1:0,y2:1});d.append(ie("stop",{offset:"0%","stop-color":e.color,"stop-opacity":0.32}),ie("stop",{offset:"100%","stop-color":e.color,"stop-opacity":0.02})),a.append(d);let _=ie("path",{d:"",class:"chart-grid"}),E=ie("path",{d:"",fill:`url(#${i})`}),T=ie("path",{d:"",fill:"none",stroke:e.color,"stroke-width":1.5,"vector-effect":"non-scaling-stroke","stroke-linejoin":"round"});s.append(a,_,E,T);let A=document.createElement("div");A.className="chart-cursor";let w=document.createElement("div");w.className="chart-dot",w.style.background=e.color;let b=document.createElement("div");b.className="chart-tip",o.append(s,A,w,b);let h=[],X=1,D=null,Q=null,Z=(U,L)=>(e.capacity-L+U)/Math.max(1,e.capacity-1)*300,de=(U)=>n-1-Math.min(U,X)/X*(n-1-2),re=()=>{let U=D===null?void 0:h[D];if(D===null||U===void 0){o.classList.remove("hovering");return}o.classList.add("hovering");let L=o.getBoundingClientRect(),M=Z(D,h.length)/300*L.width,H=de(U)/n*L.height;A.style.transform=`translateX(${M}px)`,w.style.transform=`translate(${M}px, ${H}px)`;let f=(h.length-1-D)*e.intervalSeconds;b.textContent=`${e.format(U)} · ${f===0?"now":`${f} s ago`}`;let p=M>L.width/2;b.style.left=p?"":`${M+8}px`,b.style.right=p?`${L.width-M+8}px`:""},ne=(U)=>{if(h.length===0)return;let L=o.getBoundingClientRect(),M=(U-L.left)/L.width*(e.capacity-1),H=Math.round(M-(e.capacity-h.length));D=Math.min(h.length-1,Math.max(0,H)),re()};return o.addEventListener("pointermove",(U)=>{Q=U.clientX,ne(U.clientX)}),o.addEventListener("pointerleave",()=>{Q=null,D=null,re()}),{element:o,update:(U,L)=>{if(h=U,X=L>0?L:1,_.setAttribute("d",[0.25,0.5,0.75].map((M)=>`M0 ${n*M} H300`).join(" ")),h.length===0)E.setAttribute("d",""),T.setAttribute("d","");else{let M=h.map((Y,le)=>`${Z(le,h.length).toFixed(2)} ${de(Y).toFixed(2)}`),H=h.length===1,f=H?`M${Z(0,1)-2} ${M[0]?.split(" ")[1]} L${M[0]}`:`M${M.join(" L")}`;T.setAttribute("d",f);let p=H?Z(0,1)-2:Z(0,h.length);E.setAttribute("d",`${f} L300 ${n} L${p.toFixed(2)} ${n} Z`)}if(Q!==null)ne(Q)}}};var c=(e,o="",n="",s=[])=>{let i=document.createElement(e);if(o)i.className=o;if(n)i.textContent=n;if(s.length>0)i.append(...s);return i},k=(e,o)=>{if(e.textContent!==o)e.textContent=o},ae=(e,o,n,s,i,a=0)=>{let d=new Map;for(let E of o){let T=n(E);for(let w=1;d.has(T);w+=1)T=`${n(E)}\x01${w}`;let A=i.get(T);if(A)A.update(E);d.set(T,A??s(E))}for(let[E,T]of i)if(d.get(E)!==T)T.element.remove();i.clear();let _=a;for(let[E,T]of d){i.set(E,T);let A=e.children[_]??null;if(A!==T.element)e.insertBefore(T.element,A);_+=1}};var Yt=5000,lr={"needs-approval":"Allow the local service for Resource Monitor in Settings → Extensions.",paused:"Resource Monitor is paused in Settings → Extensions.","service-failed":"The monitoring service stopped. It restarts on the next refresh.",unreachable:"Could not reach the monitoring service.","bad-answer":"The monitoring service answered with something unexpected."},Ze=(e)=>typeof e==="object"&&e!==null,mn=(e)=>Ze(e)&&typeof e.at==="number"&&Ze(e.system)&&Ze(e.app)&&Array.isArray(e.app.groups)&&Array.isArray(e.servers)&&Array.isArray(e.outside)&&Ze(e.history),fn=(e)=>{if(!(e instanceof m))return"unreachable";if(e.code==="NO_SERVICE"||e.code==="NOT_GRANTED")return"needs-approval";if(e.code==="DISABLED")return"paused";if(e.code==="SERVICE_FAILED")return"service-failed";return"unreachable"},pr=async(e,o)=>{try{return(await e.serviceRequest({method:"POST",path:"/stop",body:JSON.stringify(o)})).status===200}catch{return!1}},ur=(e,o)=>{let n=c("button","port",`:${o}`);return n.type="button",n.title=`Open http://localhost:${o}`,n.addEventListener("click",(s)=>{s.stopPropagation(),e.openUrl(`http://localhost:${o}`).catch(()=>{return})}),n},Wt=(e)=>!document.hidden&&e.getBoundingClientRect().width>0,mr=(e,o,n,s)=>{let i=!1,a=async()=>{if(i||!Wt(o))return;i=!0;try{let E=await e.serviceRequest({method:"GET",path:"/snapshot"}),T;try{T=JSON.parse(E.body)}catch{T=null}if(E.status===200&&mn(T))n(T);else s(E.status===200?"bad-answer":"service-failed")}catch(E){s(fn(E))}finally{i=!1}};a(),setInterval(()=>{a()},Yt);let d=Wt(o),_=()=>{let E=Wt(o);if(E&&!d)a();d=E};return document.addEventListener("visibilitychange",_),new ResizeObserver(_).observe(document.documentElement),{refresh:()=>{a()}}};var Jt="en",fr=(e)=>{try{Jt=Intl.NumberFormat.supportedLocalesOf(e)[0]??"en"}catch{Jt="en"}},Er=(e,o)=>new Intl.NumberFormat(Jt,{minimumFractionDigits:o,maximumFractionDigits:o}).format(e),oe=(e)=>{let o=["B","KB","MB","GB","TB"],n=Math.max(0,e),s=0;while(n>=1024&&s<o.length-1)n/=1024,s+=1;let i=s>=3&&n<100?1:0;return`${Er(n,i)} ${o[s]}`},ue=(e)=>{if(e===null)return"–";if(e>0&&e<0.01)return"<0.01%";return`${Er(e,e>0&&e<1?2:e<10?1:0)}%`},_r=(e,o)=>e===null?null:e/Math.max(1,o),Sr=(e)=>{let o=Math.floor(e/86400),n=Math.floor(e%86400/3600),s=Math.floor(e%3600/60);if(o>0)return`${o} d ${n} h`;if(n>0)return`${n} h ${s} min`;return`${s} min`},qe=(e,o)=>{let n=o.replace(/^"([^"]+)"/,"$1");if(!e||!/^([A-Za-z]:)?[\\/]/.test(n))return o;let s=-1;while((s=n.indexOf(e,s+1))>=0){if(!/[\\/]/.test(n[s-1]??""))continue;let i=n.slice(s+e.length).replace(/^\.exe/i,"");if(i===""||i.startsWith(" "))return i.trim()}return o},En={renderer:"Renderer","gpu-process":"GPU",utility:"Utility",zygote:"Zygote"},_n=[[/network/i,"Network service"],[/storage/i,"Storage service"],[/audio/i,"Audio service"],[/video_?capture/i,"Video capture"]],et=(...e)=>e.filter(Boolean).join(" · "),Qt=(e,o)=>{let n=e.ports.map((d)=>`:${d}`).join(" ");if(o==="root")return{title:"Main process",detail:et(n,qe(e.name,e.command))};if(o==="self")return{title:"Resource Monitor",detail:"this extension"};let s=/--type=([\w-]+)/.exec(e.command)?.[1];if(s&&/\bHelper\b/.test(e.name)){let d=s==="utility"?/--utility-sub-type=([\w.]+)/.exec(e.command)?.[1]??"":"";return{title:_n.find(([E])=>E.test(d))?.[1]??En[s]??s,detail:et(n,qe(e.name,e.command))}}let i=e.label||e.name,a=qe(e.name,e.command);return{title:i,detail:et(n,a===i||a===e.name?"":a)}},Zt=(e)=>{let o=qe(e.name,e.command),n=o===e.title||o===e.name||e.command===e.title;return et(e.ports.map((s)=>`:${s}`).join(" "),e.count>1?`${e.count} processes`:"",n?"":o)},Tr=(e)=>{if(e==="darwin")return"macOS";if(e==="win32")return"Windows";if(e==="linux")return"Linux";return e},tt={app:"OpenDiscovery",opencode:"OpenDiscovery Engine",terminals:"Terminal"},hr={app:"OpenDiscovery",opencode:"Agent",terminals:"Terminal"},ce={cpu:"var(--oc-info)",memory:"var(--oc-success)",app:"var(--oc-primary)",opencode:"color-mix(in srgb, var(--oc-primary) 50%, var(--oc-fg))",terminals:"var(--oc-muted)"};var xr=`
  html, body { margin: 0; background: transparent; color: var(--oc-fg); font: 12px/1.4 var(--oc-font); }
  * { box-sizing: border-box; }
  .num { font-variant-numeric: tabular-nums; }
  .muted { color: var(--oc-muted); }
  .chart { position: relative; width: 100%; }
  .chart svg { position: absolute; inset: 0; width: 100%; height: 100%; display: block; }
  .chart-grid { stroke: var(--oc-border); stroke-width: 1; vector-effect: non-scaling-stroke; opacity: .5; fill: none; }
  .chart-cursor, .chart-dot, .chart-tip { position: absolute; pointer-events: none; opacity: 0; }
  .chart.hovering .chart-cursor, .chart.hovering .chart-dot, .chart.hovering .chart-tip { opacity: 1; }
  .chart-cursor { top: 0; bottom: 0; left: 0; width: 1px; background: var(--oc-border); }
  .chart-dot { top: -3px; left: -3px; width: 6px; height: 6px; border-radius: 50%; box-shadow: 0 0 0 2px color-mix(in srgb, var(--oc-fg) 4%, var(--oc-bg)); }
  /* Floats like the app's dropdowns: lit top edge and hairline rings instead of a border. The plot is
     clipped by its own SVG, so the label can cross the chart's edge without being cut off. */
  .chart-tip { top: 2px; padding: 1px 6px; border-radius: 4px; white-space: nowrap; font-size: 11px;
    background: var(--oc-elevated); color: var(--oc-elevated-fg); font-variant-numeric: tabular-nums;
    box-shadow: inset 0 1px 0 0 rgb(255 255 255 / .8), inset 0 0 0 1px rgb(0 0 0 / .04), 0 0 0 1px rgb(0 0 0 / .1), 0 1px 2px -.5px rgb(0 0 0 / .08); }
  [data-oc-theme="dark"] .chart-tip { box-shadow: inset 0 1px 0 0 rgb(255 255 255 / .06), inset 0 0 0 1px rgb(255 255 255 / .08),
    0 0 0 1px rgb(0 0 0 / .36), 0 1px 1px -.5px rgb(0 0 0 / .22); }
  .port { display: inline-flex; align-items: center; height: 18px; padding: 0 6px; border: 0; border-radius: 4px; font: 11px var(--oc-mono); cursor: pointer;
    background: color-mix(in srgb, var(--oc-primary) 14%, transparent); color: var(--oc-primary-text, var(--oc-primary)); }
  .port:hover, .port:focus-visible { outline: none; background: color-mix(in srgb, var(--oc-primary) 24%, transparent); }
`,gr=`
  html, body { height: 100%; overflow-y: auto; overflow-x: hidden; }
  #root { display: flex; flex-direction: column; gap: 14px; padding: 12px 12px 20px; }
  .head { display: flex; align-items: flex-start; gap: 8px; }
  .head .titles { min-width: 0; flex: 1; }
  .host-name { font-size: 13px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .host-meta { color: var(--oc-muted); font-size: 11px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .live { display: inline-flex; align-items: center; gap: 6px; color: var(--oc-muted); font-size: 11px; white-space: nowrap; padding-top: 2px; }
  .live::before { content: ''; width: 6px; height: 6px; border-radius: 50%; background: var(--oc-success); }
  .live.stale::before { background: var(--oc-muted); }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; }
  /* Cards are flat and set apart by tone, like the app's tiles: no border. */
  .card { min-width: 0; display: flex; flex-direction: column; gap: 8px; padding: 12px;
    border-radius: var(--oc-radius); background: color-mix(in srgb, var(--oc-fg) 4%, transparent); }
  .card-top { display: flex; align-items: baseline; gap: 8px; }
  .label { font-size: 11px; font-weight: 600; letter-spacing: .02em; color: var(--oc-muted); text-transform: uppercase; }
  .big { font-size: 22px; font-weight: 600; line-height: 1.1; letter-spacing: -.01em; }
  .card-top .grow { flex: 1; }
  .sub { color: var(--oc-muted); font-size: 11px; }
  /* A track inside a card is the next tone step; segments part by a 1px gap. */
  .stack { display: flex; gap: 1px; height: 8px; border-radius: 4px; overflow: hidden; background: color-mix(in srgb, var(--oc-fg) 8%, transparent); }
  .stack > span { height: 100%; }
  .legend { display: flex; flex-direction: column; gap: 4px; }
  .legend-row { display: grid; grid-template-columns: 10px minmax(0, 1fr) auto auto; align-items: center; gap: 8px; }
  .legend-row .swatch { width: 8px; height: 8px; border-radius: 2px; }
  .legend-row .name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .legend-row .value { text-align: right; min-width: 56px; }
  .section { display: flex; flex-direction: column; gap: 6px; }
  .section-head { display: flex; align-items: baseline; gap: 8px; padding: 0 2px; }
  .section-head .grow { flex: 1; }
  .empty { color: var(--oc-muted); padding: 6px 2px; }
  .origin { font-size: 10px; padding: 0 5px; border-radius: 4px; line-height: 16px; background: color-mix(in srgb, var(--oc-fg) 6%, transparent); color: var(--oc-muted); flex: none; }
  /* Lists sit on the panel itself, grouped by space: lines only under the column header and between groups. */
  .list { display: flex; flex-direction: column; }
  .cols, .row, .group-head { display: grid; grid-template-columns: minmax(0, 1fr) auto 56px 72px; align-items: center; column-gap: 8px; }
  .action { display: flex; align-items: center; justify-content: flex-end; }
  .action:empty { display: block; }
  .cols { padding: 0 2px 4px; color: var(--oc-muted); font-size: 11px; border-bottom: 1px solid var(--oc-border); }
  .cell { text-align: right; white-space: nowrap; }
  .quiet { color: var(--oc-muted); }
  /* Three levels, told apart by size, weight and indent rather than boxes:
     group heading, rows on a rail in the group's colour, unfolded members deeper and quieter. */
  .row { padding: 7px 2px; }
  .group { display: flex; flex-direction: column; padding: 4px 0 10px; border-bottom: 1px solid var(--oc-border); }
  .group-head { padding: 12px 2px 6px; font-size: 13px; }
  .group-head .cell { font-weight: 600; }
  .group > .row, .group > .job-wrap { margin-left: 4px; padding-left: 12px;
    border-left: 2px solid color-mix(in srgb, var(--group-color, var(--oc-border)) 40%, transparent); }
  .group > .row { padding-top: 5px; padding-bottom: 5px; }
  .group > .job-wrap > .row { padding: 5px 2px; }
  .group .row .cell { color: color-mix(in srgb, var(--oc-fg) 80%, transparent); }
  .group .row .cell.quiet { color: var(--oc-muted); }
  .gname { display: flex; align-items: center; gap: 6px; min-width: 0; }
  .gname b { font-weight: 650; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .count { color: var(--oc-muted); font-weight: 400; }
  .dot { flex: none; width: 6px; height: 6px; border-radius: 50%; }
  .who { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
  .title-line { display: flex; align-items: center; gap: 6px; min-width: 0; }
  .pname { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
  .pname.strong { font-weight: 600; flex: none; max-width: 50%; }
  .pdetail { color: var(--oc-muted); font: 11px/1.35 var(--oc-mono); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .job.foldable, .group-head.foldable { cursor: pointer; }
  .group-head.foldable .gname::before { content: ''; flex: none; width: 0; height: 0; margin-right: 1px;
    border-left: 4px solid var(--oc-muted); border-top: 3.5px solid transparent; border-bottom: 3.5px solid transparent; transition: transform .15s ease; }
  .group-head.foldable.open .gname::before { transform: rotate(90deg); }
  /* Focus draws no ring, like the app: a focused row takes the hover fill. */
  .group-head.foldable:focus-visible, .job.foldable:focus-visible { outline: none; border-radius: 4px; background: var(--oc-hover); }
  .job.foldable .title-line::before { content: ''; flex: none; width: 0; height: 0; margin: 0 2px 0 1px;
    border-left: 4px solid var(--oc-muted); border-top: 3.5px solid transparent; border-bottom: 3.5px solid transparent; transition: transform .15s ease; }
  .job.foldable.open .title-line::before { transform: rotate(90deg); }
  .job-wrap.open .pdetail { white-space: normal; overflow-wrap: anywhere; }
  .pdetail { user-select: text; }
  .members { display: flex; flex-direction: column; padding: 0 0 6px 16px; }
  .row.member { padding: 3px 2px; font-size: 11.5px; }
  .row.member .pname { color: var(--oc-muted); }
  .row.member .pdetail { font-size: 10.5px; }
  .group .row.member .cell { color: var(--oc-muted); }
  .more { color: var(--oc-muted); padding: 2px 2px 4px; font-size: 11px; }
  /* Stop is a text button: no fill, it only changes colour, and asks once before acting. */
  .stop { flex: none; padding: 0 2px; border: 0; background: none; font: 11px var(--oc-font); color: var(--oc-muted); cursor: pointer; }
  .stop:hover, .stop:focus-visible { color: var(--oc-error-text, var(--oc-error)); }
  .stop.armed { color: var(--oc-error-text, var(--oc-error)); font-weight: 600; }
  .stop:disabled { cursor: default; opacity: .6; }
  .stop:focus-visible { outline: none; }
  /* The tint says warning or error; no border. */
  .banner { padding: 8px 12px; border-radius: var(--oc-radius);
    background: color-mix(in srgb, var(--oc-warning) 10%, transparent); color: var(--oc-warning-text, var(--oc-fg)); }
  .banner.error { background: color-mix(in srgb, var(--oc-error) 10%, transparent);
    color: var(--oc-error-text, var(--oc-fg)); }
  .footnote { color: var(--oc-muted); font-size: 11px; padding: 0 2px; }
  [hidden] { display: none !important; }
`;var qt=36;var xe=Nt(),so=document.querySelector("#root");if(!so)throw Error("Missing #root");var yr=document.createElement("style");yr.textContent=xr+gr;document.head.append(yr);var io=Yt/1000,Ae=c("div","banner");Ae.hidden=!0;var Ar=c("div","host-name","This machine"),vr=c("div","host-meta","Reading…"),Re=c("div","live stale","Starting"),Rr=c("div","head");Rr.append(c("div","titles","",[Ar,vr]),Re);var kr=(e,o,n)=>{let s=c("span","big num","–"),i=c("span","sub num"),a=c("div","card-top","",[c("span","label",e),c("span","grow"),i]),d=Kt({color:o,height:56,capacity:qt,format:n,intervalSeconds:io}),_=c("div","sub num");return{card:c("div","card","",[a,s,d.element,_]),value:s,side:i,sub:_,chart:d}},Oe=kr("CPU",ce.cpu,ue),ye=kr("Memory",ce.memory,oe),Sn=c("div","grid","",[Oe.card,ye.card]),wr=c("span","big num","–"),eo=c("span","sub num"),Ur=Kt({color:ce.app,height:44,capacity:qt,format:oe,intervalSeconds:io}),Cr=c("div","stack"),Ir=c("div","legend"),Tn=c("div","card","",[c("div","card-top","",[c("span","label","OpenDiscovery"),c("span","grow"),eo]),wr,c("div","sub","The app, OpenDiscovery Engine, and everything they started"),Ur.element,Cr,Ir]),hn=()=>{let e=c("span","cell","CPU");return e.title="CPU as a percentage of total machine capacity, on the same scale as the CPU card.",c("div","cols","",[c("span"),c("span"),e,c("span","cell","Memory")])},st=(e)=>c("span","action","",e?[e]:[]),Lr=c("span","count"),to=c("div","list"),Mr=c("div","empty","No dev servers right now. Servers started by an agent, a project action, or the terminal show up here with their ports."),xn=c("section","section","",[c("div","section-head","",[c("span","label","Dev servers"),Lr]),to,Mr]),Nr=c("div","list"),gn=c("section","section","",[c("div","section-head","",[c("span","label","Processes")]),hn(),Nr]),Pr=c("div","list"),ao=c("section","section","",[c("div","section-head","",[c("span","label","OpenDiscovery Engine outside OpenDiscovery")]),Pr]);ao.hidden=!0;var bn=c("div","footnote","CPU everywhere is a percentage of total machine capacity: all logical cores together are 100%. Memory is resident memory: pages a process shares with others count in each of them.");so.append(Ae,Rr,Sn,Tn,xn,gn,ao,bn);var Gr=()=>{return},co=(e,o,n)=>{let s=c("button","stop",e);s.type="button";let i=!1,a,d=()=>{i=!1,s.classList.remove("armed"),s.textContent=e};return s.addEventListener("click",(_)=>{if(_.preventDefault(),_.stopPropagation(),s.disabled)return;if(!i){i=!0,s.classList.add("armed"),s.textContent=o,clearTimeout(a),a=setTimeout(d,4000);return}clearTimeout(a),s.disabled=!0,s.textContent="Stopping…",pr(xe,n).then((E)=>{if(!E)Hn();s.disabled=!1,d(),Gr()})}),s},oo=0,ro=1,On=(e)=>e.pid===oo?"root":e.label==="Resource Monitor"&&e.ppid===oo?"self":"other",it=(e)=>{let o=c("span"),n=c("span","cell num");return{cpu:o,memory:n,set:(i,a)=>{let d=e==="per-core"?_r(i,ro):i,_=d!==null&&d*ro>=1?"cell num":"cell num quiet";if(o.className!==_)o.className=_;k(o,ue(d)),k(n,oe(a))}}},Dr=(e,o)=>{let n=c("span","title-line","",[c("span","pname",e)]),s=c("span","pdetail"),i=(a)=>{k(s,a),s.hidden=a===""};return i(o),{element:c("div","who","",[n,s]),setDetail:i}},lo=(e,o)=>{let{title:n,detail:s}=Qt(e,o);return[e.pid,o,n,s,e.name,e.command].join("\x00")},po=(e,o,n="row")=>{let{title:s,detail:i}=Qt(e,o),a=it("per-core");a.set(e.cpu,e.memory);let d=c("div",n,"",[Dr(s,i).element,st(),a.cpu,a.memory]);return d.title=`${e.name} · pid ${e.pid}${e.command?`
${e.command}`:""}`,{element:d,update:(_)=>a.set(_.cpu,_.memory)}},Te=new Set,$r=(e)=>e.members.length>0&&e.count>1,yn=(e,o)=>[e.pid,e.name,e.title,e.command,o,$r(e)].join("\x00"),An=(e)=>lo(e,"other"),vn=(e)=>po(e,"other","row member"),Rn=(e,o)=>{let n=$r(e),s=o?co("Stop",`Stop ${e.title}?`,{kind:"job",pid:e.pid,name:e.name}):void 0,i=it("per-core"),a=Dr(e.title,Zt(e)),d=c("div",n?"row job foldable":"row job","",[a.element,st(s),i.cpu,i.memory]);d.title=e.command||e.title;let _=c("div","job-wrap","",[d]),E=c("div","more"),T=c("div","members","",[E]),A=new Map,w=e,b=(h)=>{w=h,i.set(h.cpu,h.memory),a.setDetail(Zt(h));let X=n&&Te.has(h.pid);if(d.classList.toggle("open",X),_.classList.toggle("open",X),n)d.setAttribute("aria-expanded",String(X));if(!X){T.remove();return}ae(T,h.members,An,vn,A);let D=h.count-h.members.length;if(E.hidden=D<=0,k(E,D===1?"1 more process, idle":`${D} more processes, idle`),T.parentElement!==_)_.append(T)};if(n){d.tabIndex=0,d.setAttribute("role","button");let h=()=>{if(Te.has(w.pid))Te.delete(w.pid);else Te.add(w.pid);b(w)};d.addEventListener("click",h),d.addEventListener("keydown",(X)=>{if(X.key==="Enter"||X.key===" ")X.preventDefault(),h()})}return b(e),{element:_,update:b}},Hr="collapsed-groups",he=new Set,ot=!1,kn=()=>{if(!ot)return;xe.storage.set(Hr,[...he],{scope:"device"}).catch(()=>{return})},wn=async()=>{if(!ot)return;try{let e=await xe.storage.get(Hr,{scope:"device"});if(!Array.isArray(e))return;for(let o of e)if(o==="app"||o==="opencode"||o==="terminals")he.add(o);if(no)Vr(no)}catch{}},Un=(e)=>{let o=(n)=>e.id==="terminals"||e.id==="opencode"&&n.ports.length>0;return[...e.processes.map((n)=>({kind:"process",row:n,role:On(n)})),...e.jobs.map((n)=>({kind:"job",job:n,stoppable:o(n)}))]},Cn=(e)=>e.kind==="process"?`process\x00${lo(e.row,e.role)}`:`job\x00${yn(e.job,e.stoppable)}`,In=(e)=>{if(e.kind==="process"){let n=po(e.row,e.role);return{element:n.element,update:(s)=>{if(s.kind==="process")n.update(s.row)}}}let o=Rn(e.job,e.stoppable);return{element:o.element,update:(n)=>{if(n.kind==="job")o.update(n.job)}}},Xr=(e)=>e.id==="terminals"&&e.jobs.length>0,Ln=(e)=>`${e.id}\x00${Xr(e)}`,Mn=(e)=>{let o=c("span","dot");o.style.background=ce[e.id];let n=Xr(e)?co("Stop all","Stop everything running in the terminal?",{kind:"terminals"}):void 0,s=c("span","count"),i=c("span","gname","",[o,c("b","",tt[e.id]),s]),a=it("share"),d=c("div","group-head foldable","",[i,st(n),a.cpu,a.memory]);d.tabIndex=0,d.setAttribute("role","button");let _=c("div","group","",[d]);_.style.setProperty("--group-color",ce[e.id]);let E=new Map,T=e,A=(b)=>{T=b,k(s,String(b.count)),a.set(b.cpu,b.memory);let h=he.has(b.id);d.classList.toggle("open",!h),d.setAttribute("aria-expanded",String(!h)),ae(_,h?[]:Un(b),Cn,In,E,1)},w=()=>{if(he.has(T.id))he.delete(T.id);else he.add(T.id);kn(),A(T)};return d.addEventListener("click",w),d.addEventListener("keydown",(b)=>{if(b.key==="Enter"||b.key===" ")b.preventDefault(),w()}),A(e),{element:_,update:A}},Nn=(e)=>[e.pid,e.name,e.group,e.ports.join(","),e.command,e.job?.pid??"",e.job?.name??"",e.job?.title??""].join("\x00"),Pn=(e)=>{let o=e.ports.map((E)=>ur(xe,E)),n=c("div","title-line","",[...o,c("span","pname strong",e.name),c("span","origin",hr[e.group])]),s=e.job?co("Stop",`Stop ${e.job.title}?`,{kind:"job",pid:e.job.pid,name:e.job.name}):void 0,i=c("div","who","",[n]),a=e.job?.title??"";if(a)i.append(c("span","pdetail",a));let d=it("per-core");d.set(e.cpu,e.memory);let _=c("div","row server","",[i,st(s),d.cpu,d.memory]);return _.title=`pid ${e.pid}${e.command?`
${e.command}`:""}`,{element:_,update:(E)=>d.set(E.cpu,E.memory)}},Gn=(e)=>{let o=c("span");o.style.background=ce[e.id],o.title=tt[e.id];let n=(s)=>{o.style.width=`${Math.min(100,s.value/Math.max(1,s.total)*100)}%`};return n(e),{element:o,update:n}},Dn=(e)=>{let o=c("span","swatch");o.style.background=ce[e.id];let n=c("span","muted"),s=c("span","value num muted"),i=c("span","value num"),a=(d)=>{k(n,` · ${d.count} ${d.count===1?"process":"processes"}`),k(s,ue(d.cpu)),k(i,oe(d.memory))};return a(e),{element:c("div","legend-row","",[o,c("span","name",tt[e.id],[n]),s,i]),update:a}},$n={"processes-unavailable":"The process list could not be read just now. OpenDiscovery's numbers are from the last reading that worked.","ports-unavailable":"Listening ports could not be read, so dev servers are not detected."},ve=null,rt=!1,br,Fr=[],no=null,nt=()=>{let e=ve!==null?lr[ve]:rt?"Could not stop it. It may have ended already, or it is not something this panel stops.":Fr.join(" ");Ae.hidden=e==="",Ae.classList.toggle("error",ve!==null||rt),k(Ae,e)};function Hn(){rt=!0,clearTimeout(br),br=setTimeout(()=>{rt=!1,nt()},6000),nt()}var Xn=new Map,Fn=new Map,Vn=new Map,Bn=new Map,jn=new Map;function Vr(e){no=e;let{system:o,app:n}=e;oo=n.rootPid,ro=o.cores,k(Ar,o.hostname),k(vr,[Tr(o.platform),o.arch,o.cpuModel,`up ${Sr(o.uptimeSeconds)}`].filter(Boolean).join(" · ")),k(Re,`Live · every ${io} s`),Re.classList.remove("stale"),k(Oe.value,ue(o.cpu)),k(Oe.side,`${o.cores} cores`),k(Oe.sub,o.load?`Load ${o.load.map((a)=>a.toFixed(2)).join(" · ")}`:"All cores together"),Oe.chart.update(e.history.system.cpu,100),k(ye.value,oe(o.memoryUsed)),k(ye.side,ue(o.memoryUsed/Math.max(1,o.memoryTotal)*100)),k(ye.sub,`of ${oe(o.memoryTotal)} · ${oe(Math.max(0,o.memoryTotal-o.memoryUsed))} free`),ye.chart.update(e.history.system.memory,o.memoryTotal),k(wr,oe(n.memory)),k(eo,`${ue(n.cpu)} CPU`),eo.title=`Share of all ${o.cores} cores, the same scale as the CPU card`,Ur.update(e.history.app.memory,Math.max(n.memory,...e.history.app.memory)*1.15);let s=n.groups.filter((a)=>a.memory>0).map((a)=>({id:a.id,value:a.memory,total:n.memory}));ae(Cr,s,(a)=>a.id,Gn,Xn),ae(Ir,n.groups,(a)=>a.id,Dn,Fn),k(Lr,e.servers.length>0?String(e.servers.length):""),ae(to,e.servers,Nn,Pn,Vn),to.hidden=e.servers.length===0,Mr.hidden=e.servers.length>0,ae(Nr,n.groups,Ln,Mn,Bn);let i=new Set(n.groups.flatMap((a)=>a.jobs.map((d)=>d.pid)));for(let a of Te)if(!i.has(a))Te.delete(a);ao.hidden=e.outside.length===0,ae(Pr,e.outside,(a)=>lo(a,"other"),(a)=>po(a,"other"),jn),Fr=e.warnings.map((a)=>$n[a]),nt()}var zn=(e)=>{ve=e,nt(),Re.textContent="Paused",Re.classList.add("stale")},Or=!1;xe.onReady((e)=>{if(Pt(e,document.documentElement),fr(e.locale),e.features?.deviceStorage===!0&&!ot)ot=!0,wn();if(Or)return;Or=!0,{refresh:Gr}=mr(xe,so,(o)=>{ve=null,Vr(o)},zn)});})();
