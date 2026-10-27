"""Read score and fruit coins from the actual settlement panel, never the HUD."""
from pathlib import Path
import sys
from collections import Counter
import cv2
import numpy as np

class ResultReader:
    def __init__(self):
        root=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'assets'
        z=np.load(root/'result_digits.npz');self.prototypes=z['images'];self.labels=z['labels']
        self.templates={k:cv2.imdecode(np.fromfile(root/f'result_{k}_label.png',np.uint8),0)
                        for k in ('score','coins')}

    def classify(self,mask):
        yy,xx=np.nonzero(mask)
        if not len(xx):return None,1.
        mask=mask[yy.min():yy.max()+1,xx.min():xx.max()+1]
        h,w=mask.shape
        v=np.r_[cv2.resize(mask.astype(np.float32),(12,16)).reshape(-1),w/h]
        errors=np.mean((self.prototypes[:,:192]-v[:192])**2,axis=1)+.15*(self.prototypes[:,192]-v[192])**2
        k=int(np.argmin(errors));return str(self.labels[k]),float(errors[k])

    def component(self,mask):
        """Bold digits can touch. Decode the best split instead of merging them."""
        height,width=mask.shape;best={0:(0.,'',[])}
        for x in range(width):
            if x not in best:continue
            if not np.any(mask[:,x]):
                candidate=best[x]
                if x+1 not in best or candidate[0]<best[x+1][0]:best[x+1]=candidate
                continue
            for end in range(x+2,min(width,x+15)+1):
                part=mask[:,x:end];ys,xs=np.nonzero(part)
                if not len(xs) or ys.max()-ys.min()+1<max(6,height*.70):continue
                char,error=self.classify(part)
                if error>.18:continue
                cost=best[x][0]+error+.045
                if end<width:cost+=.012*float(np.count_nonzero(mask[:,end-1]))/height
                if end not in best or cost<best[end][0]:best[end]=(cost,best[x][1]+char,best[x][2]+[error])
        if width not in best:return None,None
        _,text,errors=best[width]
        if not text or len(text)>8:return None,None
        return text,max(errors)

    def number(self,rgb):
        hsv=cv2.cvtColor(rgb,cv2.COLOR_RGB2HSV);candidates=[]
        for threshold in (205,215,225,235):
            mask=((hsv[:,:,0]<30)&(hsv[:,:,1]>95)&(hsv[:,:,2]<threshold)).astype(np.uint8)
            stats=cv2.connectedComponentsWithStats(mask,8)[2]
            boxes=sorted([tuple(z[:4]) for z in stats[1:] if 6<=z[3]<=18 and z[4]/(z[2]*z[3])>.36])
            text='';errors=[];last=None
            for x,y,w,h in boxes:
                if last is not None and x-last>max(7,h*.7):break
                chars,error=self.component(mask[y:y+h,x:x+w])
                if chars is None:text='';break
                text+=chars;errors.append(error);last=x+w
            if text and len(text)<=8:candidates.append((text,max(errors)))
        if not candidates:return None,0.
        text,count=Counter(t for t,e in candidates).most_common(1)[0]
        errors=[e for t,e in candidates if t==text]
        if count<2 or max(errors)>.17:return None,0.
        return int(text),1-float(np.mean(errors))

    def read(self,rgb):
        h,w=rgb.shape[:2];image=cv2.resize(rgb,(327,round(h*327/w)),interpolation=cv2.INTER_AREA)
        if image.shape[0]<340:return None
        gray=cv2.cvtColor(image,cv2.COLOR_RGB2GRAY);anchors={};confidence=[]
        for key,(x0,x1) in {'score':(5,100),'coins':(165,249)}.items():
            region=gray[235:312,x0:x1];best=None
            for scale in (.94,1.,1.06):
                t=cv2.resize(self.templates[key],None,fx=scale,fy=scale)
                _,value,_,(x,y)=cv2.minMaxLoc(cv2.matchTemplate(region,t,cv2.TM_CCOEFF_NORMED))
                if best is None or value>best[0]:best=(value,x+x0,y+235,t.shape[1],scale)
            value,x,y,tw,scale=best
            if value<.78:return None
            anchors[key]=(x,y,tw,scale);confidence.append(value)
        if abs(anchors['score'][1]-anchors['coins'][1])>5:return None
        values={}
        for key in ('score','coins'):
            x,y,tw,s=anchors[key]
            left=round(x+tw+(3 if key=='score' else 20)*s)
            right=min(327,round(x+(113 if key=='score' else 118)*s))
            top,bottom=round(y+4*s),round(y+18*s)
            region=image[top:bottom,left:right]
            if not region.size or region.max(axis=2).mean()<195:return None
            value,score=self.number(region)
            if value is None:return None
            values[key]=value;confidence.append(score)
        return dict(score=values['score'],fruit_coins=values['coins'],confidence=float(min(confidence)))

class StableResult:
    def __init__(self):self.value=None;self.first=None;self.count=0;self.last_seen=None
    def observe(self,result,now):
        if result is None:return
        self.last_seen=now
        value=(result['score'],result['fruit_coins'])
        if self.value is None or value!=(self.value['score'],self.value['fruit_coins']):
            self.value=result;self.first=now;self.count=1
        else:self.count+=1
    def ready(self,now):
        return self.value is not None and self.count>=3 and now-self.first>=.30 and now-self.last_seen<.25
