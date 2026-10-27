"""Per-hole observation, acknowledgement and retry; no operating-system input."""
from dataclasses import dataclass

@dataclass
class Hole:
    serial:int=0
    pending:bool=False
    confirmed:bool=False
    first_seen:float=0.
    last_good:float=0.
    last_click:float=-100.
    empty_frames:int=0
    hit_frames:int=0
    attempts:int=0
    last_state:str='empty'
    bomb_latched:bool=False

class TargetTracker:
    def __init__(self):
        self.holes=[Hole() for _ in range(9)]
        self.events=[]
        self.confirmed=0
        self.unverified=0
        self.blocked=0

    def observe(self,observations,now):
        actions=[];self.events=[]
        for o in observations:
            k=o['id'];h=self.holes[k];state=o['state']
            if state=='bomb':
                h.bomb_latched=True
                if h.last_state!='bomb':
                    self.blocked+=1
                    self.events.append(dict(event='bomb_blocked',hole=k))
                h.last_state='bomb';h.empty_frames=0
                continue
            if state=='hit':
                h.hit_frames+=1;h.empty_frames=0
                if h.pending and not h.confirmed and h.attempts and h.hit_frames>=2:
                    h.confirmed=True;self.confirmed+=1
                    self.events.append(dict(event='hit_confirmed',hole=k,target=h.serial,attempts=h.attempts,latency=round(now-h.first_seen,4)))
                h.last_state='hit'
                continue
            h.hit_frames=0
            if state in ('empty','transition'):
                h.empty_frames+=1
                if h.empty_frames>=3:
                    if h.pending and not h.confirmed:
                        self.unverified+=1
                        self.events.append(dict(event='target_disappeared_unverified',hole=k,target=h.serial,attempts=h.attempts))
                    h.pending=False;h.confirmed=False;h.attempts=0
                    h.bomb_latched=False
                h.last_state=state
                continue
            if state!='good':
                h.last_state=state
                continue
            if h.bomb_latched:
                h.last_state='bomb'
                continue
            h.empty_frames=0
            if not h.pending or (h.confirmed and h.last_state in ('hit','empty') and now-h.last_click>.16):
                h.serial+=1;h.pending=True;h.confirmed=False;h.first_seen=now;h.attempts=0;h.last_click=-100.
                self.events.append(dict(event='target_seen',hole=k,target=h.serial))
            h.last_good=now;h.last_state='good'
            if h.confirmed:continue
            # First shot immediately. A still-visible unacknowledged target is
            # retried; later stages do not inherit a slow fixed cooldown.
            delay=.065 if h.attempts<3 else .10
            if now-h.last_click>=delay:
                actions.append(dict(o,target=h.serial,first_seen=h.first_seen,attempt=h.attempts+1))
        return sorted(actions,key=lambda a:(a['first_seen'],-a.get('good_probability',0)))

    def clicked(self,action,now):
        h=self.holes[action['id']];h.last_click=now;h.attempts+=1
