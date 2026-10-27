"""Read the two entry counters and plan a single, quantity-checked start."""
from pathlib import Path
import sys,re
from collections import Counter
from dataclasses import dataclass
import cv2
import numpy as np

NAMES={'luxury':'豪华保卫','normal':'普通保卫'}
HAMMERS={'luxury':'豪华锤','normal':'普通锤'}

class EntryError(RuntimeError):pass
class HammerInsufficient(EntryError):
    def __init__(self,mode):
        self.mode=mode
        super().__init__(f'{HAMMERS[mode]}数量不足，无法开始{NAMES[mode]}。')

@dataclass
class EntryState:
    counts:dict
    buttons:dict
    confidence:dict

class EntryReader:
    def __init__(self):
        root=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'assets'
        z=np.load(root/'hammer_digits.npz');self.prototypes=z['images'];self.labels=z['labels']
        self.templates={}
        for mode in NAMES:
            self.templates[mode]=cv2.imdecode(np.fromfile(root/f'entry_{mode}.png',np.uint8),0)

    def text(self,rgb,x0,x1,dy):
        a=cv2.cvtColor(rgb[69+dy:78+dy,x0:x1],cv2.COLOR_RGB2HSV)
        m=((a[:,:,1]<100)&(a[:,:,2]>200)).astype(np.uint8)
        stats=cv2.connectedComponentsWithStats(m,8)[2]
        boxes=sorted([tuple(z[:4]) for z in stats[1:] if z[3]>=5 and z[2]>=2 and z[4]>=6])
        if not boxes:return None,0.
        chars=[];scores=[]
        for x,y,w,h in boxes:
            v=np.r_[cv2.resize(m[y:y+h,x:x+w].astype(np.float32),(16,20)).reshape(-1),w/h]
            errors=np.mean((self.prototypes[:,:320]-v[:320])**2,axis=1)+.12*(self.prototypes[:,320]-v[320])**2
            k=int(np.argmin(errors));score=1-float(errors[k])
            if score<.80:return None,score
            chars.append(str(self.labels[k]));scores.append(score)
        return ''.join(chars),min(scores)

    def read(self,rgb):
        h,w=rgb.shape[:2]
        image=cv2.resize(rgb,(327,round(h*327/w)),interpolation=cv2.INTER_AREA)
        if image.shape[0]<575:raise EntryError('请完整显示蔬果保卫战入口后重试。')
        gray=cv2.cvtColor(image,cv2.COLOR_RGB2GRAY);buttons={};confidence={}
        for mode,(x0,x1) in {'luxury':(5,165),'normal':(163,325)}.items():
            region=gray[480:566,x0:x1];best=None
            for s in (.94,1.,1.06):
                t=cv2.resize(self.templates[mode],None,fx=s,fy=s)
                _,score,_,(x,y)=cv2.minMaxLoc(cv2.matchTemplate(region,t,cv2.TM_CCOEFF_NORMED))
                if best is None or score>best[0]:best=(score,x+x0,y+480,t.shape[1],t.shape[0])
            score,x,y,tw,th=best
            if score<.76 or float(image[y:y+th,x:x+tw].max(axis=2).mean())<150:
                raise EntryError('请先打开蔬果保卫战入口，再选择保卫方式。')
            buttons[mode]=(x+tw/2,y+th/2);confidence[mode]=float(score)
        counts={}
        for mode,(x0,x1) in {'luxury':(117,147),'normal':(188,235)}.items():
            choices=[]
            for dy in (0,-1,1,-2,2):
                text,score=self.text(image,x0,x1,dy)
                if text is None:continue
                pattern=r'([0-9]{1,3})' if mode=='luxury' else r'([0-9]{1,2})/10'
                match=re.fullmatch(pattern,text)
                if match:choices.append((score,int(match.group(1))))
            if not choices:raise EntryError('未能确认锤子数量，请保持游戏窗口无遮挡后重试。')
            score,value=max(choices);counts[mode]=value;confidence[mode+'_count']=float(score)
        return EntryState(counts,buttons,confidence)

def checked_start(mode,reader,desktop,cancel,on_counts=lambda counts:None):
    """Desktop is injected so zero-stock behavior can be tested without input."""
    if mode not in NAMES:raise EntryError('请选择保卫方式。')
    desktop.focus(cancel)
    states=[]
    for _ in range(3):
        if cancel.is_set():return None
        rect,rgb=desktop.capture();states.append((rect,reader.read(rgb)))
        if cancel.wait(.065):return None
    latest_rect,latest=states[-1]
    values={}
    for key in NAMES:
        count,n=Counter(s.counts[key] for _,s in states).most_common(1)[0]
        if n<2:raise EntryError('锤子数量正在变化，请稍后重试。')
        values[key]=count
    on_counts(values)
    if values[mode]<=0:raise HammerInsufficient(mode)
    # Fresh evidence just before input prevents a stale quantity/page check.
    rect,rgb=desktop.capture();fresh=reader.read(rgb)
    if rect!=latest_rect:raise EntryError('游戏窗口已移动，请重新点击保卫按钮。')
    on_counts(fresh.counts)
    if fresh.counts[mode]<=0:raise HammerInsufficient(mode)
    if cancel.is_set():return None
    desktop.click(fresh.buttons[mode],rect,cancel)
    return fresh
