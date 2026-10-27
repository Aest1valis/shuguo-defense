from pathlib import Path
import sys
import cv2
import numpy as np

def glyph(rgb):
    h=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV)
    m=((h[:,:,2]>205)&(h[:,:,1]>70)&(h[:,:,0]<45)).astype(np.uint8)
    num,lab,stats,_=cv2.connectedComponentsWithStats(m,8)
    ids=[i for i in range(1,num) if stats[i,4]>12]
    if not ids:return None
    k=max(ids,key=lambda i:stats[i,4]);x,y,w,h=stats[k,:4]
    return cv2.resize((lab[y:y+h,x:x+w]==k).astype(np.float32),(24,32)).reshape(-1)

class UIReader:
    def __init__(self):
        self.root=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'assets'
        z=np.load(self.root/'ui_digits.npz');self.digits=z['images'];self.labels=z['labels']
        self.stages=[]
        for n in range(1,5):
            im=cv2.imdecode(np.fromfile(self.root/f'stage{n}.png',np.uint8),1)
            self.stages.append(glyph(cv2.cvtColor(im,cv2.COLOR_BGR2RGB)))
        self.badge=cv2.imdecode(np.fromfile(self.root/'full_hit_badge.png',np.uint8),0)
        self.reward_label=cv2.imdecode(np.fromfile(self.root/'reward_label.png',np.uint8),0)

    def read(self,rgb):
        stage=None;stage_score=0.
        g=glyph(rgb[74:103,150:179])
        if g is not None:
            errors=[float(np.mean((g-a)**2)) if a is not None else 1. for a in self.stages]
            i=int(np.argmin(errors));stage_score=1-errors[i]
            if errors[i]<.32:stage=i+1
        hsv=cv2.cvtColor(rgb[210:217,74:108],cv2.COLOR_RGB2HSV)
        m=((hsv[:,:,2]>205)&(hsv[:,:,1]<175)).astype(np.uint8)
        stats=cv2.connectedComponentsWithStats(m,8)[2]
        boxes=sorted([tuple(z[:4]) for z in stats[1:] if z[3]>=4 and z[2]>=2])
        seconds=None;timer_score=0.
        if len(boxes)==4:
            values=[];scores=[]
            for x,y,w,h in boxes:
                v=cv2.resize(m[y:y+h,x:x+w].astype(np.float32),(8,10)).reshape(-1)
                error=np.mean((self.digits-v)**2,axis=1);i=int(np.argmin(error))
                values.append(int(self.labels[i]));scores.append(float(1-error[i]))
            timer_score=min(scores)
            if values[:2]==[0,0] and timer_score>.76 and values[2]<=5:
                seconds=values[2]*10+values[3]
        area=cv2.cvtColor(rgb[185:226,218:327],cv2.COLOR_RGB2GRAY)
        score=cv2.minMaxLoc(cv2.matchTemplate(area,self.badge,cv2.TM_CCOEFF_NORMED))[1]
        label=cv2.cvtColor(rgb[196:209,68:110],cv2.COLOR_RGB2GRAY)
        reward_score=cv2.matchTemplate(label,self.reward_label,cv2.TM_CCOEFF_NORMED)[0,0]
        return dict(stage=stage,stage_score=stage_score,timer=seconds,timer_score=timer_score,full_hit_badge=bool(score>.78),badge_score=float(score),reward_label=bool(reward_score>.78),reward_label_score=float(reward_score))
