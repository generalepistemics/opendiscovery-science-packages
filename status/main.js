(()=>{var E="opendiscovery.sdk",f=1;var qe=`
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
`;function qt(e){let r=e.documentElement;if(r.hasAttribute("data-oc-scrollbar-activity"))return;r.setAttribute("data-oc-scrollbar-activity","");let n=new WeakMap;e.addEventListener("scroll",(u)=>{let i=u.target===e?r:u.target;if(!(i instanceof Element))return;if(!i.hasAttribute("data-oc-scrolling"))i.setAttribute("data-oc-scrolling","");let _=n.get(i);if(_!==void 0)clearTimeout(_);n.set(i,setTimeout(()=>{n.delete(i),i.removeAttribute("data-oc-scrolling")},1000))},{capture:!0,passive:!0})}var cr=`(${qt.toString()})(document);`;var et=128,tt=65536;var Oe=128;var Ae=65536;var ro=/^[a-z][a-z0-9-]{0,39}$/;var eo=(e)=>Object(e)===e&&!Array.isArray(e),ot=(e,r)=>Object.keys(e).every((n)=>r.includes(n)),to=(e)=>String(e)===e&&e.length>=1&&e.length<=60,oo=(e)=>String(e)===e&&e.length>=1&&e.length<=80,no=(e)=>{if(!Array.isArray(e)||e.length>4)return!1;let r=new Set;for(let n of e){if(!eo(n)||!ro.test(n.id)||!to(n.label))return!1;if(n.disabled!==void 0&&n.disabled!==!0&&n.disabled!==!1)return!1;if(r.has(n.id))return!1;if(r.add(n.id),n.kind==="button"){if(!ot(n,["kind","id","label","disabled"]))return!1;continue}if(n.kind!=="select"||!ot(n,["kind","id","label","value","options","disabled"]))return!1;if(!oo(n.value)||!Array.isArray(n.options)||n.options.length<1||n.options.length>16)return!1;let u=new Set;for(let i of n.options){if(!eo(i)||!ot(i,["value","label"])||!oo(i.value)||!to(i.label)||u.has(i.value))return!1;u.add(i.value)}if(!u.has(n.value))return!1}return!0};var ye=20000000,Re=256;var rt=(e)=>("bytes"in e)?e.bytes.byteLength:e.content.length,so=(e,r)=>{if(e.path!==r.path||e.readOnly!==r.readOnly)return!1;if(e.encoding==="text"||r.encoding==="text")return e.encoding==="text"&&r.encoding==="text"&&e.content===r.content;if(e.bytes.byteLength!==r.bytes.byteLength)return!1;for(let n=0;n<e.bytes.byteLength;n+=1)if(e.bytes[n]!==r.bytes[n])return!1;return!0};var io=/^[A-Za-z0-9_-]{1,80}$/;var ao=["left","right","top","bottom"];var co=(e,r=0,n={remaining:16000})=>{if(--n.remaining<0||r>=32)return!1;if(e===null)return!0;let u=Array.isArray(e)?e:Object(e)===e?Object.values(e):[];for(let i of u)if(!co(i,r+1,n))return!1;return!0},nt=(e)=>{if(e===null||e===!0||e===!1)return!0;if(Array.isArray(e))return Object.keys(e).every((r)=>/^(0|[1-9]\d*)$/.test(r)&&Number(r)<e.length)&&e.every(nt);if(Object(e)===e){let r=Object.getPrototypeOf(e);return(r===null||r===Object.prototype)&&Object.values(e).every(nt)}return String(e)===e||Number.isFinite(e)},st=(e)=>{try{if(String(e.id)!==e.id||!io.test(e.id)||!Number.isFinite(e.anchor.x)||Math.abs(e.anchor.x)>1e5||!Number.isFinite(e.anchor.y)||Math.abs(e.anchor.y)>1e5||!Number.isFinite(e.anchor.width)||!Number.isFinite(e.anchor.height)||e.anchor.width<=0||e.anchor.height<=0||e.anchor.width>1e5||e.anchor.height>1e5||!Number.isInteger(e.width)||e.width<160||e.width>640||!Number.isInteger(e.height)||e.height<48||e.height>480||e.side!==void 0&&!ao.includes(e.side)||e.focus!==void 0&&e.focus!==!0&&e.focus!==!1||!co(e.data)||!nt(e.data))return!1;return JSON.stringify(e.data).length<=16000}catch{return!1}};var po=["file","directory","other","missing"],at=(e)=>Boolean(e&&"sessionId"in e),ct=(e)=>Boolean(e&&"sent"in e&&!("sessionId"in e));var uo=/^[0-9a-f]{7,64}$/i,dt=(e)=>uo.test(e),ve=500,ke=32000,Eo=16000,fo=128,_o=200,mo=2000,So=16000,To=80,ho=200,xo=16000;var go=2000;var lt=20000,Ue=1024,we=2000000;var Ce=64000,Ie=8000,pt=4000;var ut=960000;var bo=999,Oo=1e4,me=500,Ao=["HOST_UNAVAILABLE","HOST_TIMEOUT","HOST_REJECTED","DISCONNECTED","DISABLED","BAD_PATH","NO_INTEGRATION","NO_SERVICE","SERVICE_FAILED","REQUEST_FAILED","RESPONSE_TOO_LARGE","NO_SESSION","SESSION_BUSY","NOT_GRANTED","NO_DIRECTORY","NOT_FOUND","FILE_TOO_LARGE","DENIED","NO_MODEL","MODEL_FAILED","UNSUPPORTED"],yo=["stopped","starting","ready","failed"],lr=new Set(Ao),Ro=(e)=>lr.has(e),vo=(e)=>e&&Ro(e)?e:"HOST_REJECTED",de=(e)=>{if(e===void 0)return!1;if(e===null||e===!0||e===!1)return!0;if(String(e)===e)return!0;if(Number(e)===e)return Number.isFinite(e);if(Array.isArray(e))return e.every(de);if(Object(e)===e)return Object.values(e).every(de);return!1},ko=(e)=>de(e)&&JSON.stringify(e).length<=xo,lo=(e)=>e?.trim().slice(0,ho)??"",le=(e)=>{let r=e.id.trim().slice(0,fo),n=e.title.trim().slice(0,_o),u=e.url.trim().slice(0,mo),i=e.text?.trim().slice(0,So),_=e.author?.trim().slice(0,To),b=e.kind==="pull"?"pull":"issue",R={providerId:e.providerId.trim(),id:r,title:n||r,url:u,kind:b};if(i)R.text=i;if(_)R.author=_;if(b==="pull"){let m=lo(e.branches?.head),S=lo(e.branches?.base);if(m&&S)R.branches={head:m,base:S}}if(ko(e.data))R.data=e.data;return R},Et=(e)=>{let r=le(e);if(e.projectId)r.projectId=e.projectId;if(e.navigation)r.navigation=e.navigation;if(e.worktree)r.worktree=e.worktree;return r},ft=(e)=>{let r={text:e.text.trim().slice(0,Eo)};if(e.send)r.send=!0;return r},_t=(e)=>{if(e===null||!Number.isFinite(e))return null;return Math.min(bo,Math.max(0,Math.round(e)))},mt=(e)=>{if(!Number.isFinite(e))return 0;return Math.min(Oo,Math.max(0,Math.ceil(e)))};var pe=(e)=>e.length>0&&e.length<=Ue&&!e.includes("\x00")&&!e.includes("\\");var Le=(e)=>{if(!e.startsWith("/")||e.includes("\x00")||e.includes("\\")||e.includes("://"))return!1;if(e.length>go)return!1;return!e.split("/").some((n)=>n==="."||n==="..")},pr=new Set(yo),St=(e)=>Boolean(e&&"status"in e&&pr.has(String(e.status))&&!("body"in e)),Me=(e)=>Boolean(e&&"status"in e&&"body"in e&&Number.isInteger(e.status)),Tt=(e)=>Boolean(e&&"content"in e&&String(e.content)===e.content),ht=(e)=>Boolean(e&&"written"in e&&e.written===!0),xt=(e)=>Boolean(e&&"entries"in e&&Array.isArray(e.entries)),ur=new Set(po),gt=(e)=>Boolean(e&&"kind"in e&&"size"in e&&ur.has(String(e.kind))&&Number.isFinite(e.size)),bt=(e)=>Boolean(e&&"text"in e&&String(e.text)===e.text&&!("status"in e)),Er=new Set(["workspace","shells","ready","directory","session","connection","settings","session-lifecycle","item","resolve","action","status-control-event","popover-closed","file-open","file-snapshot","file-saved","generate-late"]),fr=(e)=>Object(e)===e?e:null,it=(e)=>String(e)===e&&e.length>0,_r=(e)=>{if(!it(e.id))return null;if(e.ok===!0){let r={channel:E,v:f,type:"result",id:e.id,ok:!0};if(Object(e.payload)===e.payload)r.payload=e.payload;return r}if(e.ok===!1&&it(e.error))return{channel:E,v:f,type:"result",id:e.id,ok:!1,error:e.error,code:vo(it(e.code)?e.code:void 0)};return null},Ot=(e)=>{let r=fr(e);if(!r||r.channel!==E||r.v!==f)return null;if(r.type==="result")return _r(r);if(!Er.has(String(r.type))||Object(r.payload)!==r.payload)return null;return r};var Uo=(e)=>("key"in e)&&("metaKey"in e)&&("ctrlKey"in e),mr=(e)=>(e.metaKey||e.ctrlKey)&&!e.altKey&&!e.shiftKey&&e.key.toLowerCase()==="s";class d extends Error{code;constructor(e,r){super(r);this.name="HostRequestError",this.code=e}}var wo=()=>Promise.reject(new d("BAD_PATH",'Request path must start with "/" and stay on the declared origin.')),Ne=()=>Promise.reject(new d("BAD_PATH",`File path must be 1 to ${Ue} characters without NUL or backslash.`)),Pe=(e)=>{if(e===void 0)return;if(Object(e)!==e||Array.isArray(e)||e.scope!==void 0&&e.scope!=="instance"&&e.scope!=="device")throw new d("HOST_REJECTED",'Storage scope must be "instance" or "device".');return e.scope==="device"?"device":void 0},p=(e)=>(e.value+=1,`oc-${e.value}`),At=(e={})=>{let r=e.target??("window"in globalThis?window:null);if(!r)throw new d("HOST_UNAVAILABLE","No window. connectHost runs in a browser frame.");let n=e.acceptSource??((t)=>t===r.parent),u=e.requestTimeoutMs??lt,i=new Set,_=new Set,b=new Set,R=new Set,m=new Set,S=new Set,N=new Set,B=new Set,W=new Set,I=new Set,se=[],F=null,Y=null,J=new Set,ie=new Set,ee=null,te=null,he=!1,O=new Map,v=new Map,k=new Map,M=!1,l={value:0},a=null,j=null,ae=!1,_e=!1,Xt=null,Ft=(t)=>{if(!t)return null;return{sessionId:t.id,phase:t.busy?"started":"completed"}},V=(t)=>{r.parent.postMessage(t,"*")},Vt=()=>{if(M||r.parent===r||I.size===0||a?.features?.lateGenerateResults!==!0)return;V({channel:E,v:f,type:"generate-late-listen"})},A=(t,o)=>{for(let s of t)try{s(o)}catch(c){console.error(c)}},Bt=(t)=>{if(!(t instanceof MessageEvent))return;if(!n(t.source))return;let o=Ot(t.data);if(!o)return;if(o.type==="workspace"){let c=v.get(o.payload.subscriptionId);if(c)A([c],o.payload.snapshot);return}if(o.type==="shells"){let c=k.get(o.payload.subscriptionId);if(c)A([c],o.payload.snapshot);return}if(o.type==="ready"){if(a=o.payload,j=Ft(o.payload.session),A(i,o.payload),A(_,o.payload.directory),A(b,o.payload.session),j)A(R,j);A(m,o.payload.connection),A(S,o.payload.settings),A(N,o.payload.item),Vt();return}if(o.type==="generate-late"){if(I.size===0)se.push(o.payload);else A(I,o.payload);return}if(o.type==="directory"){if(a)a={...a,directory:o.payload.directory};A(_,o.payload.directory);return}if(o.type==="session"){if(a)a={...a,session:o.payload.session};if(!o.payload.session)j=null;else if(j?.sessionId!==o.payload.session.id)j=Ft(o.payload.session);A(b,o.payload.session);return}if(o.type==="session-lifecycle"){j=o.payload,A(R,o.payload);return}if(o.type==="connection"){if(a)a={...a,connection:o.payload.connection};A(m,o.payload.connection);return}if(o.type==="settings"){if(a)a={...a,settings:o.payload.settings};A(S,o.payload.settings);return}if(o.type==="item"){if(a)a={...a,item:o.payload.item};A(N,o.payload.item);return}if(o.type==="status-control-event"){A(B,o.payload);return}if(o.type==="popover-closed"){A(W,o.payload);return}if(o.type==="action"){let c=(T)=>{if(!M)V({channel:E,v:f,type:"action-result",id:o.id,payload:T})},h=Y;if(!h){c({ok:!1,error:"This extension does not handle background actions."});return}Promise.resolve().then(()=>h(o.payload)).then(()=>c({ok:!0}),(T)=>{let C=(T instanceof Error?T.message:String(T)).trim();c({ok:!1,error:(C||"Action failed.").slice(0,me)})});return}if(o.type==="file-open"){let c=o.payload;if(te&&so(te,c))return;te=c,A(J,o.payload);return}if(o.type==="file-saved"){A(ie,o.payload.version);return}if(o.type==="file-snapshot"){let c=(C)=>{if(!M)V({channel:E,v:f,type:"file-snapshot-result",id:o.id,payload:C})},h=(C)=>c({error:(C.trim()||"Could not read the edited file.").slice(0,me)}),T=ee;if(!T){h("This extension does not edit files.");return}Promise.resolve().then(()=>T(o.payload.purpose)).then((C)=>{if(rt(C)>ye){h(`The file is over ${ye} ${"bytes"in C?"bytes":"characters"}.`);return}if(C.version.length>Re){h(`The snapshot version is over ${Re} characters.`);return}c({snapshot:"bytes"in C?{bytes:C.bytes,version:C.version}:{content:C.content,version:C.version}})},(C)=>h(C instanceof Error?C.message:String(C)));return}if(o.type==="resolve"){let c=(T)=>{V({channel:E,v:f,type:"resolve-result",id:o.id,payload:T})},h=F;if(!h){c({error:"This extension does not resolve commands."});return}Promise.resolve().then(()=>h(o.payload)).then((T)=>c({item:T?le(T):null}),(T)=>{let C=(T instanceof Error?T.message:String(T)).trim();c({error:(C||"Command failed.").slice(0,me)})});return}let s=O.get(o.id);if(!s)return;if(clearTimeout(s.timer),O.delete(o.id),o.ok){s.resolve(o.payload);return}s.reject(new d(o.code,o.error))};r.addEventListener("message",Bt),V({channel:E,v:f,type:"hello"});let P=(t,o=u)=>{if(M||r.parent===r)return Promise.reject(new d("HOST_UNAVAILABLE","No host frame. This page is not in an iframe."));return new Promise((s,c)=>{let h=setTimeout(()=>{O.delete(t.id),c(new d("HOST_TIMEOUT","Host did not answer in time."))},o);O.set(t.id,{resolve:s,reject:c,timer:h}),V(t)})},U=(t)=>P(t).then(()=>{return}),w={channel:E,v:f},Je=(t)=>{if(!M&&r.parent!==r)V(t)},zt=()=>Je({...w,type:"file-save"}),jt=(t)=>{if(!Uo(t)||!mr(t))return;t.preventDefault(),zt()},Kt=(t)=>{if(!Uo(t)||t.key!=="Escape"||a?.surface!=="popover"||!a.popover)return;t.preventDefault(),Qt(a.popover.id,"escape").catch(()=>{return})},xe=()=>{let t=a?.surface==="popover"?a.popover:void 0;if(!t)return;let o=ae||_e;if(Xt===o)return;Xt=o,Zt(t.id,o).catch(()=>{return})},ge=()=>{if(a?.surface!=="popover"||ae)return;ae=!0,xe()},Wt=(t)=>{if(a?.surface!=="popover"||t.relatedTarget!==null||!ae)return;ae=!1,xe()},Yt=()=>{if(a?.surface!=="popover"||_e)return;_e=!0,xe()},Jt=()=>{if(a?.surface!=="popover"||!_e)return;_e=!1,xe()},K=(t,o=1024)=>{if(!t.trim()||t.length>o)throw new d("HOST_REJECTED",`Identity must contain 1 to ${o} characters.`)},Qe=async(t)=>{if(t.kind!=="projects")K(t.projectId);let o=await P({...w,type:"workspace-read",id:p(l),payload:t});if(!o||!("kind"in o)||!("state"in o)||o.kind!==t.kind)throw new d("HOST_REJECTED","Host did not return workspace data.");return o},Ze=async(t,o)=>{if(t.kind!=="projects")K(t.projectId);let s=p(l);v.set(s,o);try{await U({...w,type:"workspace-subscribe",id:p(l),payload:{subscriptionId:s,query:t}})}catch(c){if(v.delete(s),!M)V({...w,type:"workspace-unsubscribe",id:p(l),payload:{subscriptionId:s}});throw c}return()=>{if(!v.delete(s)||M)return;V({...w,type:"workspace-unsubscribe",id:p(l),payload:{subscriptionId:s}})}},ar=async(t,o)=>{if(t.kind==="session")K(t.sessionId);if(t.kind==="project")K(t.projectId);let s=p(l);k.set(s,o);try{await U({...w,type:"shells-subscribe",id:p(l),payload:{subscriptionId:s,scope:t}})}catch(c){if(k.delete(s),!M)V({...w,type:"shells-unsubscribe",id:p(l),payload:{subscriptionId:s}});throw c}return()=>{if(!k.delete(s)||M)return;V({...w,type:"shells-unsubscribe",id:p(l),payload:{subscriptionId:s}})}},be=async(t)=>{if("key"in t&&(t.key.length===0||t.key.length>et))throw new d("HOST_REJECTED","Storage key must contain 1 to 128 characters.");if(t.op==="set"&&!de(t.value))throw new d("HOST_REJECTED","Storage values must be JSON.");if(t.op==="set"&&new TextEncoder().encode(JSON.stringify(t.value)).length>tt)throw new d("HOST_REJECTED","Storage value exceeds 64 KiB.");if(t.scope==="device"&&a?.features?.deviceStorage!==!0)throw new d("UNSUPPORTED","This host does not support device storage.");let o=await P({...w,type:"storage",id:p(l),payload:t});if(!o||!("storage"in o)||o.op!==t.op)throw new d("HOST_REJECTED","Host did not return storage data.");return o},Qt=(t,o)=>a?.features?.popovers!==!0&&!(a?.surface==="popover"&&a.popover?.id===t)?Promise.reject(new d("UNSUPPORTED","This host does not support popovers.")):U({...w,type:"popover-close",id:p(l),payload:o?{id:t,reason:o}:{id:t}}),Zt=(t,o)=>a?.features?.popovers!==!0&&!(a?.surface==="popover"&&a.popover?.id===t)?Promise.reject(new d("UNSUPPORTED","This host does not support popovers.")):U({...w,type:"popover-anchor",id:p(l),payload:{id:t,active:o}});return r.addEventListener("keydown",Kt,!0),r.addEventListener("pointerover",ge),r.addEventListener("pointermove",ge),r.addEventListener("pointerout",Wt),r.addEventListener("focus",Yt),r.addEventListener("blur",Jt),{onAction:(t)=>(Y=t,()=>{if(Y===t)Y=null}),listProjects:async()=>{let t=await Qe({kind:"projects"});if(t.kind!=="projects")throw new d("HOST_REJECTED","Expected projects.");return t},listWorktrees:async(t)=>{let o=await Qe({kind:"worktrees",projectId:t});if(o.kind!=="worktrees")throw new d("HOST_REJECTED","Expected worktrees.");return o},listSessions:async(t)=>{let o=await Qe({kind:"sessions",projectId:t});if(o.kind!=="sessions")throw new d("HOST_REJECTED","Expected sessions.");return o},onProjects:(t)=>Ze({kind:"projects"},(o)=>{if(o.kind==="projects")t(o)}),onWorktrees:(t,o)=>Ze({kind:"worktrees",projectId:t},(s)=>{if(s.kind==="worktrees")o(s)}),onSessions:(t,o)=>Ze({kind:"sessions",projectId:t},(s)=>{if(s.kind==="sessions")o(s)}),onRunningShells:(t,o)=>ar(t,o),readShellOutput:async(t,o)=>{K(t,Oe);let s=o?.cursor;if(s!==void 0&&(!Number.isInteger(s)||s<0))throw new d("HOST_REJECTED","Shell output cursor must be a non-negative integer.");let c=o?.tailBytes;if(c!==void 0&&(!Number.isInteger(c)||c<1||c>Ae))throw new d("HOST_REJECTED",`Shell output tailBytes must be an integer between 1 and ${Ae}.`);let T=await P({...w,type:"shell-output",id:p(l),payload:{shellId:t,cursor:s,tailBytes:c}});if(!T||typeof T.output!=="string"||!Number.isFinite(T.cursor))throw new d("HOST_REJECTED","Host did not return shell output.");return T},stopShell:async(t)=>{if(K(t,Oe),(await P({...w,type:"shell-stop",id:p(l),payload:{shellId:t}}))?.stopped!==!0)throw new d("HOST_REJECTED","Host did not stop the shell.");return{stopped:!0}},openSession:async(t)=>{K(t),await U({...w,type:"open-session",id:p(l),payload:{sessionId:t}})},storage:{get:async(t,o)=>{let s=Pe(o),c={op:"get",key:t};if(s)c.scope=s;let h=await be(c);return h.op==="get"&&h.found?h.value:void 0},set:async(t,o,s)=>{let c=Pe(s),h={op:"set",key:t,value:o};if(c)h.scope=c;await be(h)},delete:async(t,o)=>{let s=Pe(o),c={op:"delete",key:t};if(s)c.scope=s;await be(c)},keys:async(t)=>{let o=Pe(t),s={op:"keys"};if(o)s.scope=o;let c=await be(s);if(c.op!=="keys")throw new d("HOST_REJECTED","Expected storage keys.");return c.keys}},onReady:(t)=>{if(i.add(t),a)t(a);return()=>{i.delete(t)}},onDirectory:(t)=>{if(_.add(t),a)t(a.directory);return()=>{_.delete(t)}},onSession:(t)=>{if(b.add(t),a)t(a.session);return()=>{b.delete(t)}},onSessionLifecycle:(t)=>{if(R.add(t),j)t(j);return()=>{R.delete(t)}},onConnection:(t)=>{if(m.add(t),a)t(a.connection);return()=>{m.delete(t)}},onSettings:(t)=>{if(S.add(t),a)t(a.settings);return()=>{S.delete(t)}},onItem:(t)=>{if(N.add(t),a)t(a.item);return()=>{N.delete(t)}},onStatusControl:(t)=>(B.add(t),()=>{B.delete(t)}),onPopoverClosed:(t)=>(W.add(t),()=>{W.delete(t)}),setStatusControls:(t)=>{if(a?.features?.statusControls!==!0)return Promise.reject(new d("UNSUPPORTED","This host does not support status controls."));if(!no(t))return Promise.reject(new d("HOST_REJECTED","Status controls must have unique bounded ids and valid selected options."));return U({...w,type:"status-controls",id:p(l),payload:{controls:t}})},openPopover:(t)=>{if(a?.features?.popovers!==!0)return Promise.reject(new d("UNSUPPORTED","This host does not support popovers."));if(!st(t))return Promise.reject(new d("HOST_REJECTED","Popover requests need bounded geometry and JSON data."));return U({...w,type:"popover-open",id:p(l),payload:t})},closePopover:Qt,setPopoverAnchorActive:Zt,onResolve:(t)=>(F=t,()=>{if(F===t)F=null}),toast:(t)=>{let o=t.message.trim();if(!o||o.length>ve)return Promise.reject(new d("HOST_REJECTED",`Toast message must contain 1 to ${ve} characters.`));if(t.copy&&t.copy!==!0&&(!t.copy.text.length||t.copy.text.length>ke))return Promise.reject(new d("HOST_REJECTED",`Toast copy text must contain 1 to ${ke} characters.`));return U({channel:E,v:f,type:"toast",id:p(l),payload:{...t,message:o}})},openUrl:(t)=>U({channel:E,v:f,type:"open-url",id:p(l),payload:{url:t}}),openCommit:(t)=>dt(t)?U({channel:E,v:f,type:"open-commit",id:p(l),payload:{sha:t}}):Promise.reject(new d("HOST_REJECTED","Commit id must be 7 to 64 hex characters.")),openSurface:(t)=>U({channel:E,v:f,type:"open-surface",id:p(l),payload:{surfaceId:t}}),writeClipboard:(t)=>U({channel:E,v:f,type:"clipboard-write",id:p(l),payload:{text:t}}),compose:(t)=>U({channel:E,v:f,type:"compose",id:p(l),payload:t}),attach:(t)=>U({channel:E,v:f,type:"attach",id:p(l),payload:le(t)}),startSession:async(t)=>{if(t.projectId!==void 0)K(t.projectId);let o=t.worktree;if(o&&o!==!0)if(o.kind==="existing")K(o.directory);else{if(o.name!==void 0)K(o.name,200);if(o.baseBranch!==void 0)K(o.baseBranch,200)}let s=await P({channel:E,v:f,type:"start-session",id:p(l),payload:Et(t)},e.requestTimeoutMs??180000);if(!at(s))throw new d("HOST_REJECTED","Host did not return a session.");return s},prompt:(t)=>P({channel:E,v:f,type:"prompt",id:p(l),payload:ft(t)}).then((o)=>{if(!ct(o))throw new d("HOST_REJECTED","Host did not return a prompt result.");return o}),sessionLink:(t)=>U({channel:E,v:f,type:"session-link",id:p(l),payload:le(t)}),close:()=>U({channel:E,v:f,type:"close",id:p(l)}),oauthStart:()=>U({channel:E,v:f,type:"oauth-start",id:p(l)}),oauthDisconnect:()=>U({channel:E,v:f,type:"oauth-disconnect",id:p(l)}),request:(t)=>(Le(t.path)?P({channel:E,v:f,type:"request",id:p(l),payload:t}):wo()).then((o)=>{if(!Me(o))throw new d("HOST_REJECTED","Host request result was empty.");return o}),serviceRequest:(t)=>(Le(t.path)?P({channel:E,v:f,type:"service-request",id:p(l),payload:t}):wo()).then((o)=>{if(!Me(o))throw new d("HOST_REJECTED","Host service request result was empty.");return o}),serviceStatus:()=>P({channel:E,v:f,type:"service-status",id:p(l)}).then((t)=>{if(!St(t))throw new d("HOST_REJECTED","Host did not return service status.");return t}),readFile:(t)=>(pe(t)?P({channel:E,v:f,type:"file-read",id:p(l),payload:{path:t}}):Ne()).then((o)=>{if(!Tt(o))throw new d("HOST_REJECTED","Host did not return file content.");return o}),writeFile:(t,o)=>{if(!pe(t))return Ne();if(o.length>we)return Promise.reject(new d("FILE_TOO_LARGE",`Content is over ${we} characters.`));return P({channel:E,v:f,type:"file-write",id:p(l),payload:{path:t,content:o}}).then((s)=>{if(!ht(s))throw new d("HOST_REJECTED","Host did not confirm the write.");return s})},listDir:(t)=>(pe(t)?P({channel:E,v:f,type:"file-list",id:p(l),payload:{path:t}}):Ne()).then((o)=>{if(!xt(o))throw new d("HOST_REJECTED","Host did not return directory entries.");return o}),stat:(t)=>(pe(t)?P({channel:E,v:f,type:"file-stat",id:p(l),payload:{path:t}}):Ne()).then((o)=>{if(!gt(o))throw new d("HOST_REJECTED","Host did not return file status.");return o}),generate:(t)=>{let o=t.prompt.trim(),s=t.system?.trim();if(o.length===0||o.length>Ce)return Promise.reject(new d("HOST_REJECTED",`Prompt must be 1 to ${Ce} characters.`));if(s!==void 0&&(s.length===0||s.length>Ie))return Promise.reject(new d("HOST_REJECTED",`System prompt must be 1 to ${Ie} characters.`));let c=t.maxOutputTokens===void 0?void 0:Math.min(pt,Math.max(1,Math.floor(t.maxOutputTokens)));if(c!==void 0&&!Number.isFinite(c))return Promise.reject(new d("HOST_REJECTED","maxOutputTokens must be a number."));let h={prompt:o};if(s!==void 0)h.system=s;if(c!==void 0)h.maxOutputTokens=c;return P({channel:E,v:f,type:"generate",id:p(l),payload:h},e.requestTimeoutMs??ut).then((T)=>{if(!bt(T))throw new d("HOST_REJECTED","Host did not return generated text.");return T})},onLateGenerateResult:(t)=>{I.add(t);for(let o of se.splice(0))A([t],o);return Vt(),()=>{I.delete(t)}},setBadge:(t)=>U({channel:E,v:f,type:"badge",id:p(l),payload:{count:_t(t)}}),setHeight:(t)=>U({channel:E,v:f,type:"resize",id:p(l),payload:{height:mt(t)}}),onFileOpen:(t)=>{if(J.add(t),!he)he=!0,r.addEventListener("keydown",jt,!0);if(te)t(te);return()=>{J.delete(t)}},onFileSnapshot:(t)=>(ee=t,()=>{if(ee===t)ee=null}),onFileSaved:(t)=>(ie.add(t),()=>{ie.delete(t)}),reportFileChange:(t)=>Je({...w,type:"file-change",payload:{dirty:t.dirty,edited:t.edited}}),requestFileSave:zt,reportFileUnsupported:()=>Je({...w,type:"file-unsupported"}),dispose:()=>{for(let t of v.keys())V({...w,type:"workspace-unsubscribe",id:p(l),payload:{subscriptionId:t}});v.clear();for(let t of k.keys())V({...w,type:"shells-unsubscribe",id:p(l),payload:{subscriptionId:t}});if(k.clear(),M=!0,F=null,Y=null,ee=null,J.clear(),ie.clear(),he)r.removeEventListener("keydown",jt,!0);r.removeEventListener("message",Bt),r.removeEventListener("keydown",Kt,!0),r.removeEventListener("pointerover",ge),r.removeEventListener("pointermove",ge),r.removeEventListener("pointerout",Wt),r.removeEventListener("focus",Yt),r.removeEventListener("blur",Jt);for(let t of O.values())clearTimeout(t.timer),t.reject(new d("HOST_UNAVAILABLE","Host client was disposed."));O.clear(),i.clear(),_.clear(),b.clear(),R.clear(),m.clear(),S.clear(),N.clear(),B.clear(),W.clear(),I.clear(),se.length=0}}};var Co=["browser.open","browser.snapshot","browser.click","browser.type","browser.select","browser.scroll","browser.back","browser.forward","browser.inspect","browser.capture","browser.resize","browser.close"];var rn=new Set(Co);var Io=["none","agent","user"];var sn=new Set(Io);var Sr=[["--oc-bg","background"],["--oc-elevated","elevated"],["--oc-fg","foreground"],["--oc-muted","muted"],["--oc-subtle","subtle"],["--oc-border","border"],["--oc-hover","hover"],["--oc-selection","selection"],["--oc-focus","focus"],["--oc-primary","primary"],["--oc-muted-surface","mutedSurface"],["--oc-elevated-fg","elevatedForeground"],["--oc-active","active"],["--oc-selection-fg","selectionForeground"],["--oc-primary-fg","primaryForeground"],["--oc-primary-text","primaryText"],["--oc-success-text","successText"],["--oc-warning-text","warningText"],["--oc-error-text","errorText"],["--oc-info-text","infoText"],["--oc-success","success"],["--oc-warning","warning"],["--oc-error","error"],["--oc-info","info"],["--oc-font","font"],["--oc-mono","mono"],["--oc-radius","radius"],["--surface-background","background"],["--surface-elevated","elevated"],["--surface-foreground","foreground"],["--surface-muted-foreground","muted"],["--surface-subtle","subtle"],["--interactive-border","border"],["--interactive-hover","hover"],["--interactive-selection","selection"],["--interactive-focus-ring","focus"],["--primary","primary"],["--surface-muted","mutedSurface"],["--surface-elevated-foreground","elevatedForeground"],["--interactive-active","active"],["--interactive-selection-foreground","selectionForeground"],["--primary-foreground","primaryForeground"],["--primary-text","primaryText"],["--success-text","successText"],["--warning-text","warningText"],["--error-text","errorText"],["--info-text","infoText"],["--status-success","success"],["--status-warning","warning"],["--status-error","error"],["--status-info","info"],["--font-sans","font"],["--font-mono","mono"],["--radius","radius"]],Tr=[["--oc-syntax-keyword","--syntax-keyword","syntaxKeyword"],["--oc-syntax-string","--syntax-string","syntaxString"],["--oc-syntax-number","--syntax-number","syntaxNumber"],["--oc-syntax-function","--syntax-function","syntaxFunction"],["--oc-syntax-type","--syntax-type","syntaxType"],["--oc-syntax-comment","--syntax-comment","syntaxComment"],["--oc-syntax-variable","--syntax-variable","syntaxVariable"],["--oc-syntax-operator","--syntax-operator","syntaxOperator"]],Lo=(e,r)=>{r.style.colorScheme=e.mode;for(let[n,u]of Sr)r.style.setProperty(n,e.tokens[u]);for(let[n,u,i]of Tr){let _=e.tokens[i]??"";r.style.setProperty(n,_),r.style.setProperty(u,_)}r.style.setProperty("font-family",e.tokens.font),r.style.setProperty("font-size","0.875rem"),r.style.setProperty("line-height","1.45"),r.style.setProperty("color",e.tokens.foreground)},yt=(e,r)=>{if(Lo(e.theme,r),r.dataset)r.dataset.ocSurface=e.surface,r.dataset.ocTheme=e.theme.mode};var hr={"surface-background":"bg","surface-elevated":"elevated","surface-elevated-foreground":"elevated-fg","surface-foreground":"fg","surface-muted-foreground":"muted","surface-muted":"muted-surface","surface-subtle":"subtle","interactive-border":"border","interactive-hover":"hover","interactive-active":"active","interactive-selection":"selection","interactive-selection-foreground":"selection-fg","interactive-focus-ring":"focus",primary:"primary","primary-foreground":"primary-fg","primary-text":"primary-text","success-text":"success-text","warning-text":"warning-text","error-text":"error-text","info-text":"info-text","status-success":"success","status-warning":"warning","status-error":"error","status-info":"info","font-sans":"font","font-mono":"mono",radius:"radius"},g=(e,r)=>`var(--${e}, var(--oc-${hr[e]}, ${r}))`,Z=g("surface-background","transparent"),De=g("surface-elevated","transparent"),ue=g("surface-elevated-foreground","inherit"),z=g("surface-foreground","inherit"),x=g("surface-muted-foreground","gray"),xr=g("surface-muted","transparent"),oe=g("interactive-border","currentColor"),G=g("interactive-hover","transparent"),ce=g("interactive-active","transparent"),Rt=g("interactive-selection","transparent"),vt=g("interactive-selection-foreground","inherit"),Q=g("primary","currentColor"),kt=g("primary-text","inherit"),Ut=g("error-text","inherit"),gr=g("font-sans","inherit"),wt=g("font-mono","monospace"),Do=g("radius","9px"),Ct=`calc(${Do} - 2px)`,Mo=`calc(${Do} - 4px)`,y=(e,r,n="transparent")=>`color-mix(in srgb, ${e} ${r}%, ${n})`,No=`background-image: linear-gradient(${G}, ${G});`,It=(e)=>`box-shadow: inset 0 0 0 1px ${e}, var(--oc-sdk-field-lift);`,Lt="border-color: var(--oc-sdk-edge); box-shadow: var(--oc-sdk-raised-lift);",Po="box-shadow: var(--oc-sdk-lit);",Go=`inset 0 1px 0 0 ${y(z,1.5)}, 0 1px 1px 0 rgb(0 0 0 / 0.28), 0 2px 3px -2px rgb(0 0 0 / 0.2)`,br=`
:root {
  --oc-sdk-edge: ${y(z,10)};
  --oc-sdk-field-bg: ${De};
  --oc-sdk-raised-bg: ${Z};
  --oc-sdk-field-lift: inset 0 1px 2px 0 rgb(0 0 0 / 0.04);
  --oc-sdk-raised-lift: 0 1px 2px 0 rgb(0 0 0 / 0.06);
  --oc-sdk-lit: inset 0 1px 0 0 rgb(255 255 255 / 0.45), 0 1px 2px 0 rgb(0 0 0 / 0.08);
  --oc-sdk-float-edge: rgb(0 0 0 / 0.1);
  --oc-sdk-float: inset 0 1px 0 0 rgb(255 255 255 / 0.8), inset 0 0 0 1px rgb(0 0 0 / 0.04), 0 1px 2px -0.5px rgb(0 0 0 / 0.08), 0 4px 8px -2px rgb(0 0 0 / 0.08), 0 12px 20px -4px rgb(0 0 0 / 0.08);
}
:root[data-oc-theme="dark"] {
  --oc-sdk-edge: ${y(z,6)};
  --oc-sdk-field-bg: ${y(Z,50,De)};
  --oc-sdk-raised-bg: ${De};
  --oc-sdk-field-lift: ${Go};
  --oc-sdk-raised-lift: ${Go};
  --oc-sdk-lit: inset 0 1px 0 0 ${y(z,1.5)}, 0 1px 1px 0 rgb(0 0 0 / 0.28), 0 2px 3px -2px rgb(0 0 0 / 0.2);
  --oc-sdk-float-edge: rgb(0 0 0 / 0.36);
  --oc-sdk-float: inset 0 1px 0 0 rgb(255 255 255 / 0.06), inset 0 0 0 1px rgb(255 255 255 / 0.08), 0 1px 1px -0.5px rgb(0 0 0 / 0.22), 0 3px 3px -1.5px rgb(0 0 0 / 0.2), 0 6px 6px -3px rgb(0 0 0 / 0.16);
}`,Ge=(e)=>{let r=g(`status-${e}`,"currentColor");return`
.oc-sdk[data-tone="${e}"], .oc-sdk [data-tone="${e}"] { --oc-sdk-tone: ${r}; --oc-sdk-tone-text: ${g(`${e}-text`,"inherit")}; }`},Or=`
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
`,$o=`${br}
.oc-sdk { color: ${z}; font-family: ${gr}; }
.oc-sdk :focus-visible, .oc-sdk:focus-visible { outline: none; }
.oc-sdk :where(button, a[href], [role="button"], [role="tab"], [role="option"]):focus-visible, button.oc-sdk:focus-visible { ${No} }
.oc-sdk-mono { font-family: ${wt}; }
.oc-sdk-muted { color: ${x}; }
${Ge("success")}${Ge("warning")}${Ge("error")}${Ge("info")}
.oc-sdk[data-tone="primary"], .oc-sdk [data-tone="primary"] { --oc-sdk-tone: ${Q}; --oc-sdk-tone-text: ${kt}; }

.oc-sdk-btn { border-radius: ${Ct}; transition: background 150ms ease-out, color 150ms ease-out; }
.oc-sdk-btn[data-size="xs"] { border-radius: ${Mo}; }
.oc-sdk-btn[data-variant="default"] { color: ${kt}; background: ${y(Q,10,Z)}; border-color: ${y(Q,12)}; ${Po} }
.oc-sdk-btn[data-variant="default"]:hover { background: ${y(Q,16,Z)}; }
.oc-sdk-btn[data-variant="default"]:active { background: ${y(Q,22,Z)}; box-shadow: none; }
.oc-sdk-btn[data-variant="secondary"] { background: ${xr}; color: var(--oc-fg); }
.oc-sdk-btn[data-variant="secondary"]:hover { background-image: linear-gradient(${G}, ${G}); }
.oc-sdk-btn[data-variant="secondary"]:active { background-image: linear-gradient(${ce}, ${ce}); }
.oc-sdk-btn[data-variant="outline"] { background: var(--oc-sdk-raised-bg); color: ${ue}; ${Lt} }
.oc-sdk-btn[data-variant="outline"]:hover { background-image: linear-gradient(${G}, ${G}); }
.oc-sdk-btn[data-variant="outline"]:active { background-image: linear-gradient(${ce}, ${ce}); box-shadow: none; }
.oc-sdk-btn[data-variant="ghost"] { background: transparent; }
.oc-sdk-btn[data-variant="ghost"]:hover { background: ${G}; }
.oc-sdk-btn[data-variant="ghost"]:active { background: ${ce}; }
.oc-sdk-btn[data-variant="destructive"] { --oc-sdk-tone: ${g("status-error","red")}; color: ${Ut}; background: ${y("var(--oc-sdk-tone)",7,Z)}; border-color: ${y("var(--oc-sdk-tone)",12)}; ${Po} }
.oc-sdk-btn[data-variant="destructive"]:hover { background: ${y("var(--oc-sdk-tone)",9,Z)}; }
.oc-sdk-btn[data-variant="destructive"]:active { background: ${y("var(--oc-sdk-tone)",11,Z)}; box-shadow: none; }

.oc-sdk-field-note { color: ${x}; }
.oc-sdk-field[data-invalid="true"] .oc-sdk-field-note { color: ${Ut}; }
.oc-sdk-input { border-radius: ${Ct}; background: var(--oc-sdk-field-bg); color: ${ue}; ${It("var(--oc-sdk-edge)")} transition: background 150ms ease-out; }
.oc-sdk-input::placeholder { color: ${x}; }
.oc-sdk-input:hover:not(:focus) { background-image: linear-gradient(${G}, ${G}); }
.oc-sdk-input:focus, .oc-sdk-input:focus-visible { ${It(y(z,26))} }
.oc-sdk-field[data-invalid="true"] .oc-sdk-input, .oc-sdk-field[data-invalid="true"] .oc-sdk-input:focus { ${It(g("status-error","red"))} }
.oc-sdk-input[data-mono="true"] { font-family: ${wt}; }

.oc-sdk-search-icon { color: ${x}; }
.oc-sdk-search[data-active="true"] .oc-sdk-search-icon { color: ${Q}; }
.oc-sdk-search-clear { border-radius: ${Mo}; color: ${x}; }
.oc-sdk-search-clear:hover { background: ${G}; color: ${z}; }

.oc-sdk-trigger { border-radius: ${Ct}; background: var(--oc-sdk-raised-bg); color: ${ue}; ${Lt} transition: background 150ms ease-out; }
.oc-sdk-trigger:hover { background-image: linear-gradient(${G}, ${G}); }
.oc-sdk-trigger[aria-expanded="true"] { background-image: linear-gradient(${ce}, ${ce}); }
.oc-sdk-trigger-value[data-empty="true"] { color: ${x}; }
.oc-sdk-trigger-chevron { color: ${x}; }
/* The app's dropdown light: lit top, hairline rings and a layered shadow. Its outer ring is the border, over the page like the app's. */
.oc-sdk-popup { --surface-foreground: ${ue}; border-color: var(--oc-sdk-float-edge); border-radius: 12px; background: ${De}; background-clip: padding-box; color: ${ue}; box-shadow: var(--oc-sdk-float); }
.oc-sdk-option { border-radius: 8px; }
.oc-sdk-option[data-active="true"] { background: ${G}; }
/* A selected option shows a check mark in the text colour, like the app's own pickers. Options without the mark come
   from bundles built before it existed and keep the selection fill as their only sign of the choice. */
.oc-sdk-option[aria-selected="true"]:not([data-mark]) { background: ${Rt}; color: ${vt}; }
.oc-sdk-option-check { color: ${z}; }
.oc-sdk-option[data-destructive="true"] { color: ${Ut}; }
.oc-sdk-option[data-destructive="true"][data-active="true"] { background: ${y(g("status-error","red"),10)}; }
.oc-sdk-option-hint { color: ${x}; }
.oc-sdk-popup-empty { color: ${x}; }

/* Checked stays neutral: the mark carries the state, and the primary colour stays with primary actions. */
.oc-sdk-check-box { border-color: ${oe}; border-radius: 4px; color: ${z}; transition: border-color 150ms ease-out; }
.oc-sdk-check[aria-checked="true"] .oc-sdk-check-box { border-color: ${y(z,60,oe)}; }
.oc-sdk-check-thumb { border-radius: 9999px; background: ${oe}; transition: background 150ms ease-out; }
.oc-sdk-check-thumb::after { border-radius: 9999px; background: ${Z}; transition: transform 150ms ease-out; }
.oc-sdk-check[aria-checked="true"] .oc-sdk-check-thumb { background: ${Q}; }
.oc-sdk-check[aria-checked="true"] .oc-sdk-check-thumb::after { transform: translateX(16px); }
.oc-sdk-check:focus-visible { box-shadow: none; }
.oc-sdk-check:focus-visible .oc-sdk-check-box, .oc-sdk-check:focus-visible .oc-sdk-check-thumb { ${No} }
.oc-sdk-check-desc { color: ${x}; }

.oc-sdk-tabs { border-radius: 10px; }
.oc-sdk-tabs[data-track="true"] { background: ${y(z,4)}; box-shadow: inset 0 1px 2px 0 rgb(0 0 0 / 0.16); }
.oc-sdk-tab { border-radius: 8px; color: ${x}; transition: color 150ms ease-out, background 150ms ease-out; }
.oc-sdk-tab:hover { color: ${z}; }
.oc-sdk-tab[aria-selected="true"] { color: ${vt}; background: ${Rt}; border-color: ${oe}; }
.oc-sdk-tabs[data-track="true"] .oc-sdk-tab[aria-selected="true"] { color: ${ue}; background: var(--oc-sdk-raised-bg); ${Lt} }
.oc-sdk-tab-count { color: ${x}; }

.oc-sdk-badge { border-radius: 9999px; background: ${G}; color: ${x}; }
.oc-sdk-badge[data-tone] { color: var(--oc-sdk-tone-text, var(--oc-sdk-tone)); background: ${y("var(--oc-sdk-tone)",15)}; }

.oc-sdk-row { border-radius: 6px; transition: background 120ms ease-out; }
.oc-sdk-row:hover, .oc-sdk-row[data-active="true"] { background: ${G}; }
.oc-sdk-row[aria-selected="true"] { background: ${Rt}; color: ${vt}; }
.oc-sdk-row-lead { font-family: ${wt}; color: ${x}; }
.oc-sdk-row-sub { color: ${x}; }
.oc-sdk-row-meta { color: ${x}; }
.oc-sdk-row[aria-selected="true"] .oc-sdk-row-lead, .oc-sdk-row[aria-selected="true"] .oc-sdk-row-sub, .oc-sdk-row[aria-selected="true"] .oc-sdk-row-meta { color: inherit; opacity: .75; }
.oc-sdk-list-empty { color: ${x}; }

.oc-sdk-empty-body { color: ${x}; }

.oc-sdk-spinner { color: ${x}; }
.oc-sdk-spinner-ring { border-color: ${oe}; border-top-color: ${Q}; border-radius: 9999px; }

/* Set apart by its tint alone, like the app's banners. */
.oc-sdk-banner { border-color: transparent; border-radius: 8px; background: ${y("var(--oc-sdk-tone)",10)}; }
.oc-sdk-banner-title { color: var(--oc-sdk-tone-text, var(--oc-sdk-tone)); }
.oc-sdk-banner-body { color: ${x}; }

.oc-sdk-separator { color: ${x}; }
.oc-sdk-separator::before, .oc-sdk-separator::after { background: ${y(oe,40)}; }

.oc-sdk-progress-label { color: ${x}; }
.oc-sdk-progress-track { border-radius: 9999px; background: ${oe}; }
.oc-sdk-progress-fill { border-radius: 9999px; background: var(--oc-sdk-tone, ${Q}); }

.oc-sdk-text a { color: ${kt}; text-decoration: underline; text-underline-offset: 2px; }
.oc-sdk-text img { border-radius: 8px; border: 1px solid ${y(oe,60)}; }
`,D=`
${qe}
${Or}
${$o}`;var kr=0,re=(e,r)=>{let n=document.createElementNS("http://www.w3.org/2000/svg",e);for(let[u,i]of Object.entries(r))n.setAttribute(u,String(i));return n},Ho=(e)=>{let r=document.createElement("div");r.className="chart",r.style.height=`${e.height}px`;let n=e.height,u=re("svg",{viewBox:`0 0 300 ${n}`,preserveAspectRatio:"none","aria-hidden":"true"}),i=`fill-${++kr}`,_=re("defs",{}),b=re("linearGradient",{id:i,x1:0,x2:0,y1:0,y2:1});b.append(re("stop",{offset:"0%","stop-color":e.color,"stop-opacity":0.32}),re("stop",{offset:"100%","stop-color":e.color,"stop-opacity":0.02})),_.append(b);let R=re("path",{d:"",class:"chart-grid"}),m=re("path",{d:"",fill:`url(#${i})`}),S=re("path",{d:"",fill:"none",stroke:e.color,"stroke-width":1.5,"vector-effect":"non-scaling-stroke","stroke-linejoin":"round"});u.append(_,R,m,S);let N=document.createElement("div");N.className="chart-cursor";let B=document.createElement("div");B.className="chart-dot",B.style.background=e.color;let W=document.createElement("div");W.className="chart-tip",r.append(u,N,B,W);let I=[],se=1,F=null,Y=null,J=(O,v)=>(e.capacity-v+O)/Math.max(1,e.capacity-1)*300,ie=(O)=>n-1-Math.min(O,se)/se*(n-1-2),ee=()=>{let O=F===null?void 0:I[F];if(F===null||O===void 0){r.classList.remove("hovering");return}r.classList.add("hovering");let v=r.getBoundingClientRect(),k=J(F,I.length)/300*v.width,M=ie(O)/n*v.height;N.style.transform=`translateX(${k}px)`,B.style.transform=`translate(${k}px, ${M}px)`;let l=(I.length-1-F)*e.intervalSeconds;W.textContent=`${e.format(O)} · ${l===0?"now":`${l} s ago`}`;let a=k>v.width/2;W.style.left=a?"":`${k+8}px`,W.style.right=a?`${v.width-k+8}px`:""},te=(O)=>{if(I.length===0)return;let v=r.getBoundingClientRect(),k=(O-v.left)/v.width*(e.capacity-1),M=Math.round(k-(e.capacity-I.length));F=Math.min(I.length-1,Math.max(0,M)),ee()};return r.addEventListener("pointermove",(O)=>{Y=O.clientX,te(O.clientX)}),r.addEventListener("pointerleave",()=>{Y=null,F=null,ee()}),{element:r,update:(O,v)=>{if(I=O,se=v>0?v:1,R.setAttribute("d",[0.25,0.5,0.75].map((k)=>`M0 ${n*k} H300`).join(" ")),I.length===0)m.setAttribute("d",""),S.setAttribute("d","");else{let k=I.map((j,ae)=>`${J(ae,I.length).toFixed(2)} ${ie(j).toFixed(2)}`),M=I.length===1,l=M?`M${J(0,1)-2} ${k[0]?.split(" ")[1]} L${k[0]}`:`M${k.join(" L")}`;S.setAttribute("d",l);let a=M?J(0,1)-2:J(0,I.length);m.setAttribute("d",`${l} L300 ${n} L${a.toFixed(2)} ${n} Z`)}if(Y!==null)te(Y)}}};var L=(e,r="",n="",u=[])=>{let i=document.createElement(e);if(r)i.className=r;if(n)i.textContent=n;if(u.length>0)i.append(...u);return i},fe=(e,r)=>{if(e.textContent!==r)e.textContent=r},Xo=(e,r,n,u,i,_=0)=>{let b=new Map;for(let m of r){let S=n(m);for(let B=1;b.has(S);B+=1)S=`${n(m)}\x01${B}`;let N=i.get(S);if(N)N.update(m);b.set(S,N??u(m))}for(let[m,S]of i)if(b.get(m)!==S)S.element.remove();i.clear();let R=_;for(let[m,S]of b){i.set(m,S);let N=e.children[R]??null;if(N!==S.element)e.insertBefore(S.element,N);R+=1}};var Gt=5000,Fo={"needs-approval":"Allow the local service for Resource Monitor in Settings → Extensions.",paused:"Resource Monitor is paused in Settings → Extensions.","service-failed":"The monitoring service stopped. It restarts on the next refresh.",unreachable:"Could not reach the monitoring service.","bad-answer":"The monitoring service answered with something unexpected."},Ve=(e)=>typeof e==="object"&&e!==null,Ur=(e)=>Ve(e)&&typeof e.at==="number"&&Ve(e.system)&&Ve(e.app)&&Array.isArray(e.app.groups)&&Array.isArray(e.servers)&&Array.isArray(e.outside)&&Ve(e.history),wr=(e)=>{if(!(e instanceof d))return"unreachable";if(e.code==="NO_SERVICE"||e.code==="NOT_GRANTED")return"needs-approval";if(e.code==="DISABLED")return"paused";if(e.code==="SERVICE_FAILED")return"service-failed";return"unreachable"};var Vo=(e,r)=>{let n=L("button","port",`:${r}`);return n.type="button",n.title=`Open http://localhost:${r}`,n.addEventListener("click",(u)=>{u.stopPropagation(),e.openUrl(`http://localhost:${r}`).catch(()=>{return})}),n},Pt=(e)=>!document.hidden&&e.getBoundingClientRect().width>0,Bo=(e,r,n,u)=>{let i=!1,_=async()=>{if(i||!Pt(r))return;i=!0;try{let m=await e.serviceRequest({method:"GET",path:"/snapshot"}),S;try{S=JSON.parse(m.body)}catch{S=null}if(m.status===200&&Ur(S))n(S);else u(m.status===200?"bad-answer":"service-failed")}catch(m){u(wr(m))}finally{i=!1}};_(),setInterval(()=>{_()},Gt);let b=Pt(r),R=()=>{let m=Pt(r);if(m&&!b)_();b=m};return document.addEventListener("visibilitychange",R),new ResizeObserver(R).observe(document.documentElement),{refresh:()=>{_()}}};var Dt="en",zo=(e)=>{try{Dt=Intl.NumberFormat.supportedLocalesOf(e)[0]??"en"}catch{Dt="en"}},jo=(e,r)=>new Intl.NumberFormat(Dt,{minimumFractionDigits:r,maximumFractionDigits:r}).format(e),Se=(e)=>{let r=["B","KB","MB","GB","TB"],n=Math.max(0,e),u=0;while(n>=1024&&u<r.length-1)n/=1024,u+=1;let i=u>=3&&n<100?1:0;return`${jo(n,i)} ${r[u]}`},$t=(e)=>{if(e===null)return"–";if(e>0&&e<0.01)return"<0.01%";return`${jo(e,e>0&&e<1?2:e<10?1:0)}%`};var Be={cpu:"var(--oc-info)",memory:"var(--oc-success)",app:"var(--oc-primary)",opencode:"color-mix(in srgb, var(--oc-primary) 50%, var(--oc-fg))",terminals:"var(--oc-muted)"};var Ko=36;var Wo=`
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
`;var Yo=`
  html, body { overflow: hidden; }
  #root { display: flex; flex-direction: column; gap: 6px; padding: 2px 0 4px; }
  .line { display: grid; grid-template-columns: 84px minmax(0, 1fr) auto; align-items: center; gap: 8px; min-height: 18px; }
  .line .what { color: var(--oc-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .line .value { text-align: right; white-space: nowrap; }
  .meter { position: relative; height: 4px; border-radius: 2px; background: color-mix(in srgb, var(--oc-fg) 8%, transparent); overflow: hidden; }
  .meter > span { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 2px; }
  .ports { display: flex; flex-wrap: wrap; gap: 4px; min-width: 0; }
  .note { color: var(--oc-muted); }
  .note.error { color: var(--oc-error-text, var(--oc-fg)); }
  [hidden] { display: none !important; }
`;var ze=At(),Te=document.querySelector("#root");if(!Te)throw Error("Missing #root");var Zo=document.createElement("style");Zo.textContent=Wo+Yo;document.head.append(Zo);var qo=(e)=>{let r=L("span");return r.style.background=e,r.style.width="0%",{element:L("div","meter","",[r]),set:(n)=>{r.style.width=`${Math.min(100,Math.max(0,n))}%`}}},er=Ho({color:Be.app,height:18,capacity:Ko,format:Se,intervalSeconds:Gt/1000}),Ht=L("span","value num","–");Ht.title="Memory and CPU of OpenDiscovery, OpenDiscovery Engine, and everything they started. CPU is a percentage of total machine capacity: all logical cores together are 100%, on the same scale as the CPU line.";var tr=qo(Be.cpu),or=L("span","value num","–"),rr=qo(Be.memory),nr=L("span","value num","–"),sr=L("div","ports"),ir=L("span","value num"),je=L("div","line","",[L("span","what","OpenDiscovery"),er.element,Ht]),Ke=L("div","line","",[L("span","what","CPU"),tr.element,or]),We=L("div","line","",[L("span","what","Memory"),rr.element,nr]),Ye=L("div","line","",[L("span","what","Dev servers"),sr,ir]);Ye.hidden=!0;var ne=L("div","note","Reading…");Te.append(ne,je,Ke,We,Ye);for(let e of[je,Ke,We])e.hidden=!0;var Cr=new Map,Ir=(e)=>({element:Vo(ze,e),update:()=>{return}}),Lr=(e)=>{let{system:r,app:n}=e,u=e.warnings.includes("processes-unavailable");if(ne.hidden=!u,ne.className!=="note error")ne.className="note error";fe(ne,u?"Could not read the process list; showing system totals only.":"");for(let _ of[Ke,We])_.hidden=!1;je.hidden=u,fe(Ht,`${Se(n.memory)} · ${$t(n.cpu)}`),er.update(e.history.app.memory,Math.max(n.memory,...e.history.app.memory)*1.15),tr.set(r.cpu??0),fe(or,$t(r.cpu)),rr.set(r.memoryUsed/Math.max(1,r.memoryTotal)*100),fe(nr,`${Se(r.memoryUsed)} / ${Se(r.memoryTotal)}`);let i=[...new Set(e.servers.flatMap((_)=>_.ports))].sort((_,b)=>_-b);Ye.hidden=i.length===0||u,Xo(sr,i.slice(0,6),String,Ir,Cr),fe(ir,i.length>6?`+${i.length-6}`:"")},Jo=-1;new ResizeObserver(()=>{let e=Math.ceil(Te.getBoundingClientRect().height);if(e===Jo)return;Jo=e,ze.setHeight(e).catch(()=>{return})}).observe(Te);var Qo=!1;ze.onReady((e)=>{if(yt(e,document.documentElement),zo(e.locale),Qo)return;Qo=!0,Bo(ze,Te,Lr,(r)=>{ne.hidden=!1,ne.className="note error",ne.textContent=Fo[r];for(let n of[je,Ke,We,Ye])n.hidden=!0})});})();
