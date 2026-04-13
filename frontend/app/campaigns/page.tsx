"use client";
import { useState, useCallback, useMemo, memo, useEffect } from "react";
import { campaignsApi } from "@/lib/api";
import type { Campaign, LLMModelSlim, Benchmark } from "@/lib/api";
import { useCampaigns, useModels, useBenchmarks } from "@/lib/useApi";
import { PageHeader } from "@/components/PageHeader";
import { StatusBadge } from "@/components/StatusBadge";
import { EmptyState } from "@/components/EmptyState";
import { Spinner } from "@/components/Spinner";
import { ModelSelector } from "@/components/ModelSelector";
import { timeAgo } from "@/lib/utils";
import { Plus, Play, Square, Trash2, BarChart2, RefreshCw,
         ChevronRight, ChevronLeft, Check, Radio, ChevronDown, ChevronUp,
         ScrollText, Copy, CheckCircle2 } from "lucide-react";
import Link from "next/link";
import { API_BASE } from "@/lib/config";

// ── Reproducibility manifest button (#93) ────────────────────────────────────
function ManifestButton({ campaignId }: { campaignId: number }) {
  const [loading, setLoading] = useState(false);
  const [manifest, setManifest] = useState<any>(null);
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);

  const generate = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (manifest) { setOpen(o => !o); return; }
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/research/manifests/generate/${campaignId}`, { method: "POST" });
      if (res.ok) { setManifest(await res.json()); setOpen(true); }
    } catch {}
    setLoading(false);
  };

  const copy = (e: React.MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard.writeText(JSON.stringify(manifest, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="relative">
      <button onClick={generate} disabled={loading}
        className="flex items-center gap-1.5 text-xs px-3 py-1.5 border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600 disabled:opacity-40"
        title="Generate reproducibility manifest">
        {loading ? <Spinner size={12} /> : <ScrollText size={13} />}
        {loading ? "…" : "Manifest"}
      </button>

      {open && manifest && (
        <div className="absolute right-0 top-9 z-50 w-80 bg-white border border-slate-200 rounded-xl shadow-xl p-4 space-y-2"
          onClick={e => e.stopPropagation()}>
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-700">📋 Reproducibility Manifest</span>
            <button onClick={copy} className="flex items-center gap-1 text-[10px] text-blue-500 hover:underline">
              {copied ? <><CheckCircle2 size={10} /> Copied</> : <><Copy size={10} /> Copy JSON</>}
            </button>
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs">
            {[
              ["Seed", manifest.seed ?? "—"],
              ["Temperature", manifest.temperature ?? "—"],
              ["Benchmarks", manifest.benchmark_versions ? Object.keys(manifest.benchmark_versions).length : "—"],
              ["Judge", manifest.judge_version ?? "—"],
            ].map(([k, v]) => (
              <div key={k as string} className="bg-slate-50 rounded-lg p-2">
                <div className="text-slate-400 text-[10px]">{k}</div>
                <div className="font-mono font-medium text-slate-800 truncate">{v}</div>
              </div>
            ))}
          </div>
          {manifest.replication_command && (
            <div className="bg-slate-900 rounded-lg p-2 font-mono text-[10px] text-green-400 break-all">
              {manifest.replication_command}
            </div>
          )}
          <button onClick={() => setOpen(false)} className="text-[10px] text-slate-400 hover:text-slate-600 w-full text-right">
            Close
          </button>
        </div>
      )}
    </div>
  );
}

type BenchFilterKey = "all"|"academic"|"safety"|"coding"|"custom"|"inesia";
const BENCH_FILTERS: {key:BenchFilterKey;label:string}[] = [
  {key:"all",label:"Tous"},{key:"inesia",label:"☿ INESIA"},{key:"academic",label:"Academic"},
  {key:"safety",label:"Safety"},{key:"coding",label:"Code"},{key:"custom",label:"Custom"},
];
function benchInFilter(b:Benchmark,f:BenchFilterKey):boolean {
  if(f==="all") return true;
  if(f==="inesia") return (b.tags??[]).some(t=>["INESIA","frontier","cyber","disinformation","MITRE","DISARM","ATLAS"].includes(t))||b.type==="safety";
  return b.type===f;
}

const STEPS=["Parameters","Models","Benchmarks","Launch"];

const StepIndicator=memo(function StepIndicator({current}:{current:number}){
  return(
    <div className="flex items-center gap-2 mb-6 flex-wrap">
      {STEPS.map((label,i)=>(
        <div key={label} className="flex items-center gap-2">
          <div className={`flex items-center justify-center w-7 h-7 rounded-full text-xs font-medium transition-colors ${i<current?"bg-green-500 text-white":i===current?"bg-slate-900 text-white":"bg-slate-100 text-slate-400"}`}>
            {i<current?<Check size={12}/>:i+1}
          </div>
          <span className={`text-sm ${i===current?"font-medium text-slate-900":"text-slate-400"}`}>{label}</span>
          {i<STEPS.length-1&&<ChevronRight size={14} className="text-slate-200 mx-1"/>}
        </div>
      ))}
    </div>
  );
});

// ── LiveFeed — ONE instance per running campaign, self-contained ───────────────
interface LiveItem{id:number;item_index:number;prompt:string;response:string;expected:string|null;score:number;latency_ms:number;model_name:string;benchmark_name:string;}
interface LiveData{items:LiveItem[];total_items:number;completed_runs:number;total_runs:number;items_per_sec:number;eta_seconds:number|null;pending_runs:number;current_item_index:number|null;current_item_total:number|null;current_item_label:string|null;}

function fmtTime(s:number|null):string{
  if(s==null||s<0)return"—";
  if(s<60)return`${s}s`;if(s<3600)return`${Math.floor(s/60)}m ${s%60}s`;
  return`${Math.floor(s/3600)}h ${Math.floor((s%3600)/60)}m`;
}

function useCountdown(eta:number|null){
  const[rem,setRem]=useState<number|null>(eta);
  useEffect(()=>{if(eta==null){setRem(null);return;}setRem(eta);const t=setInterval(()=>setRem(s=>s!=null&&s>0?s-1:s),1000);return()=>clearInterval(t);},[eta]);
  return rem;
}

const LiveFeed=memo(function LiveFeed({campaignId}:{campaignId:number}){
  const[data,setData]=useState<LiveData|null>(null);
  const[open,setOpen]=useState(true);
  const[selected,setSelected]=useState<LiveItem|null>(null);
  const countdown=useCountdown(data?.eta_seconds??null);

  useEffect(()=>{
    let active=true;
    const fetch_=async()=>{
      try{const r=await fetch(`${API_BASE}/results/campaign/${campaignId}/live?limit=8`);if(r.ok&&active)setData(await r.json());}catch{}
    };
    fetch_();
    // Single interval per LiveFeed instance — 4s polling
    const poll=setInterval(fetch_,4000);
    return()=>{active=false;clearInterval(poll);};
  },[campaignId]);

  const latest=data?.items?.[0]??null;

  return(
    <div className="border-t border-slate-100">
      <button className="w-full flex items-center justify-between px-5 py-2.5 text-xs hover:bg-slate-50" onClick={()=>setOpen(o=>!o)}>
        <div className="flex items-center gap-3 flex-wrap">
          <Radio size={12} className="text-red-500 animate-pulse shrink-0"/>
          <span className="font-semibold text-slate-700">Live</span>
          {!data&&<span className="text-slate-400 animate-pulse">Connecting…</span>}
          {countdown!=null&&countdown>0&&<span className="bg-slate-900 text-white px-2 py-0.5 rounded font-mono font-bold text-xs">⏱ {fmtTime(countdown)}</span>}
          {data?.current_item_index!=null&&data?.current_item_total!=null&&<span className="text-blue-600 font-mono text-[11px]">🔄 {data.current_item_index}/{data.current_item_total}</span>}
          {latest&&<span className="text-slate-400 truncate max-w-48">{latest.model_name} → {latest.benchmark_name}</span>}
          {data&&<span className="text-slate-300 ml-auto">{data.total_items} items · {data.completed_runs}/{data.total_runs} runs</span>}
        </div>
        {open?<ChevronUp size={13} className="text-slate-300 shrink-0"/>:<ChevronDown size={13} className="text-slate-300 shrink-0"/>}
      </button>

      {open&&(
        <div className="border-t border-slate-50">
          {data?.current_item_index!=null&&data?.current_item_label&&(
            <div className="px-5 py-2 bg-amber-50 border-b border-amber-100 flex items-center gap-2 text-xs">
              <div className="w-3 h-3 border-2 border-amber-500 border-t-transparent rounded-full animate-spin shrink-0"/>
              <span className="text-amber-700 font-medium">Processing:</span>
              <span className="text-amber-600">{data.current_item_label}</span>
              <span className="text-amber-500 font-mono ml-auto">item {data.current_item_index}/{data.current_item_total}</span>
            </div>
          )}
          {latest&&(
            <div className="px-5 py-3 bg-blue-50 border-b border-blue-100">
              <div className="flex items-center gap-2 mb-2 text-xs">
                <span className="font-semibold text-blue-700">{latest.model_name}</span>
                <span className="text-blue-300">→</span><span className="text-blue-600">{latest.benchmark_name}</span>
                <span className={`ml-auto font-bold ${latest.score>=0.5?"text-green-600":"text-red-500"}`}>{latest.score>=0.5?"✓":"✗"} {(latest.score*100).toFixed(0)}%</span>
                <span className="text-slate-400">{latest.latency_ms}ms</span>
              </div>
              <div className="text-xs text-slate-700 bg-white rounded-lg p-2.5 border border-blue-100 space-y-1.5">
                <div><span className="font-medium text-slate-400 uppercase text-[10px] tracking-wide">Prompt</span><p className="mt-0.5 line-clamp-2">{latest.prompt}</p></div>
                {latest.response&&<div><span className="font-medium text-slate-400 uppercase text-[10px] tracking-wide">Response</span><p className="mt-0.5 line-clamp-2">{latest.response}</p></div>}
                {latest.expected&&<div className="flex items-center gap-2 text-[11px]"><span className="text-slate-400">Expected:</span><span className="font-mono font-medium text-green-700 bg-green-50 px-1.5 py-0.5 rounded">{latest.expected}</span></div>}
              </div>
            </div>
          )}
          {(!data||data.items.length===0)?(
            <div className="px-5 py-4 text-xs text-slate-400 flex items-center gap-2"><div className="w-3 h-3 border-2 border-slate-300 border-t-transparent rounded-full animate-spin shrink-0"/>Waiting for first results…</div>
          ):(
            <div className="px-5 py-3 space-y-1.5 max-h-48 overflow-y-auto">
              {data.items.slice(1).map(item=>(
                <button key={item.id} onClick={()=>setSelected(s=>s?.id===item.id?null:item)} className="w-full flex items-center gap-2 text-xs text-left hover:bg-slate-50 rounded-lg px-2 py-1.5 transition-colors">
                  <span className={`w-4 h-4 rounded-full flex items-center justify-center text-white text-[9px] shrink-0 ${item.score>=0.5?"bg-green-500":"bg-red-400"}`}>{item.score>=0.5?"✓":"✗"}</span>
                  <span className="text-slate-500 w-24 shrink-0 truncate">{item.model_name}</span>
                  <span className="text-slate-400 flex-1 truncate">{item.prompt}</span>
                  <span className="text-slate-300 shrink-0">{item.latency_ms}ms</span>
                </button>
              ))}
              {selected&&selected.id!==latest?.id&&(
                <div className="bg-slate-50 rounded-lg p-3 border border-slate-100 text-xs space-y-1.5 mt-1">
                  <div className="font-medium text-slate-600">{selected.model_name} → {selected.benchmark_name}</div>
                  <div><span className="text-slate-400">Q: </span>{selected.prompt}</div>
                  {selected.response&&<div><span className="text-slate-400">A: </span>{selected.response}</div>}
                  {selected.expected&&<div><span className="text-slate-400">Expected: </span><span className="font-mono text-green-700">{selected.expected}</span></div>}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
});

// ── Main page ─────────────────────────────────────────────────────────────────
export default function CampaignsPage(){
  // ── State — minimal, no duplication of SWR data ────────────────────────────
  const[showWizard,setShowWizard]=useState(false);
  const[step,setStep]=useState(0);
  const[saving,setSaving]=useState(false);
  const[runningId,setRunningId]=useState<number|null>(null);
  const[benchFilter,setBenchFilter]=useState<BenchFilterKey>("all");
  const[activeLiveFeed,setActiveLiveFeed]=useState<number|null>(null); // ONE feed at a time
  const[form,setForm]=useState({name:"",description:"",model_ids:[] as number[],benchmark_ids:[] as number[],max_samples:50,temperature:0.0});

  // ── SWR — use directly, NO local useState copy ─────────────────────────────
  const{campaigns,isLoading,refresh:refreshCampaigns,hasRunning}=useCampaigns();
  const{models}=useModels();
  const{benchmarks}=useBenchmarks(undefined,!isLoading); // staggered

  // Auto-show live feed for newest running campaign
  useEffect(()=>{
    const running=campaigns.find(c=>c.status==="running"||c.id===runningId);
    if(running&&activeLiveFeed!==running.id) setActiveLiveFeed(running.id);
    else if(!running&&runningId===null) setActiveLiveFeed(null);
  },[campaigns,runningId]);

  // Auto-refresh while any campaign is running (SWR handles dedup)
  useEffect(()=>{
    if(!hasRunning&&runningId===null) return;
    const t=setInterval(()=>refreshCampaigns(),5000);
    return()=>clearInterval(t);
  },[hasRunning,runningId,refreshCampaigns]);

  const toggleId=(arr:number[],id:number)=>arr.includes(id)?arr.filter(x=>x!==id):[...arr,id];

  const resetWizard=useCallback(()=>{
    setStep(0);
    setForm({name:"",description:"",model_ids:[],benchmark_ids:[],max_samples:50,temperature:0.0});
    setShowWizard(false);setBenchFilter("all");
  },[]);

  const handleCreate=useCallback(async()=>{
    setSaving(true);
    try{await campaignsApi.create({...form});resetWizard();refreshCampaigns();}
    catch(err){alert(String(err));}
    finally{setSaving(false);}
  },[form,resetWizard,refreshCampaigns]);

  const handleRun=useCallback(async(id:number)=>{
    setRunningId(id);
    setActiveLiveFeed(id); // show live feed immediately
    try{
      await campaignsApi.run(id);
      // Rely on the auto-refresh effect above — no manual polling loop
      refreshCampaigns();
    }catch(e:any){
      alert(e?.message??String(e));
      setRunningId(null);
      refreshCampaigns();
    }
  },[refreshCampaigns]);

  const handleCancel=useCallback(async(id:number)=>{
    await campaignsApi.cancel(id).catch(e=>alert(String(e)));
    setRunningId(null);refreshCampaigns();
  },[refreshCampaigns]);

  const handleDelete=useCallback(async(id:number)=>{
    if(!confirm("Delete campaign and all results?"))return;
    try{await campaignsApi.delete(id);}catch(e){alert(String(e));return;}
    refreshCampaigns();
  },[refreshCampaigns]);

  const isRunning=(c:Campaign)=>c.status==="running"||runningId===c.id;

  const filteredBenches=useMemo(()=>benchmarks.filter(b=>benchInFilter(b,benchFilter)),[benchmarks,benchFilter]);

  const canNext=[form.name.trim().length>0,form.model_ids.length>0,form.benchmark_ids.length>0,true][step];

  return(
    <div>
      <PageHeader title="Campaigns" description="Multi-model × multi-benchmark evaluations."
        action={!showWizard&&<button onClick={()=>setShowWizard(true)} className="flex items-center gap-2 bg-slate-900 text-white px-4 py-2 rounded-lg text-sm hover:bg-slate-700"><Plus size={14}/> New campaign</button>}
      />

      {showWizard&&(
        <div className="mx-4 sm:mx-8 mt-6 bg-white border border-slate-200 rounded-2xl p-4 sm:p-7">
          <StepIndicator current={step}/>

          {step===0&&(
            <div className="space-y-4 max-w-lg">
              <div><label className="text-xs font-medium text-slate-600 mb-1 block">Nom *</label><input autoFocus required value={form.name} onChange={e=>setForm(f=>({...f,name:e.target.value}))} placeholder="ex. Frontier safety audit v1" className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900"/></div>
              <div><label className="text-xs font-medium text-slate-600 mb-1 block">Description</label><input value={form.description} onChange={e=>setForm(f=>({...f,description:e.target.value}))} className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900"/></div>
              <div className="grid grid-cols-2 gap-4">
                <div><label className="text-xs font-medium text-slate-600 mb-1 block">Max samples / bench</label><input type="number" value={form.max_samples} onChange={e=>setForm(f=>({...f,max_samples:+e.target.value}))} className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900"/></div>
                <div><label className="text-xs font-medium text-slate-600 mb-1 block">Temperature</label><input type="number" step="0.1" min="0" max="2" value={form.temperature} onChange={e=>setForm(f=>({...f,temperature:+e.target.value}))} className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900"/></div>
              </div>
            </div>
          )}

          {step===1&&<ModelSelector mode="multi" selected={form.model_ids} onChange={ids=>setForm(f=>({...f,model_ids:ids.map(id=>Number(id))}))} idType="db_id" label="Select models to evaluate" maxHeight="max-h-72"/>}

          {step===2&&(
            <div>
              <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
                <div className="flex gap-1.5 flex-wrap">
                  {BENCH_FILTERS.map(({key,label})=>(
                    <button key={key} onClick={()=>setBenchFilter(key)} className={`text-xs px-2.5 py-1 rounded-lg transition-colors ${benchFilter===key?"bg-slate-900 text-white":"border border-slate-200 text-slate-600 hover:bg-slate-50"}`}>
                      {label} <span className="opacity-50">{benchmarks.filter(b=>benchInFilter(b,key)).length}</span>
                    </button>
                  ))}
                </div>
                <span className="text-xs bg-slate-100 text-slate-600 px-2 py-1 rounded-full shrink-0">{form.benchmark_ids.length} selected</span>
              </div>
              <div className="space-y-1.5 max-h-72 overflow-y-auto">
                {filteredBenches.map(b=>{
                  const selected=form.benchmark_ids.includes(b.id);
                  return(
                    <button key={b.id} type="button" onClick={()=>setForm(f=>({...f,benchmark_ids:toggleId(f.benchmark_ids,b.id)}))}
                      className={`w-full flex items-center gap-3 p-3 rounded-xl border text-left transition-colors ${selected?"border-slate-900 bg-slate-50":"border-slate-100 bg-white hover:border-slate-200"}`}>
                      <div className={`w-5 h-5 rounded-md border-2 flex items-center justify-center shrink-0 ${selected?"border-slate-900 bg-slate-900":"border-slate-300"}`}>{selected&&<Check size={11} className="text-white"/>}</div>
                      <div className="flex-1 min-w-0"><div className="text-sm font-medium text-slate-900 truncate">{b.name}</div><div className="text-xs text-slate-400">{b.metric} · {b.num_samples??"all"} items</div></div>
                      <span className={`text-xs px-2 py-0.5 rounded-full shrink-0 ${b.type==="safety"?"bg-red-50 text-red-600":b.type==="academic"?"bg-blue-50 text-blue-600":"bg-slate-100 text-slate-500"}`}>{b.type}</span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {step===3&&(
            <div className="space-y-4 max-w-lg">
              <div className="bg-slate-50 rounded-xl p-5 space-y-3 text-sm">
                {[["Campagne",form.name],["Models",form.model_ids.length],["Benchmarks",form.benchmark_ids.length],["Runs total",form.model_ids.length*form.benchmark_ids.length],["Max items",form.max_samples],["Temperature",form.temperature]].map(([l,v])=>(
                  <div key={String(l)} className="flex justify-between"><span className="text-slate-500">{l}</span><span className="font-medium text-slate-900">{v}</span></div>
                ))}
              </div>
            </div>
          )}

          <div className="flex items-center justify-between mt-6 pt-5 border-t border-slate-100">
            <button onClick={step===0?resetWizard:()=>setStep(s=>s-1)} className="flex items-center gap-1.5 text-sm text-slate-600 hover:text-slate-900"><ChevronLeft size={14}/>{step===0?"Cancel":"Back"}</button>
            {step<3?(
              <button onClick={()=>setStep(s=>s+1)} disabled={!canNext} className="flex items-center gap-1.5 bg-slate-900 text-white px-5 py-2 rounded-lg text-sm hover:bg-slate-700 disabled:opacity-40">Suivant <ChevronRight size={14}/></button>
            ):(
              <button onClick={handleCreate} disabled={saving} className="flex items-center gap-2 bg-green-600 text-white px-5 py-2 rounded-lg text-sm hover:bg-green-700 disabled:opacity-50">
                {saving?<Spinner size={13}/>:<Check size={14}/>}{saving?"Creating…":"Create campaign"}
              </button>
            )}
          </div>
        </div>
      )}

      <div className="p-4 sm:p-8 pt-4 sm:pt-6 space-y-3">
        {isLoading?(
          <div className="flex justify-center py-20"><Spinner size={24}/></div>
        ):campaigns.length===0?(
          <EmptyState icon="🚀" title="No campaigns" description="Create a campaign to start evaluating models."/>
        ):campaigns.map(c=>{
          const running=isRunning(c);
          const modelCount=Array.isArray(c.model_ids)?c.model_ids.length:0;
          const benchCount=Array.isArray(c.benchmark_ids)?c.benchmark_ids.length:0;
          return(
            <div key={c.id} className="bg-white border border-slate-200 rounded-xl overflow-hidden">
              <div className="flex items-start gap-4 p-5">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span className="font-medium text-slate-900">{c.name}</span>
                    <StatusBadge status={c.status}/>
                  </div>
                  {c.description&&<p className="text-xs text-slate-500 mb-1">{c.description}</p>}
                  {c.status==="failed"&&c.error_message&&!c.error_message.startsWith("ETA:")&&<p className="text-xs text-red-500 mb-1 font-mono">{c.error_message}</p>}
                  <div className="flex gap-3 text-xs text-slate-400 flex-wrap">
                    <span>{modelCount} model{modelCount!==1?"s":""}</span>
                    <span>{benchCount} benchmark{benchCount!==1?"s":""}</span>
                    <span>{c.max_samples??50} items/bench</span>
                    {c.created_at&&<span>{timeAgo(c.created_at)}</span>}
                  </div>
                  {c.status==="running"&&(()=>{
                    const totalRuns=modelCount*benchCount;
                    let vp=c.progress;
                    if(c.current_item_index!=null&&c.current_item_total!=null&&c.current_item_total>0&&totalRuns>0)
                      vp=Math.max(c.progress,c.progress+(c.current_item_index/c.current_item_total)*(100/totalRuns));
                    vp=Math.min(vp,99.9);
                    return(
                      <div className="mt-3">
                        <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
                          <span className="font-mono">{vp.toFixed(0)}%</span>
                          {c.error_message?.startsWith("ETA:")&&<span className="text-slate-500 font-medium">{c.error_message}</span>}
                        </div>
                        <div className="h-2 bg-slate-100 rounded-full overflow-hidden"><div className="h-full bg-gradient-to-r from-slate-800 to-slate-600 rounded-full transition-all duration-700 ease-out" style={{width:`${vp}%`}}/></div>
                      </div>
                    );
                  })()}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {c.status==="completed"&&!running&&(
                    <>
                      <Link href={`/dashboard?campaign=${c.id}`} className="flex items-center gap-1.5 text-xs px-3 py-1.5 border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600"><BarChart2 size={13}/> Results</Link>
                      <ManifestButton campaignId={c.id} />
                      <button onClick={()=>handleRun(c.id)} className="flex items-center gap-1.5 text-xs px-3 py-1.5 border border-slate-200 rounded-lg hover:bg-slate-50 text-slate-600"><RefreshCw size={13}/> Re-run</button>
                    </>
                  )}
                  {(c.status==="pending"||c.status==="failed")&&!running&&<button onClick={()=>handleRun(c.id)} className="flex items-center gap-1.5 text-xs px-3 py-1.5 bg-slate-900 text-white rounded-lg hover:bg-slate-700"><Play size={13}/> Run</button>}
                  {running&&<button onClick={()=>handleCancel(c.id)} className="flex items-center gap-1.5 text-xs px-3 py-1.5 bg-red-50 text-red-600 border border-red-200 rounded-lg hover:bg-red-100"><Square size={13}/> Cancel</button>}
                  {runningId===c.id&&c.status!=="running"&&<div className="flex items-center gap-1.5 text-xs text-slate-400"><Spinner size={13}/> Starting…</div>}
                  <button onClick={()=>handleDelete(c.id)} className="p-1.5 text-slate-300 hover:text-red-500 rounded-lg hover:bg-red-50 transition-colors"><Trash2 size={14}/></button>
                </div>
              </div>
              {/* ONE LiveFeed at a time — only the active one mounts */}
              {c.status==="running"&&activeLiveFeed===c.id&&<LiveFeed campaignId={c.id}/>}
            </div>
          );
        })}
      </div>
    </div>
  );
}
