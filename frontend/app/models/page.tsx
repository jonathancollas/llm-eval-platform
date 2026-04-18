"use client";
import { useState, useCallback, useMemo, memo, useRef, useEffect } from "react";
import { List, type ListImperativeAPI, type RowComponentProps } from "react-window";
import { modelsApi, ollamaApi } from "@/lib/api";
import { API_BASE, OLLAMA_BASE_URL } from "@/lib/config";
import type { LLMModel, ModelProvider } from "@/lib/api";
import { useModelsFull } from "@/lib/useApi";
import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/Badge";
import { EmptyState } from "@/components/EmptyState";
import { Spinner } from "@/components/Spinner";
import { ModelCatalogModal } from "@/components/ModelCatalogModal";
import { AppErrorBoundary } from "@/components/AppErrorBoundary";
import { providerColor } from "@/lib/utils";
import {
  Plus, Zap, Eye, Wrench, Brain, CheckCircle2, XCircle,
  ChevronDown, ChevronUp, Trash2, Search, ExternalLink, Shield,
  Download, HardDrive, Lock, Unlock,
} from "lucide-react";

const PROVIDERS: ModelProvider[] = ["openai","anthropic","mistral","groq","ollama","vllm","custom"];
const PROVIDER_LABELS: Record<string,string> = {
  openai:"OpenAI",anthropic:"Anthropic",mistral:"Mistral",
  groq:"Groq",ollama:"Ollama (local)",vllm:"vLLM (local)",custom:"Custom / OpenRouter",
};
const CARD_H = 80; // collapsed height px

// ── Debounce ──────────────────────────────────────────────────────────────────
function useDebounce<T>(value: T, delay = 250): T {
  const [d, setD] = useState<T>(value);
  useEffect(() => { const t = setTimeout(() => setD(value), delay); return () => clearTimeout(t); }, [value, delay]);
  return d;
}

// ── Filters ───────────────────────────────────────────────────────────────────
interface Filters { search:string; onlyFree:boolean; onlyVision:boolean; onlyTools:boolean; onlyReasoning:boolean; }
const F0: Filters = { search:"", onlyFree:false, onlyVision:false, onlyTools:false, onlyReasoning:false };

function applyFilters(models: LLMModel[], f: Filters, q: string): LLMModel[] {
  return models.filter(m => {
    if (q && !m.name.toLowerCase().includes(q) && !m.model_id.toLowerCase().includes(q)) return false;
    if (f.onlyFree && !m.is_free) return false;
    if (f.onlyVision && !m.supports_vision) return false;
    if (f.onlyTools && !m.supports_tools) return false;
    if (f.onlyReasoning && !m.supports_reasoning) return false;
    return true;
  });
}

// ── Sub-components (memoized) ─────────────────────────────────────────────────
const AccessTypeBadge = memo(function AccessTypeBadge({ model }: { model: LLMModel }) {
  if (model.provider === "ollama") return <span className="inline-flex items-center gap-0.5 text-[9px] px-1.5 py-0.5 rounded font-bold bg-purple-100 text-purple-700 border border-purple-200"><HardDrive size={8}/>LOCAL</span>;
  if (model.provider === "vllm") return <span className="inline-flex items-center gap-0.5 text-[9px] px-1.5 py-0.5 rounded font-bold bg-indigo-100 text-indigo-700 border border-indigo-200"><HardDrive size={8}/>LOCAL</span>;
  if ((model as any).is_open_weight) return <span className="inline-flex items-center gap-0.5 text-[9px] px-1.5 py-0.5 rounded font-bold bg-emerald-100 text-emerald-700 border border-emerald-200"><Unlock size={8}/>OPEN WEIGHT</span>;
  return <span className="inline-flex items-center gap-0.5 text-[9px] px-1.5 py-0.5 rounded font-bold bg-slate-100 text-slate-500 border border-slate-200"><Lock size={8}/>API ONLY</span>;
});

const OllamaPullButton = memo(function OllamaPullButton({ modelId }: { modelId: string }) {
  const [st, setSt] = useState<"idle"|"pulling"|"done"|"error">("idle");
  const [prog, setProg] = useState("");
  const pull = useCallback(async () => {
    setSt("pulling"); setProg("Connexion…");
    try {
      const res = await fetch(`${OLLAMA_BASE_URL}/api/pull`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:modelId,stream:true})});
      if(!res.ok) throw new Error(`Ollama ${res.status}`);
      const reader = res.body?.getReader(); if(!reader) throw new Error("No body");
      const dec = new TextDecoder();
      for(;;){const{done,value}=await reader.read();if(done)break;for(const l of dec.decode(value).split("\n").filter(Boolean)){try{const o=JSON.parse(l);if(o.status)setProg(o.status);if(o.completed&&o.total)setProg(`${Math.round(o.completed/o.total*100)}%`);}catch{}}}
      setSt("done"); setProg("✓");
    } catch(e:any){setSt("error");setProg(String(e).slice(0,60));}
  },[modelId]);
  if(st==="done") return <span className="flex items-center gap-1 text-xs text-green-600"><CheckCircle2 size={12}/>Installed</span>;
  return <div className="flex items-center gap-2"><button onClick={pull} disabled={st==="pulling"} className="flex items-center gap-1 text-xs px-2.5 py-1.5 border border-purple-200 rounded-lg hover:bg-purple-50 text-purple-700 disabled:opacity-50">{st==="pulling"?<Spinner size={11}/>:<Download size={11}/>}{st==="pulling"?"Pulling…":"⬇ Local"}</button>{st==="pulling"&&<span className="text-[10px] text-slate-400">{prog}</span>}{st==="error"&&<span className="text-[10px] text-red-500">Ollama not running</span>}</div>;
});

const ModelDetail = memo(function ModelDetail({ m }: { m: LLMModel }) {
  const created = m.model_created_at ? new Date(m.model_created_at*1000).toLocaleDateString("en-US",{year:"numeric",month:"short"}) : null;
  const canPull = (m as any).is_open_weight && m.provider !== "ollama";
  return (
    <div className="border-t border-slate-100 px-5 py-4 bg-slate-50 text-xs text-slate-600 space-y-3">
      <div className="grid grid-cols-3 gap-3">
        {[["Input",m.is_free?"🆓 Free":`$${m.cost_input_per_1k.toFixed(4)}/1k`],["Output",m.is_free?"🆓 Free":`$${m.cost_output_per_1k.toFixed(4)}/1k`],["Context",`${(m.context_length/1000).toFixed(0)}k`]].map(([l,v])=>(
          <div key={l} className="bg-white rounded-lg p-2.5 border border-slate-100"><div className="text-slate-400 mb-0.5">{l}</div><div className="font-medium text-slate-800">{v}</div></div>
        ))}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {m.supports_vision&&<Badge className="bg-purple-50 text-purple-700 border border-purple-100"><Eye size={10} className="inline mr-1"/>Vision</Badge>}
        {m.supports_tools&&<Badge className="bg-blue-50 text-blue-700 border border-blue-100"><Wrench size={10} className="inline mr-1"/>Tools</Badge>}
        {m.supports_reasoning&&<Badge className="bg-amber-50 text-amber-700 border border-amber-100"><Brain size={10} className="inline mr-1"/>Reasoning</Badge>}
        {m.is_moderated&&<Badge className="bg-red-50 text-red-600 border border-red-100"><Shield size={10} className="inline mr-1"/>Moderated</Badge>}
      </div>
      {canPull&&<div className="bg-purple-50 border border-purple-100 rounded-lg p-3"><div className="text-slate-600 font-medium mb-2 flex items-center gap-1.5"><HardDrive size={12}/>Download locally</div><OllamaPullButton modelId={m.model_id}/></div>}
      <div className="grid grid-cols-2 gap-x-6 gap-y-1">
        {m.tokenizer&&<div><span className="text-slate-400">Tokenizer:</span> <span className="font-mono">{m.tokenizer}</span></div>}
        {m.instruct_type&&<div><span className="text-slate-400">Format:</span> <span className="font-mono">{m.instruct_type}</span></div>}
        {created&&<div><span className="text-slate-400">Sortie:</span> {created}</div>}
      </div>
      {m.tags.length>0&&<div className="flex flex-wrap gap-1">{m.tags.map(t=><Badge key={t} className="bg-white border border-slate-200 text-slate-500">{t}</Badge>)}</div>}
      {m.notes&&!m.notes.startsWith("Via OpenRouter")&&<p className="text-slate-500 italic">{m.notes}</p>}
      <div className="flex gap-3 pt-1">
        {m.hugging_face_id&&<a href={`https://huggingface.co/${m.hugging_face_id}`} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1 text-xs text-blue-600 hover:underline"><ExternalLink size={11}/>HuggingFace</a>}
        <a href={`https://openrouter.ai/models/${m.model_id}`} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1 text-xs text-blue-600 hover:underline"><ExternalLink size={11}/>OpenRouter</a>
      </div>
    </div>
  );
});

// ── ModelCard — React.memo prevents re-render unless own props change ──────────
interface CardProps { model:LLMModel; expanded:boolean; testResult:any; testing:boolean; onToggle:(id:number)=>void; onTest:(id:number)=>void; onDelete:(id:number)=>void; }
const ModelCard = memo(function ModelCard({model:m,expanded,testResult,testing,onToggle,onTest,onDelete}:CardProps){
  return (
    <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
      <div className="flex items-center gap-4 px-5 py-4 cursor-pointer hover:bg-slate-50 transition-colors" onClick={()=>onToggle(m.id)}>
        {m.is_free&&<span className="text-xs font-bold text-green-600 bg-green-50 border border-green-200 px-2 py-0.5 rounded-full shrink-0">FREE</span>}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-0.5 flex-wrap">
            <span className="font-medium text-slate-900">{m.name}</span>
            <Badge className={providerColor(m.provider)}>{m.provider}</Badge>
            <AccessTypeBadge model={m}/>
            {m.supports_vision&&<Badge className="bg-purple-50 text-purple-600 border border-purple-100"><Eye size={9} className="inline mr-0.5"/>Vision</Badge>}
            {m.supports_tools&&<Badge className="bg-blue-50 text-blue-600 border border-blue-100"><Wrench size={9} className="inline mr-0.5"/>Tools</Badge>}
            {m.supports_reasoning&&<Badge className="bg-amber-50 text-amber-600 border border-amber-100"><Brain size={9} className="inline mr-0.5"/>Reasoning</Badge>}
          </div>
          <div className="flex gap-3 text-xs text-slate-400">
            <span className="font-mono truncate max-w-48">{m.model_id}</span>
            <span>{(m.context_length/1000).toFixed(0)}k ctx</span>
            {!m.is_free&&m.cost_input_per_1k>0&&<span>${m.cost_input_per_1k.toFixed(4)}/1k</span>}
            {m.has_api_key&&<span className="text-green-500">🔑</span>}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {testResult&&<div className="flex items-center gap-1.5 text-xs">{testResult.ok?<><CheckCircle2 size={13} className="text-green-500"/><span className="text-green-600">{testResult.latency_ms}ms</span></>:<><XCircle size={13} className="text-red-500"/><span className="text-red-500 max-w-32 truncate">{testResult.error}</span></>}</div>}
          <button onClick={e=>{e.stopPropagation();onTest(m.id);}} disabled={testing} className="flex items-center gap-1 text-xs px-2.5 py-1.5 border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600 disabled:opacity-50">
            {testing?<Spinner size={11}/>:<Zap size={11}/>}{testing?"…":"Test"}
          </button>
          <button onClick={e=>{e.stopPropagation();onDelete(m.id);}} className="p-1.5 text-slate-300 hover:text-red-500 rounded-lg hover:bg-red-50 transition-colors"><Trash2 size={13}/></button>
          {expanded?<ChevronUp size={14} className="text-slate-400"/>:<ChevronDown size={14} className="text-slate-400"/>}
        </div>
      </div>
      {expanded&&<ModelDetail m={m}/>}
    </div>
  );
});

const FilterChip = memo(function FilterChip({label,active,onClick}:{label:string;active:boolean;onClick:()=>void}){
  return <button onClick={onClick} className={`text-xs px-3 py-1.5 rounded-lg border transition-colors ${active?"bg-slate-900 text-white border-slate-900":"border-slate-200 text-slate-600 hover:bg-slate-50"}`}>{label}</button>;
});

// ── Virtual row (react-window) ────────────────────────────────────────────────
interface RowData { items:LLMModel[];expandedId:number|null;testResults:Record<number,any>;testingId:number|null;onToggle:(id:number)=>void;onTest:(id:number)=>void;onDelete:(id:number)=>void; }
function VirtualRow({index,style,items,expandedId,testResults,testingId,onToggle,onTest,onDelete}:RowComponentProps<RowData>){
  const m=items[index];
  return <div style={{...style,paddingBottom:8}}><ModelCard model={m} expanded={expandedId===m.id} testResult={testResults[m.id]} testing={testingId===m.id} onToggle={onToggle} onTest={onTest} onDelete={onDelete}/></div>;
}

// ── Page ──────────────────────────────────────────────────────────────────────
export default function ModelsPage(){
  const[showForm,setShowForm]=useState(false);
  const[showCatalog,setShowCatalog]=useState(false);
  const[expandedId,setExpandedId]=useState<number|null>(null);
  const[testingId,setTestingId]=useState<number|null>(null);
  const[testResults,setTestResults]=useState<Record<number,any>>({});
  const[creating,setCreating]=useState(false);
  const[dupWarning,setDupWarning]=useState<string|null>(null);
  const[importingOllama,setImportingOllama]=useState(false);
  const[ollamaStatus,setOllamaStatus]=useState<{available:boolean;total:number}|null>(null);
  const[filters,setFilters]=useState<Filters>(F0);
  const[form,setForm]=useState({name:"",provider:"custom" as ModelProvider,model_id:"",endpoint:"",api_key:"",context_length:4096,cost_input_per_1k:0,cost_output_per_1k:0,notes:""});

  const{models,isLoading:loading,refresh:refreshModels}=useModelsFull();
  const debouncedSearch=useDebounce(filters.search,250);

  useEffect(()=>{
    if(loading)return;
    const ctrl=new AbortController();
    const t=setTimeout(()=>ollamaApi.check(ctrl.signal).then(setOllamaStatus).catch(()=>{}),300);
    return()=>{clearTimeout(t);ctrl.abort();};
  },[loading]);

  const filtered=useMemo(()=>applyFilters(models,filters,debouncedSearch.toLowerCase()),[models,filters,debouncedSearch]);
  const freeCount=useMemo(()=>models.filter(m=>m.is_free).length,[models]);
  const visionCount=useMemo(()=>models.filter(m=>m.supports_vision).length,[models]);
  const toolsCount=useMemo(()=>models.filter(m=>m.supports_tools).length,[models]);
  const reasoningCount=useMemo(()=>models.filter(m=>m.supports_reasoning).length,[models]);

  // Stable memoized callbacks — prevents ModelCard re-renders
  const handleToggle=useCallback((id:number)=>setExpandedId(prev=>prev===id?null:id),[]);
  const handleTest=useCallback(async(id:number)=>{
    setTestingId(id);
    try{const r=await modelsApi.test(id);setTestResults(p=>({...p,[id]:r}));}
    catch(e){setTestResults(p=>({...p,[id]:{ok:false,latency_ms:0,error:String(e)}}));}
    finally{setTestingId(null);}
  },[]);
  const handleDelete=useCallback(async(id:number)=>{
    if(!confirm("Delete this model?"))return;
    await modelsApi.delete(id).catch(e=>alert(String(e)));
    refreshModels();
  },[refreshModels]);
  const handleImportOllama=useCallback(async()=>{
    setImportingOllama(true);
    try{const r=await ollamaApi.import();if(r.added>0)refreshModels();alert(r.available?`${r.added} model(s) imported`:"Ollama unavailable");}
    catch(e:any){alert(String(e));}
    finally{setImportingOllama(false);}
  },[refreshModels]);
  const setFilter=useCallback(<K extends keyof Filters>(k:K,v:Filters[K])=>setFilters(f=>({...f,[k]:v})),[]);
  const resetFilters=useCallback(()=>setFilters(F0),[]);

  const handleCreate=useCallback(async(e:React.FormEvent)=>{
    e.preventDefault();setDupWarning(null);
    if(models.some(m=>m.model_id===form.model_id)){setDupWarning(`Already registered: ${form.model_id}`);return;}
    setCreating(true);
    try{
      await modelsApi.create({name:form.name,provider:form.provider,model_id:form.model_id,endpoint:form.endpoint||undefined,api_key:form.api_key||undefined,context_length:form.context_length,cost_input_per_1k:form.cost_input_per_1k,cost_output_per_1k:form.cost_output_per_1k,notes:form.notes});
      setForm({name:"",provider:"custom",model_id:"",endpoint:"",api_key:"",context_length:4096,cost_input_per_1k:0,cost_output_per_1k:0,notes:""});
      setShowForm(false);refreshModels();
    }catch(err:any){if(String(err).includes("409"))setDupWarning(`Already registered: ${form.model_id}`);else alert(String(err));}
    finally{setCreating(false);}
  },[form,models,refreshModels]);

  const listData=useMemo<RowData>(()=>({items:filtered,expandedId,testResults,testingId,onToggle:handleToggle,onTest:handleTest,onDelete:handleDelete}),[filtered,expandedId,testResults,testingId,handleToggle,handleTest,handleDelete]);
  const listRef=useRef<ListImperativeAPI>(null);

  return(
    <AppErrorBoundary>
    <div>
      <PageHeader title="Model Registry" description={`${models.length} models · ${freeCount} gratuits`}
        action={<div className="flex gap-2">
          {ollamaStatus?.available&&<button onClick={handleImportOllama} disabled={importingOllama} className="flex items-center gap-2 border border-purple-200 px-4 py-2 rounded-lg text-sm hover:bg-purple-50 text-purple-700 disabled:opacity-50">{importingOllama?<Spinner size={13}/>:"🦙"} Ollama ({ollamaStatus.total})</button>}
          <button onClick={()=>setShowCatalog(true)} className="flex items-center gap-2 border border-slate-200 px-4 py-2 rounded-lg text-sm hover:bg-slate-50 text-slate-700">🔍 Catalogue OpenRouter</button>
          <button onClick={()=>setShowForm(!showForm)} className="flex items-center gap-2 bg-slate-900 text-white px-4 py-2 rounded-lg text-sm hover:bg-slate-700"><Plus size={14}/> Ajouter</button>
        </div>}
      />

      <div className="px-4 sm:px-8 pt-4 pb-2 space-y-3">
        <div className="relative max-w-sm">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"/>
          <input value={filters.search} onChange={e=>setFilter("search",e.target.value)} placeholder="Search by name or model ID…" className="w-full pl-9 pr-4 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-slate-900"/>
        </div>
        <div className="flex gap-2 flex-wrap items-center">
          <FilterChip label={`🆓 Gratuit (${freeCount})`} active={filters.onlyFree} onClick={()=>setFilter("onlyFree",!filters.onlyFree)}/>
          <FilterChip label={`👁 Vision (${visionCount})`} active={filters.onlyVision} onClick={()=>setFilter("onlyVision",!filters.onlyVision)}/>
          <FilterChip label={`🔧 Tools (${toolsCount})`} active={filters.onlyTools} onClick={()=>setFilter("onlyTools",!filters.onlyTools)}/>
          <FilterChip label={`🧠 Reasoning (${reasoningCount})`} active={filters.onlyReasoning} onClick={()=>setFilter("onlyReasoning",!filters.onlyReasoning)}/>
          {(Object.values(filters).some(v=>v!==''&&v!==false))&&<button onClick={resetFilters} className="text-xs px-3 py-1.5 text-slate-400 hover:text-slate-700">Reset</button>}
          <span className="text-xs text-slate-400 ml-auto">{filtered.length} / {models.length} models</span>
        </div>
      </div>

      {showForm&&(
        <div className="mx-4 sm:mx-8 mt-4 bg-white border border-slate-200 rounded-xl p-6">
          <h3 className="font-medium text-slate-900 mb-4">Nouveau model</h3>
          {dupWarning&&<div className="mb-4 p-3 bg-amber-50 border border-amber-200 rounded-lg text-xs text-amber-700">⚠️ {dupWarning}</div>}
          <form onSubmit={handleCreate} className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {[{label:"Nom *",key:"name",type:"text",ph:"ex. GPT-4o Mini"},{label:"Model ID *",key:"model_id",type:"text",ph:"ex. gpt-4o-mini"},{label:"Endpoint",key:"endpoint",type:"text",ph:"https://openrouter.ai/api/v1"},{label:"API Key",key:"api_key",type:"password",ph:"sk-…"}].map(({label,key,type,ph})=>(
              <div key={key}><label className="text-xs font-medium text-slate-600 mb-1 block">{label}</label><input type={type} required={label.includes("*")} value={(form as any)[key]} placeholder={ph} onChange={e=>setForm(f=>({...f,[key]:e.target.value}))} className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900"/></div>
            ))}
            <div><label className="text-xs font-medium text-slate-600 mb-1 block">Provider</label><select value={form.provider} onChange={e=>setForm(f=>({...f,provider:e.target.value as ModelProvider}))} className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm">{PROVIDERS.map(p=><option key={p} value={p}>{PROVIDER_LABELS[p]}</option>)}</select></div>
            <div><label className="text-xs font-medium text-slate-600 mb-1 block">Context length</label><input type="number" value={form.context_length} onChange={e=>setForm(f=>({...f,context_length:+e.target.value}))} className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm"/></div>
            <div className="col-span-2 flex gap-3 pt-1">
              <button type="submit" disabled={creating} className="bg-slate-900 text-white px-4 py-2 rounded-lg text-sm hover:bg-slate-700 disabled:opacity-50">{creating?"Creating…":"Ajouter"}</button>
              <button type="button" onClick={()=>{setShowForm(false);setDupWarning(null);}} className="px-4 py-2 text-sm text-slate-600">Cancel</button>
            </div>
          </form>
        </div>
      )}

      <div className="px-4 sm:px-8 pt-4 pb-8">
        {loading?(
          <div className="flex justify-center py-20"><Spinner size={24}/></div>
        ):filtered.length===0?(
          <EmptyState icon="🤖" title={models.length===0?"No models":"No results"} description={models.length===0?"Add models from the OpenRouter catalog.":"Adjust your filters."}/>
        ):filtered.length<=80?(
          /* Small list — regular map with React.memo cards */
          <div className="space-y-2">
            {filtered.map(m=><ModelCard key={m.id} model={m} expanded={expandedId===m.id} testResult={testResults[m.id]} testing={testingId===m.id} onToggle={handleToggle} onTest={handleTest} onDelete={handleDelete}/>)}
          </div>
        ):(
          /* Large list — virtualized, collapsed cards only */
          <List listRef={listRef} style={{height:Math.min(700,typeof window!=="undefined"?window.innerHeight-300:600),width:"100%"}} rowCount={filtered.length} rowHeight={CARD_H+8} rowProps={listData} rowComponent={VirtualRow} overscanCount={5}/>
        )}
      </div>

      {showCatalog&&<ModelCatalogModal existingModelIds={models.map(m=>m.model_id)} onClose={()=>{setShowCatalog(false);refreshModels();}}/>}
    </div>
    </AppErrorBoundary>
  );
}
