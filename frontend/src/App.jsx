import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity, AlertTriangle, BarChart3, BookOpen, Bot, Check, ChevronRight, ClipboardCheck,
  Clock3, Gauge, HardHat, Headphones, LayoutDashboard, LogOut, Menu, Mic, Pause,
  Moon, Play, Plus, Radio, ShieldAlert, Square, Sun, TicketCheck, UserRound, Volume2, VolumeX, Wrench, X
} from 'lucide-react'
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from './api'

const nav = [
  ['overview', 'Overview', LayoutDashboard], ['tasks', 'Tasks', ClipboardCheck],
  ['training', 'Training', BookOpen], ['safety', 'Safety', ShieldAlert],
  ['efficiency', 'Machine metrics', BarChart3], ['assistant', 'Assistant', Bot],
  ['profile', 'Profile', UserRound],
]

function classNames(...x) { return x.filter(Boolean).join(' ') }
function minutes(value) { return `${Math.round(value || 0)} min` }
function normalizeSpeechText(text) {
  const months=['January','February','March','April','May','June','July','August','September','October','November','December']
  return String(text)
    .replace(/\b(\d{4})-(\d{1,2})-(\d{1,2})\b/g,(_,year,month,day)=>`${Number(day)} ${months[Number(month)-1]||month} ${year}`)
    .replace(/\b(\d{1,2})-(\d{1,2})\b/g,(_,day,month)=>`${Number(day)} ${months[Number(month)-1]||month}`)
}
function spoken(text, rate = 1, onError) {
  if (!('speechSynthesis' in window) || !text) { onError?.('Voice playback is not supported in this browser.'); return false }
  const synth = window.speechSynthesis
  synth.cancel()
  const play = () => {
    const utterance = new SpeechSynthesisUtterance(normalizeSpeechText(text))
    const voices = synth.getVoices()
    utterance.voice = voices.find(v => /^en-IN/i.test(v.lang)) || voices.find(v => /^en/i.test(v.lang)) || null
    utterance.lang = utterance.voice?.lang || 'en-IN'
    utterance.rate = rate
    utterance.volume = 1
    utterance.onerror = event => onError?.(`Voice playback stopped: ${event.error || 'browser error'}`)
    synth.resume()
    synth.speak(utterance)
  }
  window.setTimeout(play, 80)
  return true
}

const istDateTime = value => new Intl.DateTimeFormat('en-IN', {timeZone:'Asia/Kolkata', dateStyle:'medium', timeStyle:'short'}).format(new Date(value))
const istHour = () => Number(new Intl.DateTimeFormat('en-IN', {timeZone:'Asia/Kolkata', hour:'2-digit', hour12:false}).format(new Date()))

function App() {
  const [operators, setOperators] = useState([])
  const [operatorId, setOperatorId] = useState(Number(localStorage.getItem('operatorId')) || 1)
  const [page, setPage] = useState('overview')
  const [dashboard, setDashboard] = useState(null)
  const [error, setError] = useState('')
  const [menu, setMenu] = useState(false)
  const [notice, setNotice] = useState('')
  const [dark,setDark] = useState(()=>localStorage.getItem('theme')!=='light')
  const [handsFree,setHandsFree] = useState(false)

  const loadDashboard = async () => {
    try {
      const fresh = await api(`/api/dashboard/${operatorId}`)
      setDashboard(fresh)
      setOperators(current => current.map(item => item.id === fresh.operator.id ? fresh.operator : item))
      setError('')
    }
    catch (e) { setError(e.message) }
  }
  useEffect(() => { api('/api/operators').then(setOperators).catch(e => setError(e.message)) }, [])
  useEffect(() => { localStorage.setItem('operatorId', operatorId); loadDashboard(); const id=window.setInterval(loadDashboard,30000); return()=>window.clearInterval(id) }, [operatorId])
  useEffect(() => { if (!notice) return; const id = setTimeout(() => setNotice(''), 4500); return () => clearTimeout(id) }, [notice])
  useEffect(()=>{document.documentElement.classList.toggle('dark',dark);localStorage.setItem('theme',dark?'dark':'light')},[dark])

  const operator = dashboard?.operator || operators.find(o => o.id === operatorId)
  const content = {
    overview: <Overview data={dashboard} go={setPage} />,
    tasks: <Tasks data={dashboard} reload={loadDashboard} notify={setNotice} />,
    training: <Training operatorId={operatorId} notify={setNotice} reload={loadDashboard} />,
    safety: <Safety data={dashboard} notify={setNotice} />,
    efficiency: <Efficiency machine={dashboard?.machine} />,
    assistant: <Assistant operatorId={operatorId} notify={setNotice} />,
    profile: <Profile operator={operator} machine={dashboard?.machine} operators={operators} select={setOperatorId} />,
  }[page]

  return <div className="min-h-screen bg-canvas lg:flex">
    <aside className={classNames('fixed inset-y-0 left-0 z-40 w-64 bg-ink text-white transition-transform lg:sticky lg:top-0 lg:h-screen lg:translate-x-0', menu ? 'translate-x-0' : '-translate-x-full')}>
      <div className="flex h-16 items-center justify-between border-b border-zinc-700 px-5">
        <div className="flex items-center gap-3"><div className="h-8 w-10 bg-cat text-center text-lg font-semibold leading-8 text-ink">C</div><div><div className="text-sm font-semibold">OPERATOR ASSIST</div><div className="text-[10px] tracking-[.18em] text-zinc-400">FIELD CONSOLE</div></div></div>
        <button className="lg:hidden" onClick={() => setMenu(false)} aria-label="Close navigation"><X size={20}/></button>
      </div>
      <div className="border-b border-zinc-700 px-5 py-5"><div className="label text-zinc-500">Signed in as</div><div className="mt-1 font-semibold">{operator?.name || 'Loading'}</div><div className="mt-2 flex items-center gap-2 text-xs text-zinc-400"><HardHat size={14}/><span className="capitalize">{operator?.expertise}</span><span>•</span><span>{operator?.points || 0} pts</span></div></div>
      <nav className="p-3" aria-label="Primary navigation">{nav.map(([id, label, Icon]) => <button key={id} onClick={() => {setPage(id); setMenu(false)}} className={classNames('mb-1 flex w-full items-center gap-3 rounded-md px-3 py-2.5 text-left text-sm', page === id ? 'bg-cat font-semibold text-ink' : 'text-zinc-300 hover:bg-zinc-800')}><Icon size={18}/>{label}</button>)}</nav>
      <div className="absolute bottom-0 w-full border-t border-zinc-700 p-4 text-xs text-zinc-500">Prototype environment<br/>Synthetic data only</div>
    </aside>
    {menu && <button className="fixed inset-0 z-30 bg-black/40 lg:hidden" onClick={() => setMenu(false)} aria-label="Close menu overlay"/>}
    <main className="min-w-0 flex-1">
      <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-[#d8d8d3] bg-white px-4 sm:px-7">
        <div className="flex items-center gap-3"><button className="lg:hidden" onClick={() => setMenu(true)} aria-label="Open navigation"><Menu/></button><div><div className="text-xs text-zinc-500">{new Intl.DateTimeFormat('en-IN',{timeZone:'Asia/Kolkata',weekday:'long',month:'short',day:'numeric'}).format(new Date())} · IST</div><div className="text-sm font-semibold">{dashboard?.machine ? `${dashboard.machine.machine_code} · ${dashboard.machine.machine_type}` : 'No machine assigned'}</div></div></div>
        <div className="flex items-center gap-2"><HandsFreeAssistant operatorId={operatorId} enabled={handsFree} setEnabled={setHandsFree} notify={setNotice}/><button className="btn-quiet p-2" onClick={()=>setDark(v=>!v)} aria-label={dark?'Use light theme':'Use dark theme'}>{dark?<Sun size={17}/>:<Moon size={17}/>}</button><ShiftTimer start={dashboard?.shift_start}/><div className="hidden h-8 w-px bg-zinc-200 sm:block"/><button onClick={() => setPage('profile')} className="hidden items-center gap-2 text-sm sm:flex"><div className="flex h-8 w-8 items-center justify-center rounded-md bg-zinc-100"><UserRound size={16}/></div><span>{operator?.name?.split(' ')[0]}</span></button></div>
      </header>
      <div className="mx-auto max-w-[1440px] p-4 sm:p-7">{error && <Alert tone="red">{error}</Alert>}{!dashboard ? <Loading/> : content}</div>
      <footer className="border-t border-zinc-200 bg-white px-7 py-4 text-xs text-zinc-500">Smart Operator Assistant prototype. Made with the help of AI.</footer>
    </main>
    {notice && <div role="status" className="fixed bottom-5 right-5 z-50 max-w-sm rounded-md border border-zinc-700 bg-ink px-4 py-3 text-sm text-white shadow-xl">{notice}</div>}
  </div>
}

function HandsFreeAssistant({operatorId,enabled,setEnabled,notify}) {
  const [status,setStatus]=useState('Say “operator help”')
  const [response,setResponse]=useState(null)
  const recognitionRef=useRef(null), enabledRef=useRef(enabled), armedRef=useRef(false), processingRef=useRef(false), startRef=useRef(null)
  useEffect(()=>{enabledRef.current=enabled},[enabled])

  const askHandsFree=async question=>{
    processingRef.current=true
    try{recognitionRef.current?.stop()}catch{}
    setStatus('Checking the manual and live site data')
    try{
      const result=await api('/api/assistant/ask',{method:'POST',body:JSON.stringify({operator_id:operatorId,question})})
      setResponse({question,...result})
      setStatus(result.automatic_actions?'Critical action completed':'Answer ready')
      spoken(result.answer,0.95,notify)
      const delay=Math.min(14000,Math.max(3500,result.answer.length*42))
      window.setTimeout(()=>{processingRef.current=false;if(enabledRef.current)startRef.current?.()},delay)
    }catch(error){notify(error.message);setStatus('Voice request failed. Try again.');processingRef.current=false;if(enabledRef.current)window.setTimeout(()=>startRef.current?.(),1000)}
  }

  const startRecognition=()=>{
    if(!enabledRef.current||processingRef.current||recognitionRef.current)return
    const Recognition=window.SpeechRecognition||window.webkitSpeechRecognition
    if(!Recognition){setStatus('Hands-free mode needs Chrome or Edge');setEnabled(false);return}
    const recognition=new Recognition();recognitionRef.current=recognition;recognition.lang='en-IN';recognition.continuous=true;recognition.interimResults=false
    recognition.onstart=()=>setStatus(armedRef.current?'Listening for your question':'Say “operator help”')
    recognition.onresult=event=>{for(let i=event.resultIndex;i<event.results.length;i++){if(!event.results[i].isFinal)continue;const phrase=event.results[i][0].transcript.trim();const lower=phrase.toLowerCase();const wakeIndex=lower.indexOf('operator help');if(wakeIndex>=0){const remainder=phrase.slice(wakeIndex+'operator help'.length).trim();if(remainder){armedRef.current=false;askHandsFree(remainder)}else{armedRef.current=true;setStatus('Listening for your question')}}else if(armedRef.current){armedRef.current=false;askHandsFree(phrase)}}}
    recognition.onerror=event=>{if(event.error!=='aborted'&&event.error!=='no-speech')setStatus(event.error==='not-allowed'?'Microphone permission is blocked':`Voice listener paused: ${event.error}`)}
    recognition.onend=()=>{recognitionRef.current=null;if(enabledRef.current&&!processingRef.current)window.setTimeout(()=>startRef.current?.(),700)}
    try{recognition.start()}catch{recognitionRef.current=null}
  }
  startRef.current=startRecognition

  useEffect(()=>{if(enabled)startRecognition();else{armedRef.current=false;try{recognitionRef.current?.stop()}catch{}recognitionRef.current=null;setStatus('Say “operator help”')}return()=>{try{recognitionRef.current?.stop()}catch{}}},[enabled,operatorId])

  const toggle=async()=>{
    if(enabled){setEnabled(false);return}
    try{if(navigator.mediaDevices?.getUserMedia){const stream=await navigator.mediaDevices.getUserMedia({audio:true});stream.getTracks().forEach(track=>track.stop())}setEnabled(true)}
    catch{setStatus('Allow microphone access to use hands-free mode');notify('Microphone access is required for hands-free mode.')}
  }

  return <><button className={classNames('btn-quiet flex items-center gap-2 p-2 text-xs',enabled&&'border-emerald-600 bg-emerald-50 text-emerald-800')} onClick={toggle} aria-label={enabled?'Turn off hands-free assistant':'Turn on hands-free assistant'}><Radio size={17}/><span className="hidden xl:inline">Hands-free {enabled?'on':'off'}</span></button>{enabled&&<div className="fixed bottom-5 left-1/2 z-[65] w-[min(92vw,440px)] -translate-x-1/2 rounded-lg border border-zinc-700 bg-ink p-4 text-white shadow-2xl"><div className="flex items-start justify-between gap-3"><div><div className="flex items-center gap-2 text-xs text-cat"><span className="h-2 w-2 animate-pulse bg-cat"/> OPERATOR VOICE</div><div className="mt-1 text-sm">{status}</div></div><button onClick={()=>setEnabled(false)} aria-label="Turn off hands-free mode"><X size={18}/></button></div>{response&&<div className="mt-3 border-t border-zinc-700 pt-3"><div className="text-xs text-zinc-400">{response.question}</div><div className="mt-1 text-sm leading-5">{response.answer}</div>{response.automatic_actions&&<div className="mt-2 bg-red-700 p-2 text-xs">Supervisor contacted. Incident and ticket #{response.automatic_actions.ticket_id} logged.</div>}</div>}</div>}</>
}

function ShiftTimer({start}) {
  const [now,setNow] = useState(Date.now())
  useEffect(() => { const id=setInterval(()=>setNow(Date.now()),1000); return()=>clearInterval(id)},[])
  const elapsed = start ? Math.max(0, now-new Date(start).getTime()) : 0
  const h = String(Math.floor(elapsed/3600000)).padStart(2,'0'), m=String(Math.floor(elapsed/60000)%60).padStart(2,'0'), s=String(Math.floor(elapsed/1000)%60).padStart(2,'0')
  return <div className="flex items-center gap-2 text-sm"><Clock3 size={16}/><span className="hidden text-zinc-500 sm:inline">Shift</span><span className="font-semibold tabular-nums">{h}:{m}:{s}</span></div>
}

function PageTitle({eyebrow,title,children}) { return <div className="mb-6 flex flex-col justify-between gap-3 sm:flex-row sm:items-end"><div><div className="label">{eyebrow}</div><h1 className="mt-1 text-2xl font-semibold text-ink sm:text-3xl">{title}</h1></div>{children}</div> }
function Alert({children,tone='yellow'}) { return <div className={classNames('mb-5 flex items-start gap-3 rounded-md border p-3 text-sm',tone==='red'?'border-red-300 bg-red-50 text-red-900':'border-amber-300 bg-amber-50 text-amber-950')}><AlertTriangle className="mt-0.5 shrink-0" size={17}/>{children}</div> }
function Loading(){ return <div className="space-y-5"><div className="skeleton h-10 w-72 rounded-md"/><div className="grid gap-4 md:grid-cols-3">{[1,2,3].map(x=><div key={x} className="skeleton h-36 rounded-lg"/>)}</div><div className="skeleton h-72 rounded-lg"/></div> }

function Overview({data,go}) {
  const done = data.tasks.filter(t=>t.status==='completed').length
  const risk = data.breakdown
  return <>
    <PageTitle eyebrow="Shift overview" title={`Good ${istHour()<12?'morning':'afternoon'}, ${data.operator.name.split(' ')[0]}`}><button className="btn-yellow flex items-center gap-2" onClick={()=>go('tasks')}>View task plan <ChevronRight size={17}/></button></PageTitle>
    {risk && risk.risk!=='low' && <Alert tone="red"><div><div className="font-semibold">Maintenance risk is {risk.risk}</div><div className="mt-1">Forecast probability {Math.round(risk.probability*100)}%. Estimated {risk.hours_to_failure} operating hours to threshold. Drivers: {risk.drivers.join(', ')}.</div></div></Alert>}
    <div className="grid gap-4 md:grid-cols-3">
      <Stat icon={ClipboardCheck} label="Tasks completed" value={`${done} / ${data.tasks.length}`} note={`${data.tasks.length-done} remaining today`}/>
      <Stat icon={Activity} label="Assigned machine" value={data.machine?.machine_code || 'None'} note={data.machine?.machine_type || 'No active assignment'}/>
      <Stat icon={Gauge} label="Breakdown risk" value={risk ? `${Math.round(risk.probability*100)}%` : 'N/A'} note={risk ? `${risk.risk} risk · ${risk.hours_to_failure} h forecast` : 'No telemetry'}/>
    </div>
    <div className="mt-5 grid gap-5 xl:grid-cols-[1.6fr_1fr]">
      <section className="card p-5"><div className="mb-4 flex items-center justify-between"><div><div className="label">Today</div><h2 className="mt-1 text-lg font-semibold">Assigned work</h2></div><button className="text-sm font-semibold underline decoration-cat decoration-2 underline-offset-4" onClick={()=>go('tasks')}>Open tasks</button></div><TaskList tasks={data.tasks} compact/></section>
      <section className="card p-5"><div className="label">Site conditions</div><h2 className="mt-1 text-lg font-semibold capitalize">{data.weather?.condition}</h2><div className="mt-5 grid grid-cols-2 gap-4"><Metric label="Temperature" value={`${Math.round(data.weather?.temperature_c)}°C`}/><Metric label="Wind" value={`${Math.round(data.weather?.wind_kph)} km/h`}/><Metric label="Rain" value={`${data.weather?.precipitation_mm?.toFixed(1)} mm`}/><Metric label="Work impact" value={['heavy rain','hot'].includes(data.weather?.condition)?'Caution':'Normal'}/></div><div className="mt-5 border-t pt-4 text-sm text-zinc-600">Task duration forecasts include these conditions and the planned start time.</div></section>
    </div>
  </>
}
function Stat({icon:Icon,label,value,note}) { return <div className="card flex min-h-32 items-start gap-4 p-5"><div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-cat"><Icon size={20}/></div><div><div className="label">{label}</div><div className="mt-2 text-2xl font-semibold">{value}</div><div className="mt-1 text-sm text-zinc-500">{note}</div></div></div> }
function Metric({label,value}) { return <div><div className="text-xs text-zinc-500">{label}</div><div className="mt-1 font-semibold">{value}</div></div> }
function TaskList({tasks,compact=false,onOpen}) { return <div className="divide-y divide-zinc-200">{tasks.map((task,index)=><div key={task.id} className="flex items-center gap-4 py-3.5"><div className={classNames('flex h-7 w-7 shrink-0 items-center justify-center rounded-md border text-xs font-semibold',task.status==='completed'?'border-emerald-600 bg-emerald-600 text-white':'border-zinc-300')}>{task.status==='completed'?<Check size={15}/>:index+1}</div><div className="min-w-0 flex-1"><div className={classNames('font-semibold',task.status==='completed'&&'text-zinc-400 line-through')}>{task.title}</div><div className="mt-1 text-xs text-zinc-500">SITE-101 · North-east end · 30 meter</div><div className="mt-1 text-xs text-zinc-500">Forecast {minutes(task.predicted_minutes)} · {String(task.planned_start_hour).padStart(2,'0')}:00 IST</div></div><span className={classNames('status',task.status==='completed'?'bg-emerald-50 text-emerald-700':task.status==='in_progress'?'bg-blue-50 text-blue-700':'bg-zinc-100 text-zinc-600')}>{task.status.replace('_',' ')}</span>{!compact&&task.status!=='completed'&&<button className="btn-quiet" onClick={()=>onOpen(task)}>{task.status==='in_progress'?'Resume':'Open'}</button>}</div>)}</div> }

function Tasks({data,reload,notify}) {
  const [selected,setSelected]=useState(null)
  const [checks,setChecks]=useState({brakes:false,fluids:false,seatbelt:false,work_area_clear:false,cable_clearance:false})
  const [busy,setBusy]=useState(false)
  const [hazard,setHazard]=useState(null)

  useEffect(() => {
    if (!selected || selected.status !== 'in_progress') return
    let stopped = false
    const scan = async () => {
      try {
        const result = await api(`/api/tasks/${selected.id}/sensor-scan`, {method:'POST'})
        if (!stopped && result.hazard) {
          setHazard(result.hazard)
          spoken(`Safety intervention. ${result.hazard.message}. ${result.hazard.action}`, 0.95, notify)
        }
      } catch (error) {
        if (!stopped && !String(error.message).includes('active task')) notify(error.message)
      }
    }
    const first = window.setTimeout(scan, 4500 + Math.random() * 3500)
    const interval = window.setInterval(scan, 8500)
    return () => { stopped = true; window.clearTimeout(first); window.clearInterval(interval) }
  }, [selected?.id, selected?.status])

  const start=async()=>{setBusy(true);try{const result=await api(`/api/tasks/${selected.id}/start`,{method:'POST',body:JSON.stringify(checks)});spoken(result.instruction,1,notify);notify('Task started. Sensor monitoring is active.');setSelected({...selected,status:'in_progress'});await reload()}catch(e){notify(e.message)}finally{setBusy(false)}}
  const complete=async()=>{setBusy(true);try{const result=await api(`/api/tasks/${selected.id}/complete`,{method:'POST',body:JSON.stringify({simulated_minutes:selected.predicted_minutes})});notify(result.recommended_lesson?'Task complete. A matching micro-lesson is ready.':`Task complete. ${result.points_awarded} points awarded.`);spoken('Task complete. Return controls to neutral and confirm the area is safe.',1,notify);setSelected(null);await reload()}catch(e){notify(e.message)}finally{setBusy(false)}}
  const replay = `${selected?.site_instruction || ''} Use smooth control inputs. Watch the exclusion zone and stop if conditions change.`

  return <>
    <PageTitle eyebrow="Work plan" title="Today’s tasks"><div className="text-sm text-zinc-500">Ordered by dependency and priority</div></PageTitle>
    <div className="grid gap-5 xl:grid-cols-[1.5fr_1fr]">
      <section className="card p-5"><TaskList tasks={data.tasks} onOpen={setSelected}/></section>
      <section className="card h-fit p-5"><div className="label">Prediction method</div><h2 className="mt-1 text-lg font-semibold">Duration inputs</h2><div className="mt-4 space-y-3 text-sm"><div className="flex justify-between border-b pb-3"><span className="text-zinc-500">Machine</span><span>{data.machine.machine_type}, {data.machine.age_years} years</span></div><div className="flex justify-between border-b pb-3"><span className="text-zinc-500">Weather</span><span className="capitalize">{data.weather.condition}</span></div><div className="flex justify-between"><span className="text-zinc-500">Time</span><span>Planned start hour, IST</span></div></div><p className="mt-5 text-xs leading-5 text-zinc-500">No operator skill or operator efficiency field is used in the prediction.</p></section>
    </div>
    {selected&&<Modal title={selected.title} close={()=>setSelected(null)}>{selected.status==='in_progress'?<div>
      <div className="mb-4 border-l-4 border-cat bg-zinc-50 p-4"><div className="label">Work location and scope</div><div className="mt-1 font-semibold">{selected.site_instruction}</div></div>
      <Alert>Live synthetic sensor monitoring is active. If a hazard is detected, the machine will intervene and the event will be logged automatically.</Alert>
      <div className="flex flex-wrap gap-2"><button className="btn-quiet flex items-center gap-2" onClick={()=>spoken(replay,1,notify)}><Volume2 size={16}/> Replay instructions</button><button className="btn-quiet flex items-center gap-2" onClick={()=>window.speechSynthesis?.cancel()}><Square size={16}/> Stop speech</button></div>
      <button disabled={busy} className="btn-yellow mt-6 w-full" onClick={complete}>Complete task and award points</button>
    </div>:<div>
      <div className="mb-4 border-l-4 border-cat bg-zinc-50 p-4"><div className="label">Work location and scope</div><div className="mt-1 font-semibold">{selected.site_instruction}</div></div>
      <div className="mb-4 rounded-md border border-zinc-200 bg-zinc-50 p-4 text-sm"><div className="font-semibold">Site condition summary</div><div className="mt-1 text-zinc-600 capitalize">{data.weather.condition}, {Math.round(data.weather.temperature_c)}°C, wind {Math.round(data.weather.wind_kph)} km/h. Electrical cable clearance must be confirmed.</div></div>
      <div className="space-y-2">{[['brakes','Brakes respond correctly'],['fluids','Oil and fluid levels checked'],['seatbelt','Seatbelt and restraint checked'],['work_area_clear','Work area and blind spots clear'],['cable_clearance','Electrical cable clearance confirmed']].map(([key,label])=><label key={key} className="flex cursor-pointer items-center gap-3 rounded-md border border-zinc-200 p-3 text-sm"><input type="checkbox" className="h-4 w-4 accent-black" checked={checks[key]} onChange={e=>setChecks({...checks,[key]:e.target.checked})}/>{label}</label>)}</div>
      <button disabled={busy||!Object.values(checks).every(Boolean)} className="btn-yellow mt-5 w-full disabled:cursor-not-allowed disabled:opacity-40" onClick={start}>Start task and play instructions</button>
    </div>}</Modal>}
    {hazard&&<HazardPopup hazard={hazard} close={()=>setHazard(null)} />}
  </>
}
function HazardPopup({hazard,close}) { return <div className="fixed inset-0 z-[70] flex items-center justify-center bg-red-950/70 p-4" role="alertdialog" aria-modal="true"><div className="w-full max-w-md rounded-lg border-2 border-red-600 bg-white shadow-2xl"><div className="flex items-center gap-3 bg-red-700 px-5 py-4 text-white"><ShieldAlert size={26}/><div><div className="text-xs tracking-wider">SENSOR INTERVENTION</div><h2 className="text-lg font-semibold capitalize">{hazard.event_type.replaceAll('_',' ')}</h2></div></div><div className="p-5"><div className="text-sm font-semibold">{hazard.message}</div><div className="mt-3 rounded-md bg-red-50 p-3 text-sm text-red-950">{hazard.action}</div><div className="mt-4 flex justify-between text-xs text-zinc-500"><span>Sensor confidence {hazard.confidence}%</span><span>Incident auto-logged</span></div><button className="btn-primary mt-5 w-full" onClick={close}>I understand, continue safely</button></div></div></div> }
function Modal({title,children,close}) { return <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/55 p-4" role="dialog" aria-modal="true"><div className="card max-h-[90vh] w-full max-w-lg overflow-auto shadow-2xl"><div className="flex items-center justify-between border-b px-5 py-4"><h2 className="text-lg font-semibold">{title}</h2><button onClick={close} aria-label="Close"><X size={20}/></button></div><div className="p-5">{children}</div></div></div> }

function Training({operatorId,notify,reload}) {
  const [data,setData]=useState(null),[rate,setRate]=useState(1),[loadError,setLoadError]=useState('')
  const load=async()=>{try{setLoadError('');setData(await api(`/api/training/${operatorId}`))}catch(e){setLoadError(e.message);notify(e.message)}}
  useEffect(()=>{ load() },[operatorId])
  const complete=async lesson=>{try{const result=await api(`/api/training/${operatorId}/lessons/${lesson.id}/complete`,{method:'POST'});notify(result.message);spoken(result.message);await load();if(result.promoted)await reload()}catch(e){notify(e.message)}}
  return <><PageTitle eyebrow="Skills" title="Training hub"><select value={rate} onChange={e=>setRate(Number(e.target.value))} className="rounded-md border border-zinc-300 bg-white px-3 py-2 text-sm" aria-label="Narration speed"><option value=".75">0.75x voice</option><option value="1">1x voice</option><option value="1.25">1.25x voice</option></select></PageTitle>{loadError?<div className="card p-8 text-center"><AlertTriangle className="mx-auto text-red-600" size={36}/><h2 className="mt-4 font-semibold">Training could not load</h2><p className="mt-2 text-sm text-zinc-500">{loadError}</p><button className="btn-primary mt-5" onClick={load}>Try again</button></div>:!data?<Loading/>:data.lessons.length===0?<div className="card p-8 text-center"><Check className="mx-auto text-emerald-600" size={38}/><h2 className="mt-4 text-xl font-semibold">No assigned training</h2><p className="mx-auto mt-2 max-w-lg text-sm text-zinc-500">No training lessons are currently available.</p></div>:<><div className="mb-5 rounded-md border border-zinc-200 bg-white p-4 text-sm"><div className="font-semibold">{data.library_mode?'Completed lesson library':'Your training summary'}</div><div className="mt-1 text-zinc-600">{data.library_mode?'Your completed lessons remain available for review.':data.training_summary}</div></div><div className="grid gap-5 lg:grid-cols-2">{data.lessons.map((lesson,index)=><article className={classNames('card overflow-hidden',lesson.recommended&&'border-amber-500')} key={lesson.id}><div className="aspect-video bg-zinc-950"><iframe className="h-full w-full" src={lesson.video_url} title={lesson.title} allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" allowFullScreen/></div><div className="p-5"><div className="flex items-center justify-between gap-3"><div className="label">Level {index+1} of 2</div><div className="flex gap-2">{lesson.recommended&&<span className="status bg-amber-50 text-amber-800">Recommended from task</span>}<span className={classNames('status',lesson.completed?'bg-emerald-50 text-emerald-700':'bg-zinc-100 text-zinc-600')}>{lesson.completed?'Completed':'Required'}</span></div></div><h2 className="mt-2 text-xl font-semibold">{lesson.title}</h2>{lesson.recommendation_reason&&<div className="mt-3 border-l-4 border-cat bg-amber-50 p-3 text-xs text-amber-950">{lesson.recommendation_reason}.</div>}<p className="mt-3 text-sm leading-6 text-zinc-600">{lesson.narration}</p><div className="mt-5 flex gap-2"><button className="btn-quiet flex items-center gap-2" onClick={()=>spoken(lesson.narration,rate,notify)}><Headphones size={16}/> Play voice-over</button>{data.eligible&&!lesson.completed&&<button className="btn-yellow flex-1" onClick={()=>complete(lesson)}>Mark complete</button>}</div></div></article>)}</div></>}</>
}

function Safety({data,notify}) {
  const [incidents,setIncidents]=useState([]),[tickets,setTickets]=useState([]),[ticketOpen,setTicketOpen]=useState(false),[form,setForm]=useState({component:'',description:''})
  const load=()=>Promise.all([api(`/api/incidents?operator_id=${data.operator.id}`),api(`/api/tickets?operator_id=${data.operator.id}`)]).then(([a,b])=>{setIncidents(a);setTickets(b)}); useEffect(()=>{load().catch(e=>notify(e.message));const id=window.setInterval(()=>load().catch(e=>notify(e.message)),12000);return()=>window.clearInterval(id)},[data.operator.id])
  const trigger=async(type,severity='medium')=>{try{const labels={seatbelt:'Seatbelt is not fastened',speed_limit:'Site speed limit exceeded',rollover:'Unsafe machine angle detected',proximity:'Personnel detected in blind spot',drowsiness:'Drowsiness threshold crossed',electrical_cable:'Electrical cable clearance is unsafe',low_charge:'Machine charge is below the safe threshold',faulty_component:'Oil pressure or component condition is faulty'};const r=await api('/api/incidents',{method:'POST',body:JSON.stringify({operator_id:data.operator.id,machine_id:data.machine.machine_id,event_type:type,severity,details:labels[type]})});notify(r.auto_action);if(type==='drowsiness')spoken('Drowsiness alert. Slowing and stopping vehicle. Site authority has been alerted.');else spoken(`Safety warning. ${labels[type]}`);await load()}catch(e){notify(e.message)}}
  const ticket=async()=>{try{await api('/api/tickets',{method:'POST',body:JSON.stringify({...form,operator_id:data.operator.id,machine_id:data.machine.machine_id})});setTicketOpen(false);setForm({component:'',description:''});notify('Maintenance ticket created.');await load()}catch(e){notify(e.message)}}
  const items=[['seatbelt','Seatbelt',ShieldAlert],['speed_limit','Speed limit',Gauge],['rollover','Rollover risk',AlertTriangle],['proximity','Proximity',Activity],['drowsiness','Drowsiness',Clock3],['electrical_cable','Cable proximity',Activity],['low_charge','Low charge',Gauge],['faulty_component','Faulty component',Wrench]]
  return <><PageTitle eyebrow="Protection" title="Safety center"><button className="btn-yellow flex items-center gap-2" onClick={()=>setTicketOpen(true)}><Plus size={17}/> Report a defect</button></PageTitle><Alert>Active tasks are monitored automatically and unexpected sensor hazards appear as interventions. The controls below remain available for manual demo testing.</Alert><div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{items.map(([id,label,Icon])=><button key={id} className="card flex items-center gap-3 p-4 text-left hover:border-zinc-500" onClick={()=>trigger(id,id==='drowsiness'?'critical':'medium')}><div className="flex h-9 w-9 items-center justify-center rounded-md bg-zinc-100"><Icon size={18}/></div><div><div className="font-semibold">{label}</div><div className="mt-1 text-xs text-zinc-500">Manual test</div></div></button>)}</div><div className="mt-6 grid gap-5 xl:grid-cols-[1.4fr_1fr]"><section className="card overflow-hidden"><div className="border-b px-5 py-4"><h2 className="font-semibold">Incident log</h2></div><div className="max-h-96 divide-y overflow-auto">{incidents.length?incidents.map(i=><div key={i.id} className="p-4"><div className="flex items-center justify-between gap-4"><span className="font-semibold capitalize">{i.event_type.replaceAll('_',' ')}</span><span className={classNames('status',i.severity==='critical'?'bg-red-50 text-red-700':'bg-amber-50 text-amber-700')}>{i.severity}</span></div><p className="mt-1 text-sm text-zinc-600">{i.message}</p><div className="mt-2 text-xs text-zinc-400">{istDateTime(i.created_at)} IST {i.authority_alerted?'· Authority log created':''} {i.task_id?'· Auto-detected during task':''}</div></div>):<div className="p-8 text-center text-sm text-zinc-500">No incidents logged for this operator.</div>}</div></section><section className="card overflow-hidden"><div className="border-b px-5 py-4"><h2 className="font-semibold">Maintenance tickets</h2></div><div className="divide-y">{tickets.length?tickets.map(t=><div key={t.id} className="p-4"><div className="flex justify-between gap-3"><span className="font-semibold">{t.component}</span><span className="status bg-zinc-100 text-zinc-700">{t.status}</span></div><p className="mt-1 text-sm text-zinc-500">{t.description}</p></div>):<div className="p-8 text-center text-sm text-zinc-500">No tickets submitted.</div>}</div></section></div>{ticketOpen&&<Modal title="Report a machine defect" close={()=>setTicketOpen(false)}><label className="block text-sm font-semibold">Component<input value={form.component} onChange={e=>setForm({...form,component:e.target.value})} maxLength={80} className="mt-2 w-full rounded-md border border-zinc-300 p-2.5" placeholder="Example: hydraulic hose"/></label><label className="mt-4 block text-sm font-semibold">Description<textarea value={form.description} onChange={e=>setForm({...form,description:e.target.value})} maxLength={500} rows={4} className="mt-2 w-full resize-none rounded-md border border-zinc-300 p-2.5" placeholder="Describe the condition and where it was observed"/></label><button onClick={ticket} disabled={form.component.length<2||form.description.length<5} className="btn-yellow mt-5 w-full disabled:opacity-40">Submit ticket</button></Modal>}</>
}

function Efficiency({machine}) {
  const [period,setPeriod]=useState('week'),[data,setData]=useState(null),[models,setModels]=useState([]),[day,setDay]=useState(null)
  useEffect(()=>{if(!machine)return;api(`/api/metrics/machines/${machine.machine_id}?period=${period}`).then(setData);api('/api/model-metrics').then(setModels)},[machine?.machine_id,period])
  const average=useMemo(()=>data?.days?.length?data.days.reduce((a,x)=>a+x.efficiency,0)/data.days.length:0,[data])
  return <><PageTitle eyebrow="Machine only" title="Productivity and efficiency"><div className="flex gap-2"><button className={period==='week'?'btn-primary':'btn-quiet'} onClick={()=>setPeriod('week')}>7 days</button><button className={period==='month'?'btn-primary':'btn-quiet'} onClick={()=>setPeriod('month')}>30 days</button></div></PageTitle><div className="grid gap-4 sm:grid-cols-3"><Stat icon={Gauge} label="Average efficiency" value={`${average.toFixed(1)}%`} note={data?.formula || ''}/><Stat icon={ClipboardCheck} label="Latest completion" value={`${Math.round((data?.days.at(-1)?.completion_rate||0)*100)}%`} note="Completed machine tasks"/><Stat icon={Clock3} label="Latest idle time" value={minutes(data?.days.at(-1)?.idle_minutes)} note="From telemetry samples"/></div><section className="card mt-5 p-5"><div className="mb-5"><div className="label">Comparison</div><h2 className="mt-1 text-lg font-semibold">Daily machine efficiency</h2></div><div className="h-72"><ResponsiveContainer width="100%" height="100%"><LineChart data={data?.days||[]} onClick={state=>state?.activePayload&&setDay(state.activePayload[0].payload)}><CartesianGrid stroke="#e5e5e0" vertical={false}/><XAxis dataKey="day" tickFormatter={x=>x.slice(5)} fontSize={11}/><YAxis domain={[0,100]} fontSize={11}/><Tooltip/><Line type="monotone" dataKey="efficiency" stroke="#171717" strokeWidth={2} dot={{fill:'#ffcd11',stroke:'#171717',r:3}} activeDot={{r:6}}/></LineChart></ResponsiveContainer></div><p className="mt-3 text-xs text-zinc-500">Select a point to inspect the day. Formula: {data?.formula}.</p></section><section className="card mt-5 p-5"><div className="label">Model validation</div><h2 className="mt-1 text-lg font-semibold">Quality on noisy synthetic data</h2><div className="mt-4 grid gap-3 md:grid-cols-3">{models.map(m=><div className="rounded-md border border-zinc-200 p-4" key={m.model_name}><div className="font-semibold capitalize">{m.model_name.replaceAll('_',' ')}</div><div className="mt-1 text-xs text-zinc-500">Noise level {m.noise_level}</div><div className="mt-3 space-y-2">{Object.entries(m.metrics).map(([k,v])=><div key={k} className="flex justify-between text-xs"><span className="text-zinc-500">{k.replaceAll('_',' ')}</span><span className="font-semibold">{v}</span></div>)}</div></div>)}</div></section>{day&&<Modal title={`Machine metrics · ${day.day}`} close={()=>setDay(null)}><div className="grid grid-cols-2 gap-4"><Metric label="Efficiency" value={`${day.efficiency.toFixed(1)}%`}/><Metric label="Completion" value={`${Math.round(day.completion_rate*100)}%`}/><Metric label="Time score" value={`${Math.round(day.time_score*100)}%`}/><Metric label="Idle score" value={`${Math.round(day.idle_score*100)}%`}/><Metric label="Safety score" value={`${Math.round(day.safety_score*100)}%`}/><Metric label="Incidents" value={day.incident_count}/></div></Modal>}</>
}

function Assistant({operatorId,notify}) {
  const [question,setQuestion]=useState(''),[history,setHistory]=useState([]),[listening,setListening]=useState(false),[busy,setBusy]=useState(false),[voiceStatus,setVoiceStatus]=useState('')
  const [autoSpeak,setAutoSpeak]=useState(()=>localStorage.getItem('chatVoice')!=='off')
  const recognitionRef=useRef(null)
  useEffect(()=>()=>{try{recognitionRef.current?.stop()}catch{}},[])
  useEffect(()=>localStorage.setItem('chatVoice',autoSpeak?'on':'off'),[autoSpeak])
  const ask=async text=>{const q=(text||question).trim();if(!q)return;setBusy(true);try{const result=await api('/api/assistant/ask',{method:'POST',body:JSON.stringify({operator_id:operatorId,question:q})});setHistory(h=>[...h,{q,...result}]);setQuestion('');if(autoSpeak)spoken(result.answer,1,notify)}catch(e){notify(e.message)}finally{setBusy(false)}}
  const listen=async()=>{
    if(listening){recognitionRef.current?.stop();return}
    const Recognition=window.SpeechRecognition||window.webkitSpeechRecognition
    if(!Recognition){setVoiceStatus('Voice input needs Chrome or Edge. You can always type the question.');return}
    try{
      if(navigator.mediaDevices?.getUserMedia){const stream=await navigator.mediaDevices.getUserMedia({audio:true});stream.getTracks().forEach(track=>track.stop())}
      const r=new Recognition(); recognitionRef.current=r; r.lang='en-IN'; r.continuous=true; r.interimResults=true; r.maxAlternatives=1
      r.onstart=()=>{setListening(true);setVoiceStatus('Listening. Speak clearly, then press Stop listening.')}
      r.onresult=e=>{let finalText='', interim='';for(let i=e.resultIndex;i<e.results.length;i++){const text=e.results[i][0].transcript;if(e.results[i].isFinal)finalText+=text;else interim+=text}setQuestion(current=>finalText.trim()||interim.trim()||current)}
      r.onerror=e=>{const messages={not_allowed:'Microphone permission was denied.',no_speech:'No speech was detected. Move closer to the microphone and try again.',audio_capture:'No working microphone was found.',network:'Browser speech recognition could not reach its speech service.'};setVoiceStatus(messages[e.error]||`Voice input stopped: ${e.error}`)}
      r.onend=()=>{setListening(false);recognitionRef.current=null;setVoiceStatus(current=>current.startsWith('Listening')?'Transcript ready. Review it, then press Ask.':current)}
      r.start()
    }catch(e){setListening(false);setVoiceStatus(e.name==='NotAllowedError'?'Microphone permission was denied. Allow microphone access in the browser and retry.':'The microphone could not be started. You can type the question instead.')}
  }
  const escalate=async q=>{try{const r=await api('/api/assistant/escalate',{method:'POST',body:JSON.stringify({operator_id:operatorId,question:q})});notify(r.message)}catch(e){notify(e.message)}}
  return <><PageTitle eyebrow="Voice support" title="Machine assistant"><div className="flex flex-wrap items-center gap-2"><div className="flex items-center gap-2 text-xs text-zinc-500"><span className="h-2 w-2 bg-emerald-500"/> Manual and live RAG ready</div><button className="btn-quiet flex items-center gap-2 text-xs" onClick={()=>setAutoSpeak(v=>!v)}>{autoSpeak?<Volume2 size={15}/>:<VolumeX size={15}/>} Auto voice {autoSpeak?'on':'off'}</button></div></PageTitle><div className="mx-auto max-w-3xl"><div className="card min-h-96 overflow-hidden"><div className="border-b bg-zinc-50 px-5 py-4 text-sm text-zinc-600">Ask about safe operation, a machine warning, recent tasks, or machine efficiency. Safety answers use the complete synthetic operator manual before any model response.</div><div className="space-y-5 p-5">{history.length===0&&<div className="py-14 text-center"><Bot className="mx-auto text-zinc-300" size={44}/><h2 className="mt-4 font-semibold">How can I help in the field?</h2><p className="mt-2 text-sm text-zinc-500">Answers are grounded in the machine manual and local operating records.</p></div>}{history.map((item,i)=><div key={i}><div className="ml-auto max-w-[85%] rounded-md bg-ink px-4 py-3 text-sm text-white">{item.q}</div><div className="mt-3 max-w-[90%] rounded-md border border-zinc-200 bg-zinc-50 px-4 py-3"><p className="text-sm leading-6">{item.answer}</p>{item.automatic_actions&&<div className="mt-3 bg-red-700 p-3 text-xs text-white">Critical workflow completed. Supervisor contacted, incident #{item.automatic_actions.incident_id} logged, and maintenance ticket #{item.automatic_actions.ticket_id} opened.</div>}<div className="mt-3 flex flex-wrap items-center gap-2"><span className="text-[11px] text-zinc-400">{item.mode==='groq'?'Groq, constrained to retrieved context':item.mode==='verified_local'?'Verified manual answer':item.mode==='intent'?'Live app answer':'Offline grounded response'}</span>{item.sources?.map(source=><span key={source} className="rounded-sm bg-white px-1.5 py-0.5 text-[10px] text-zinc-500">{source}</span>)}<button className="text-xs font-semibold underline" onClick={()=>spoken(item.answer,1,notify)}>Replay</button>{!item.automatic_actions&&<button className="text-xs font-semibold underline" onClick={()=>escalate(item.q)}>Connect to supervisor</button>}</div></div></div>)}</div><div className="border-t p-4"><div className="flex gap-2"><input value={question} onChange={e=>setQuestion(e.target.value)} onKeyDown={e=>e.key==='Enter'&&ask()} maxLength={500} className="min-w-0 flex-1 rounded-md border border-zinc-300 px-3" placeholder="Describe your concern" aria-label="Question"/><button onClick={listen} className={classNames('btn-quiet flex items-center gap-2 px-3',listening&&'border-red-500 bg-red-50 text-red-700')} aria-label={listening?'Stop listening':'Speak question'}>{listening?<><Pause size={18}/><span className="hidden sm:inline">Stop</span></>:<Mic size={18}/>}</button><button disabled={busy||!question.trim()} onClick={()=>ask()} className="btn-yellow disabled:opacity-40">Ask</button></div>{voiceStatus&&<div className="mt-2 text-xs text-zinc-500">{voiceStatus}</div>}</div></div><p className="mt-3 text-center text-xs text-zinc-500">Turn on Hands-free in the top bar, then say “operator help” followed by your question. Voice input depends on Chrome or Edge microphone support.</p></div></>
}

function Profile({operator,machine,operators,select}) { return <><PageTitle eyebrow="Account" title="Operator profile"/><div className="grid gap-5 lg:grid-cols-[1fr_1.3fr]"><section className="card p-6"><div className="flex h-14 w-14 items-center justify-center rounded-md bg-cat"><UserRound size={28}/></div><h2 className="mt-4 text-2xl font-semibold">{operator.name}</h2><div className="mt-1 capitalize text-zinc-500">{operator.expertise} operator</div><div className="mt-6 grid grid-cols-2 gap-4 border-t pt-5"><Metric label="Points earned" value={operator.points}/><Metric label="Machine" value={machine?.machine_code||'Not assigned'}/></div></section><section className="card p-6"><h2 className="text-lg font-semibold">Demo operator</h2><p className="mt-1 text-sm text-zinc-500">No real authentication is used. Choose a profile to switch the active demo session.</p><div className="mt-5 space-y-2">{operators.map(o=><button key={o.id} className={classNames('flex w-full items-center justify-between rounded-md border p-4 text-left',o.id===operator.id?'border-ink bg-zinc-50':'border-zinc-200')} onClick={()=>select(o.id)}><div><div className="font-semibold">{o.name}</div><div className="mt-1 text-xs capitalize text-zinc-500">{o.expertise} · {o.points} points</div></div>{o.id===operator.id&&<Check size={18}/>}</button>)}</div><button className="btn-quiet mt-5 flex w-full items-center justify-center gap-2" onClick={()=>select(1)}><LogOut size={16}/> Reset to default operator</button></section></div></> }

export default App
