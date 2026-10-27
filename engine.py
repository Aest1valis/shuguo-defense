"""Run one session, acknowledge each hole and hold until the reward scene ends."""
import json,sys,time,collections
from pathlib import Path
from datetime import datetime
from ctypes import wintypes
import numpy as np
from PIL import Image
from tracker import TargetTracker
from results import ResultReader,StableResult

def initial_reward_seconds(votes):
    valid=[v for v,c in votes.items() if c>=2]
    # Use the stable majority, not the largest occasional OCR outlier.
    return max(valid,key=lambda v:(votes[v],v)) if valid else None

def run_engine(app,hwnd,mode,cancel,user32,bounds,release,grabber_factory,start_timeout=None):
    base=Path(sys.executable if getattr(sys,'frozen',False) else __file__).parent
    folder=base/'runs'/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-v2')
    folder.mkdir(parents=True,exist_ok=True)
    trace=(folder/'events.jsonl').open('w',encoding='utf-8',buffering=65536)
    begin=time.monotonic();tracker=TargetTracker();grabber=None
    clicked=0;held=False;hold_start=None;hold_segments=[];seen=False
    absent=None;stable=0;frame_no=0;last_image=-1.
    phase=1;phase_candidate=1;phase_votes=0;full_badges=set();phase_changes=[]
    reward_votes=collections.Counter();reward_first=None;reward_zero=False
    saved=None;last_result=None;model_times=[];capture_times=[];loop_times=[]
    reason='stopped'
    result_reader=ResultReader();settlement=StableResult();settled=None
    def record(event,**data):
        trace.write(json.dumps(dict(t=round(time.monotonic()-begin,4),event=event,**data),ensure_ascii=False)+'\n')
    def up(why):
        nonlocal held,hold_start
        if held:
            release();held=False
            duration=time.monotonic()-hold_start
            hold_segments.append(round(duration,4));record('hold_end',reason=why,duration=round(duration,4))
    try:
        if hasattr(app.detector,'reset_session'):app.detector.reset_session()
        grabber=grabber_factory()
        while not cancel.is_set() and not app.closed.is_set():
            now=time.monotonic();loop_start=time.perf_counter()
            if now-begin>600:reason='ten_minute_limit';break
            if start_timeout and not seen and now-begin>start_timeout:
                reason='start_not_confirmed';app.send(('entry_error','未能确认已开局，请回到入口后重试。'));break
            point=wintypes.POINT();user32.GetCursorPos(__import__('ctypes').byref(point))
            if mode!='preview' and point.x<=8 and point.y<=8:reason='corner_stop';break
            if mode!='preview' and user32.GetAsyncKeyState(0x1B)&0x8000:reason='escape';break
            rect=bounds(hwnd)
            if user32.GetForegroundWindow()!=hwnd:
                up('focus_lost')
                if seen:reason='focus_lost';break
                cancel.wait(.04);continue
            t=time.perf_counter();rgb=grabber.grab(rect);capture_times.append((time.perf_counter()-t)*1000)
            result=app.detector.detect(rgb);last_result=result;frame_no+=1
            model_times.append(result.get('model_ms',0.))
            ui=result.get('ui',{})
            # Save 20 fps evidence; every inference remains in the JSON trace.
            if now-last_image>=.05 or ui.get('full_hit_badge'):
                saved=f'{frame_no:06d}.jpg';Image.fromarray(result['image']).save(folder/saved,quality=86)
                last_image=now
            else:saved=None
            record('frame',file=saved,active=result['active'],scene=result.get('scene'),
                   holes=result.get('holes',[]),targets=result['targets'],bombs=result.get('bombs',[]),
                   hold=result['hold'],ui=ui,model_ms=round(result.get('model_ms',0),3))
            stable=stable+1 if result['active'] else 0
            if result['active']:
                absent=None
                if stable>=2 and not seen:
                    seen=True;record('game_started');app.send(('status','已进入局内，逐洞确认命中；Esc 停止。'))
                    app.send(('started',None))
                n=ui.get('stage')
                if n in (phase,phase+1) and ui.get('stage_score',0)>.80:
                    phase_votes=phase_votes+1 if n==phase_candidate else 1;phase_candidate=n
                    if n>phase and phase_votes>=3:
                        phase=n;phase_changes.append(dict(stage=n,t=round(now-begin,3)))
                        record('stage_started',stage=n)
                        app.send(('status',f'第 {n} 阶段：逐洞跟踪，等待命中确认。'))
                        app.send(('phase',n))
                if ui.get('full_hit_badge') and phase not in full_badges:
                    full_badges.add(phase);record('game_full_hit_badge',stage=phase,file=saved)
                if ui.get('reward_label'):
                    if reward_first is None:reward_first=now;record('reward_started',stage=phase)
                    value=ui.get('timer')
                    if value is not None and ui.get('timer_score',0)>.83:
                        if now-reward_first<1.2:reward_votes[int(value)]+=1
                        if value==0:reward_zero=True
            elif seen:
                up('reward_or_game_scene_ended')
                if absent is None:absent=now
                candidate=result_reader.read(rgb)
                settlement.observe(candidate,now)
                if candidate:record('settlement_observation',**candidate)
                if now-absent>.90 and settlement.ready(now):
                    settled=dict(settlement.value)
                    reason='game_scene_ended';break
                if now-absent>3:
                    reason='game_scene_ended';break
            if mode=='preview' or stable<2:
                up('inactive_or_preview');cancel.wait(.003);continue
            if bounds(hwnd)!=rect or user32.GetForegroundWindow()!=hwnd:continue
            scale=(rect[2]-rect[0])/327.
            if result['hold']:
                a=result['hold'];x=round(rect[0]+a['x']*scale);y=round(rect[1]+a['y']*scale)
                over=user32.WindowFromPoint(wintypes.POINT(x,y))
                if user32.GetAncestor(over,2)!=hwnd:
                    up('covered');cancel.wait(.01);continue
                if not held and not cancel.is_set():
                    user32.SetCursorPos(x,y);user32.mouse_event(2,0,0,0,0)
                    held=True;hold_start=time.monotonic();record('hold_start',x=a['x'],y=a['y'])
                    app.send(('status','狂热奖励：持续按住，直到奖励画面结束。'))
                    app.send(('reward',None))
                # No fixed 12-second timeout. A 4-stage perfect reward may run longer.
            else:
                up('left_reward_scene')
                observations=result.get('holes',[])
                if not observations and result['targets']:
                    observations=[dict(a,id=i,state='good') for i,a in enumerate(result['targets'][:9])]
                actions=tracker.observe(observations,now)
                for e in tracker.events:
                    event=e.pop('event');record(event,**e)
                for a in actions:
                    if cancel.is_set() or app.closed.is_set():break
                    if bounds(hwnd)!=rect or user32.GetForegroundWindow()!=hwnd:break
                    x=round(rect[0]+a['x']*scale);y=round(rect[1]+a['y']*scale)
                    if user32.GetAncestor(user32.WindowFromPoint(wintypes.POINT(x,y)),2)!=hwnd:continue
                    user32.SetCursorPos(x,y);user32.mouse_event(2,0,0,0,0)
                    try:cancel.wait(.010)
                    finally:release()
                    clicked+=1;tracker.clicked(a,time.monotonic())
                    record('click',hole=a['id'],target=a['target'],attempt=a['attempt'],
                           x=a['x'],y=a['y'],age_ms=round((time.monotonic()-a['first_seen'])*1000,2))
            loop_times.append((time.perf_counter()-loop_start)*1000)
            cancel.wait(.002)
    except Exception as e:
        reason='error:'+str(e);app.send(('status','已停止：'+str(e)));record('error',message=str(e))
    finally:
        up(reason)
        if grabber:grabber.close()
        initial=initial_reward_seconds(reward_votes)
        summary=dict(format_version=2,reason=reason,stage_count=phase,stage_full_badges=sorted(full_badges),
                     reward_initial_seconds=initial,expected_perfect_reward_seconds=3*phase,
                     game_verified_all_stages_full=bool(initial==3*phase and seen),
                     reward_reached_zero=reward_zero,hold_segments=hold_segments,
                     continuous_reward_press=len(hold_segments)==1,
                     clicks=clicked,hit_animations_confirmed=tracker.confirmed,
                     targets_disappeared_unverified=tracker.unverified,bomb_episodes_blocked=tracker.blocked,
                     frame_count=frame_no,stage_changes=phase_changes,
                     model_ms_median=float(np.median(model_times)) if model_times else None,
                     loop_ms_p95=float(np.percentile(loop_times,95)) if loop_times else None)
        summary.update(score=settled['score'] if settled else None,
                       fruit_coins=settled['fruit_coins'] if settled else None,
                       settlement_confidence=settled['confidence'] if settled else None,
                       settlement_read=settled is not None)
        if last_result is not None:Image.fromarray(last_result['image']).save(folder/'last_frame.png')
        (folder/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
        record('end',**summary);trace.close();cancel.set()
        if reason=='game_scene_ended':
            proof='游戏奖励时长验证全阶段全中' if summary['game_verified_all_stages_full'] else '阶段全中尚未全部验证'
            app.send(('status',f'已停止：{phase} 阶段，狂热 {initial} 秒；{proof}。'))
            app.send(('complete',summary))
