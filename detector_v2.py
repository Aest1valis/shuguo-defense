"""Calibrated nine-hole state recognition and game-provided completion evidence."""
from pathlib import Path
import sys,time
import cv2
import numpy as np
from vision_model import VisualStateModel,CLASSES
from ui_read import UIReader

CENTERS=((164,282),(86,332),(242,332),(60,409),(164,409),
         (269,409),(86,484),(242,484),(164,531))

class Detector:
    WIDTH=327
    def __init__(self):
        root=Path(getattr(sys,'_MEIPASS',Path(__file__).parent))/'assets'
        self.board=cv2.imdecode(np.fromfile(root/'board_live.png',np.uint8),0)
        self.hold_template=cv2.imdecode(np.fromfile(root/'hold.png',np.uint8),0)
        self.model=VisualStateModel();self.reader=UIReader()
        self.reset_session()

    def reset_session(self):
        self.geometry=None;self.header_seen=0.;self.bonus=False;self.bonus_point=None

    def calibrate(self,gray):
        best=None
        for s in (.88,.94,1.,1.06,1.12):
            t=cv2.resize(self.board,None,fx=s,fy=s)
            response=cv2.matchTemplate(gray[:235],t,cv2.TM_CCOEFF_NORMED)
            _,score,_,xy=cv2.minMaxLoc(response)
            if best is None or score>best[0]:best=(score,xy,s,t)
        if best[0]<.77:return False
        score,(x,y),s,t=best
        self.geometry=(x+t.shape[1]/2,y+t.shape[0]/2,s,t)
        self.header_seen=time.monotonic()
        return True

    def detect(self,rgb):
        start=time.perf_counter();h,w=rgb.shape[:2]
        image=cv2.resize(rgb,(327,round(h*327/w)),interpolation=cv2.INTER_AREA)
        gray=cv2.cvtColor(image,cv2.COLOR_RGB2GRAY)
        r=dict(active=False,scene='waiting',targets=[],bombs=[],unknown=[],holes=[],hold=None,
               board_score=0.,image=image,ui={})
        if self.geometry is None and not self.calibrate(gray):return r
        cx,cy,s,template=self.geometry
        # Local verification avoids repeatedly searching the whole screen.
        bx=round(cx-template.shape[1]/2);by=round(cy-template.shape[0]/2)
        y0,y1=max(0,by-3),min(gray.shape[0],by+template.shape[0]+3)
        x0,x1=max(0,bx-3),min(gray.shape[1],bx+template.shape[1]+3)
        region=gray[y0:y1,x0:x1]
        score=cv2.minMaxLoc(cv2.matchTemplate(region,template,cv2.TM_CCOEFF_NORMED))[1]
        if score>.65:self.header_seen=time.monotonic()
        canonical=cv2.warpAffine(image,np.float32([[1/s,0,163-cx/s],[0,1/s,145-cy/s]]),(327,619),flags=cv2.INTER_LINEAR,borderMode=cv2.BORDER_REPLICATE)
        band=canonical[545:570,125:200]
        bright=float(np.max(band,axis=2).mean())>125
        if not bright:
            r['scene']='overlay';self.bonus=False;self.bonus_point=None
            return r
        if time.monotonic()-self.header_seen>.65 and not self.bonus:
            self.geometry=None
            return r
        ui=self.reader.read(canonical);r.update(active=True,scene='playing',board_score=float(score),ui=ui)
        if not self.bonus:
            area=cv2.cvtColor(canonical[470:552,110:235],cv2.COLOR_RGB2GRAY)
            best=(-1,None)
            for hs in (.94,1.,1.06):
                t=cv2.resize(self.hold_template,None,fx=hs,fy=hs)
                _,value,_,(x,y)=cv2.minMaxLoc(cv2.matchTemplate(area,t,cv2.TM_CCOEFF_NORMED))
                if value>best[0]:best=(value,(x+110+t.shape[1]/2,y+470+t.shape[0]/2-35*hs))
            hsv=cv2.cvtColor(canonical[440:518,118:216],cv2.COLOR_RGB2HSV)
            red=int(np.count_nonzero(((hsv[:,:,0]<12)|(hsv[:,:,0]>170))&(hsv[:,:,1]>150)&(hsv[:,:,2]>160)))
            if best[0]>.77 or (ui['reward_label'] and red>1100):
                self.bonus=True;self.bonus_point=best[1] if best[0]>.77 else (167.5,481.)
        if self.bonus:
            x,y=self.bonus_point
            r['hold']=dict(x=(x-163)*s+cx,y=(y-145)*s+cy,score=1.,kind='reward')
            r['scene']='bonus';r['model_ms']=(time.perf_counter()-start)*1000
            return r
        patches=[canonical[y-94:y+12,x-38:x+38] for x,y in CENTERS]
        probs=self.model.predict(patches)
        for k,((hx,hy),patch,p) in enumerate(zip(CENTERS,patches,probs)):
            p=np.asarray(p);idx=int(np.argmax(p));state=CLASSES[idx]
            hsv=cv2.cvtColor(patch[15:80,12:64],cv2.COLOR_RGB2HSV)
            charcoal=float(np.mean((hsv[:,:,1]<110)&(hsv[:,:,2]<110)))
            dark=((hsv[:,:,1]<110)&(hsv[:,:,2]<110)).astype(np.uint8)
            stats=cv2.connectedComponentsWithStats(dark,8)[2]
            banded=any(z[2]>24 and z[3]>=3 and z[4]>55 for z in stats[1:])
            # A bomb candidate is never accepted merely because the other tree
            # votes slightly prefer a partly visible normal face.
            if p[2]>.16 or (p[2]>.045 and charcoal>.075) or (p[2]>.015 and banded):state='bomb'
            elif p[1]>.47 and p[2]<.10:state='good'
            elif p[3]>.46 and p[1]<.43:state='hit'
            elif max(p)<.52:state='unknown'
            # Aim at the visible pale muzzle as it rises, not at a fixed pixel
            # above a short, just-emerging character.
            face=canonical[hy-70:hy-5,hx-20:hx+21]
            hf=cv2.cvtColor(face,cv2.COLOR_RGB2HSV)
            py=np.nonzero((hf[:,:,1]<110)&(hf[:,:,2]>170))[0]
            target_y=float(np.clip(hy-70+np.median(py)+4,hy-50,hy-8)) if len(py)>15 else hy-33.
            hit=dict(id=k,x=(hx-163)*s+cx,y=(target_y-145)*s+cy,w=50*s,h=65*s,
                     state=state,kind=state,score=float(p[idx]),good_probability=float(p[1]),
                     probabilities=[round(float(z),5) for z in p])
            r['holes'].append(hit)
            if state=='good':r['targets'].append(hit)
            elif state=='bomb':r['bombs'].append(hit)
        r['model_ms']=(time.perf_counter()-start)*1000
        return r
