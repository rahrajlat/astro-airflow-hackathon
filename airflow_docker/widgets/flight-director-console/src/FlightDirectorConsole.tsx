import { useCallback, useEffect, useRef, useState } from "react";

type DagRun = { dag_run_id: string; state: string };
type TaskInstance = { task_id: string; task_display_name?: string; state?: string | null };
type HitlDetail = {
  task_instance: { dag_id: string; dag_run_id: string; task_id: string; map_index: number };
  subject: string;
  body?: string | null;
  options: string[];
};
type ApiError = { detail?: string | { message?: string } };

const DAG_ID = "planet_exploration_rover";
const HITL_TASK_ID = "flight_director_decision";
const POLL_MS = 3000;
const labels: Record<string, string> = {
  turn_left_then_move_five: "Turn left",
  turn_right_then_move_five: "Turn right",
  move_backward_five: "Reverse",
  return_to_base_now: "Return to base",
  abort_and_hold_position: "Abort / hold",
};

const list = <T,>(payload: unknown, keys: string[]): T[] => {
  if (!payload || typeof payload !== "object") return [];
  const record = payload as Record<string, unknown>;
  for (const key of keys) if (Array.isArray(record[key])) return record[key] as T[];
  return [];
};

const apiError = async (response: Response, fallback: string) => {
  try {
    const payload = (await response.json()) as ApiError;
    return typeof payload.detail === "string" ? payload.detail : payload.detail?.message ?? fallback;
  } catch { return fallback; }
};

const bodyValue = (body: string, label: string) => {
  const escaped=label.replace(/[.*+?^${}()|[\]\\]/g,"\\$&");
  return body.match(new RegExp(`\\|\\s*${escaped}\\s*\\|\\s*\\*{0,2}([^|*]+)`,"i"))?.[1]?.trim();
};

export const FlightDirectorConsole = () => {
  const rootRef = useRef<HTMLElement>(null);
  const [run, setRun] = useState<DagRun>();
  const [tasks, setTasks] = useState<TaskInstance[]>([]);
  const [hitl, setHitl] = useState<HitlDetail>();
  const [selected, setSelected] = useState<string>();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string>();

  const refresh = useCallback(async () => {
    const options = { credentials: "same-origin" as RequestCredentials, headers: { Accept: "application/json" } };
    try {
      const [runsResponse, hitlResponse] = await Promise.all([
        fetch(`/api/v2/dags/${DAG_ID}/dagRuns?limit=1&order_by=-logical_date`, options),
        fetch(`/api/v2/dags/${DAG_ID}/dagRuns/~/hitlDetails?response_received=false&limit=10`, options),
      ]);
      if (!runsResponse.ok) throw new Error(await apiError(runsResponse, "Unable to read latest run"));
      if (!hitlResponse.ok) throw new Error(await apiError(hitlResponse, "Unable to read approvals"));
      const latest = list<DagRun>(await runsResponse.json(), ["dag_runs", "dagRuns"])[0];
      const pending = list<HitlDetail>(await hitlResponse.json(), ["hitl_details", "hitlDetails"])
        .find((item) => item.task_instance.task_id === HITL_TASK_ID);
      let latestTasks: TaskInstance[] = [];
      if (latest) {
        const response = await fetch(`/api/v2/dags/${DAG_ID}/dagRuns/${encodeURIComponent(latest.dag_run_id)}/taskInstances?limit=100`, options);
        if (!response.ok) throw new Error(await apiError(response, "Unable to read task status"));
        latestTasks = list<TaskInstance>(await response.json(), ["task_instances", "taskInstances"]);
      }
      setRun(latest); setTasks(latestTasks); setHitl(pending); setError(undefined);
      if (!pending) setSelected(undefined);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Airflow unavailable"); }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), POLL_MS);
    return () => clearInterval(timer);
  }, [refresh]);

  const submit = async () => {
    if (!hitl || !selected || submitting) return;
    const task = hitl.task_instance;
    setSubmitting(true); setError(undefined);
    try {
      const response = await fetch(`/api/v2/dags/${encodeURIComponent(task.dag_id)}/dagRuns/${encodeURIComponent(task.dag_run_id)}/taskInstances/${encodeURIComponent(task.task_id)}/${task.map_index ?? -1}/hitlDetails`, {
        method: "PATCH", credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ chosen_options: [selected], params_input: {} }),
      });
      if (!response.ok) throw new Error(await apiError(response, "Airflow rejected the response"));
      setHitl(undefined); setSelected(undefined);
      window.setTimeout(() => void refresh(), 500);
    } catch (caught) { setError(caught instanceof Error ? caught.message : "Unable to submit response"); }
    finally { setSubmitting(false); }
  };

  const body = hitl?.body ?? "";
  const image=body.match(/\/flight-director-api\/rover-captures\/([^)\s]+)/)?.[0];
  const visualEvidence=body.match(/>\s*\*\*Visual evidence:\*\*\s*(.+)/i)?.[1]?.trim();
  return <main ref={rootRef} className="screen"><style>{styles}{evidenceStyles}</style>
    <header><div><small>DAGSTRONAUT</small><b>Planet Exploration Rover</b></div><button onClick={() => void(document.fullscreenElement ? document.exitFullscreen() : rootRef.current?.requestFullscreen())}>⛶</button></header>
    {hitl ? <section className="approval">
      <h1>Approval required</h1><p>{hitl.subject}</p>
      <div className="decision-layout">
        <div className="camera-panel">{image?<img src={image} alt="Obstacle captured by the rover"/>:<div>No camera image</div>}<span>ROVER CAMERA</span></div>
        <div className="decision-panel">
          <small>AI ASSESSMENT</small>
          <h2>{bodyValue(body,"Predicted object")??"Unknown obstruction"}</h2>
          <div className="facts"><span>Distance <b>{bodyValue(body,"Obstacle distance")??"—"}</b></span><span>Confidence <b>{bodyValue(body,"Confidence")??"—"}</b></span></div>
          <div className="visual-evidence"><small>VISUAL EVIDENCE</small><p>{visualEvidence??"No visual explanation was provided."}</p></div>
          <div className="recommend"><small>RECOMMENDED ACTION</small><strong>{bodyValue(body,"AI recommendation")??"Review manually"}</strong><em>AI advice only — a human must authorize movement.</em></div>
          <div className="choices">{hitl.options.filter(option=>labels[option]).map(option=><button className={selected===option?"selected":""} onClick={()=>setSelected(option)} key={option}><i/>{labels[option]}</button>)}</div>
          <button className="submit" disabled={!selected||submitting} onClick={()=>void submit()}>{submitting?"Submitting…":selected?`Authorize ${labels[selected]}`:"Select an action"}</button>
        </div>
      </div>
    </section> : (!run||!["running","queued"].includes(run.state)) ? <section className="empty-state">
      <div className="signal-orbit"><i/><span>◎</span></div>
      <h1>No Rover Missions in progress</h1>
    </section> : <section className="monitor">
      <div className="run"><small>MOST RECENT RUN</small><h1>{run?run.state.replaceAll("_"," "):"No runs"}</h1><p>{run?.dag_run_id??"Trigger the DAG to begin."}</p></div>
      <div className="tasks">{tasks.map(task=><div className={`task ${task.state??"none"}`} key={task.task_id}><i/><span>{(task.task_display_name??task.task_id).replaceAll("_"," ")}</span><b>{(task.state??"pending").replaceAll("_"," ")}</b></div>)}</div>
    </section>}
    {error&&<div className="error">{error}</div>}
  </main>;
};

const styles=`
*{box-sizing:border-box}html,body{margin:0;background:#0b0c12}.screen{width:100%;height:calc(100vh - 70px);min-height:380px;padding:14px;background:#10121b;color:#f4f5f8;font-family:Arial,sans-serif}.screen:fullscreen{width:100vw;height:100vh}.screen header{height:42px;display:flex;justify-content:space-between;border-bottom:1px solid #303342}.screen header small,.screen header b{display:block}.screen header small{color:#55d9ff;font-size:7px;font-weight:900;letter-spacing:.16em}.screen header b{margin-top:3px;font-size:13px}.screen header button{height:27px;border:1px solid #3a3d4b;border-radius:3px;background:#20232f;color:#fff}.monitor,.approval,.empty-state{height:calc(100% - 42px);padding-top:12px}.approval{overflow:auto;padding-bottom:8px}.empty-state{display:grid;place-content:center;justify-items:center;text-align:center}.empty-state h1{margin:25px 0 0;color:#bbc0cc;font-size:20px;font-weight:500}.signal-orbit{position:relative;display:grid;width:115px;height:115px;place-items:center;border:1px solid #55d9ff44;border-radius:50%;animation:float 4s ease-in-out infinite}.signal-orbit:before,.signal-orbit:after{content:'';position:absolute;border-radius:50%}.signal-orbit:before{inset:14px;border:1px dashed #55d9ff77;animation:spin 16s linear infinite}.signal-orbit:after{inset:31px;border:1px solid #55d9ff33;box-shadow:0 0 28px #55d9ff1f}.signal-orbit>i{position:absolute;z-index:2;top:10px;width:8px;height:8px;border-radius:50%;background:#55d9ff;box-shadow:0 0 12px #55d9ff;animation:breathe 2.5s ease-in-out infinite}.signal-orbit>span{color:#55d9ff;font-size:34px}.run{padding:12px;border:1px solid #343746;border-radius:5px;background:#1b1e29}.run small{color:#7e8394;font-size:7px;font-weight:900;letter-spacing:.15em}.run h1{margin:4px 0;font-size:25px;text-transform:uppercase}.run p{margin:0;overflow:hidden;color:#9499a8;font:7px ui-monospace,monospace;text-overflow:ellipsis;white-space:nowrap}.tasks{height:calc(100% - 98px);margin-top:7px;overflow:auto}.task{display:grid;grid-template-columns:8px 1fr auto;gap:8px;align-items:center;padding:7px 9px;border-bottom:1px solid #292c38;color:#9ba0ae;font-size:8px;text-transform:uppercase}.task i{width:7px;height:7px;border-radius:50%;background:#555a69}.task b{font-size:7px}.task.success{color:#70dfa0}.task.success i{background:#5dde95}.task.running,.task.queued,.task.scheduled,.task.deferred,.task.awaiting_input{color:#63dbfa}.task.running i,.task.queued i,.task.scheduled i,.task.deferred i,.task.awaiting_input i{background:#4bd9ff}.task.failed{color:#ff8583}.task.failed i{background:#ff625f}.task.skipped{opacity:.45}.approval>h1{margin:0;color:#ffd466;font-size:25px}.approval>p{margin:4px 0 8px;color:#a9adba;font-size:8px}.decision-layout{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(250px,1fr);gap:8px}.camera-panel{position:relative;min-height:275px;overflow:hidden;border:1px solid #3a3e4e;border-radius:5px;background:#171923}.camera-panel>img{width:100%;height:100%;object-fit:cover}.camera-panel>div{display:grid;height:100%;place-items:center;color:#777c8d;font-size:9px}.camera-panel>span{position:absolute;left:7px;bottom:7px;padding:4px 6px;background:#090a10d9;color:#67ddff;font-size:6px;font-weight:900}.decision-panel{padding:10px;border:1px solid #3a3e4e;border-radius:5px;background:#1b1e29}.decision-panel>small{color:#62dcff;font-size:6px;font-weight:900;letter-spacing:.15em}.decision-panel h2{margin:4px 0 8px;font-size:20px;text-transform:capitalize}.facts{display:grid;grid-template-columns:1fr 1fr;gap:5px}.facts span{padding:6px;border:1px solid #343847;color:#858a9b;font-size:7px}.facts b{float:right;color:#fff}.recommend{margin-top:6px;padding:7px 8px;border-left:3px solid #ffd466;background:#302b1d}.recommend small,.recommend strong,.recommend em{display:block}.recommend small{color:#ffd466;font-size:6px;font-weight:900;letter-spacing:.12em}.recommend strong{margin-top:3px;font-size:11px;text-transform:uppercase}.recommend em{margin-top:3px;color:#969181;font-size:6px;font-style:normal}.choices{display:grid;grid-template-columns:1fr 1fr;gap:5px;margin-top:7px}.choices button{min-height:34px;display:flex;gap:6px;align-items:center;border:1px solid #414554;border-radius:4px;background:#252833;color:#daddE5;padding:6px 8px;font-size:8px;text-align:left}.choices button i{width:7px;height:7px;flex:none;border:1px solid #777c8c;border-radius:50%}.choices button.selected{border-color:#55d9ff;background:#173b49;color:#fff}.choices button.selected i{border-color:#55d9ff;background:#55d9ff;box-shadow:0 0 7px #55d9ff}.submit{width:100%;height:36px;margin-top:6px;border:0;border-radius:4px;background:#3fbd78;color:#07150e;font-size:8px;font-weight:900;text-transform:uppercase}.submit:disabled{background:#292c37;color:#656977}.approval details{margin-top:7px;border:1px solid #343847;border-radius:4px;background:#171923}.approval summary{padding:7px 9px;color:#858a9a;font-size:7px;cursor:pointer}.markdown{margin:0 7px 7px;padding:8px 10px;border:1px solid #383b49;border-radius:4px;background:#1b1e29;font-size:8px;line-height:1.4}.markdown h1,.markdown h2,.markdown h3{margin:9px 0 4px;color:#f4f5f8}.markdown h1{font-size:14px}.markdown h2{font-size:12px}.markdown h3{font-size:10px}.markdown p{margin:4px 0}.markdown a{color:#55d9ff}.markdown code{padding:1px 3px;background:#10121b;color:#8ce5ff}.markdown blockquote{margin:7px 0;padding:6px 8px;border-left:3px solid #ffd466;background:#2b291f}.markdown table{width:100%;margin:6px 0;border-collapse:collapse}.markdown th,.markdown td{padding:4px 5px;border:1px solid #383c4a;text-align:left}.markdown th{color:#8ce5ff}.md-image{display:block;width:100%;max-height:145px;margin:5px 0;border-radius:3px;object-fit:cover}.error{position:absolute;left:14px;right:14px;bottom:10px;padding:7px;border:1px solid #74343b;background:#461f26;color:#ffaaaa;font-size:8px;text-align:center}@keyframes breathe{50%{opacity:.35;transform:scale(.75);box-shadow:0 0 3px #55d9ff}}@keyframes spin{to{transform:rotate(360deg)}}@keyframes float{50%{transform:translateY(-7px)}}@media(max-height:440px){.screen{height:100vh;padding:9px}.screen header{height:35px}.monitor,.approval,.empty-state{height:calc(100% - 35px);padding-top:7px}.approval>h1{font-size:19px}.approval>p{margin-bottom:5px}.decision-layout{grid-template-columns:1.1fr 1fr}.camera-panel{min-height:250px}.decision-panel{padding:7px}.decision-panel h2{font-size:15px}.choices button{min-height:29px}.submit{height:31px}.run{padding:8px}.run h1{font-size:20px}.tasks{height:calc(100% - 77px)}.task{padding:5px 8px}}@media(max-width:550px){.decision-layout{grid-template-columns:1fr}.camera-panel{min-height:180px}.choices{grid-template-columns:1fr 1fr}}@media(prefers-reduced-motion:reduce){.signal-orbit,.signal-orbit:before,.signal-orbit>i{animation:none}}`;

const evidenceStyles=`.visual-evidence{margin-top:6px;padding:6px 8px;border:1px solid #343847;background:#171923}.visual-evidence small{color:#62dcff;font-size:6px;font-weight:900;letter-spacing:.12em}.visual-evidence p{max-height:42px;margin:3px 0 0;overflow:auto;color:#b8bcc8;font-size:7px;line-height:1.35}`;
